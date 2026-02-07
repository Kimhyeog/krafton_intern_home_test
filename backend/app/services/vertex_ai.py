import os
import asyncio
import base64
import time
import random
import logging

import aiofiles
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.config import get_settings

# Mock 모드: LOAD_TEST_MODE=true 일 때 Vertex AI 호출을 asyncio.sleep으로 대체
LOAD_TEST_MODE = os.environ.get("LOAD_TEST_MODE", "").lower() == "true"

if not LOAD_TEST_MODE:
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

settings = get_settings()

VEO_MODEL = "veo-3.0-fast-generate-001"
IMAGEN_MODEL = "imagen-3.0-fast-generate-001"

# Vertex AI API 스코프
VERTEX_AI_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]

# LRO Polling 설정
LRO_POLL_INTERVAL = 10  # 10초마다 상태 확인
LRO_MAX_WAIT_TIME = 600  # 최대 10분 대기

# Rate Limit 제어용 Semaphore
# Vertex AI Rate Limit: 이미지 60회/분, 비디오 10회/분
IMAGE_SEMAPHORE = asyncio.Semaphore(10)  # 이미지 동시 최대 10개
VIDEO_SEMAPHORE = asyncio.Semaphore(3)   # 비디오 동시 최대 3개


# ===== 재시도용 커스텀 예외 =====

class RetryableAPIError(Exception):
    """429 (Rate Limit), 503 (Service Unavailable) 등 재시도 가능한 에러"""
    pass

class NonRetryableAPIError(Exception):
    """400 (Bad Request) 등 재시도해도 의미 없는 에러"""
    pass

# 서비스 계정 파일 경로
SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/app/credentials/service-account.json"
)


# ===== Vertex AI 안전 정책 에러 → 한글 변환 =====

_SAFETY_PATTERNS = [
    # (영문 패턴, 한글 사유 메시지)
    ("usage guidelines", "입력하신 프롬프트가 Vertex AI 이용 정책을 위반하여 요청이 거부되었습니다."),
    ("could not be submitted", "입력하신 프롬프트가 정책에 의해 제출이 거부되었습니다."),
    ("raiMediaFiltered", "생성된 콘텐츠가 안전 정책(폭력, 선정성 등)에 의해 차단되었습니다."),
    ("safety", "안전 정책에 의해 요청이 차단되었습니다."),
    ("responsible ai", "AI 윤리 정책에 의해 요청이 차단되었습니다."),
    ("copyright", "저작권 관련 정책에 의해 차단되었습니다."),
    ("trademark", "상표권 관련 정책에 의해 차단되었습니다."),
    ("person", "특정 인물 생성이 정책에 의해 제한되었습니다."),
    ("child", "아동 관련 콘텐츠가 정책에 의해 차단되었습니다."),
    ("blocked", "콘텐츠 정책에 의해 차단되었습니다."),
]

def _to_korean_safety_message(error_msg: str) -> str | None:
    """
    Vertex AI 에러 메시지에서 안전 정책 관련 패턴을 감지하여 한글로 변환.
    안전 정책과 무관한 에러이면 None을 반환.
    """
    lower = error_msg.lower()
    for pattern, korean_msg in _SAFETY_PATTERNS:
        if pattern in lower:
            return f"{korean_msg} 프롬프트를 수정한 후 다시 시도해 주세요."
    return None


class VertexAIService:
    def __init__(self):
        if LOAD_TEST_MODE:
            # Mock 모드: GCP 인증/SDK 초기화 건너뛰기
            logger.info("[VertexAI] LOAD_TEST_MODE enabled — skipping GCP auth")
            print("[VertexAI] LOAD_TEST_MODE enabled — using mock generation")
            return

        self.project = settings.google_cloud_project
        self.location = settings.google_cloud_region

        # 서비스 계정 인증 정보 로드 (스코프 포함)
        self.credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=VERTEX_AI_SCOPES
        )

        # Vertex AI 초기화 (Imagen용)
        vertexai.init(
            project=self.project,
            location=self.location,
            credentials=self.credentials
        )

        self.image_model = ImageGenerationModel.from_pretrained(IMAGEN_MODEL)

        # Veo API 엔드포인트 (REST API)
        self.veo_base_url = f"https://{self.location}-aiplatform.googleapis.com/v1"
        self.veo_endpoint = f"projects/{self.project}/locations/{self.location}/publishers/google/models/{VEO_MODEL}"

        print(f"[VertexAI] Initialized with project={self.project}, location={self.location}")
        print(f"[VertexAI] Service account: {SERVICE_ACCOUNT_FILE}")

    def _get_auth_token(self) -> str:
        """인증 토큰 가져오기 (자동 갱신)"""
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        return self.credentials.token

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(RetryableAPIError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def generate_image(self, prompt: str, job_id: str) -> str:
        """
        Text-to-Image: Imagen 3.0으로 이미지 생성

        - Semaphore로 동시 실행 수 제한 (최대 10개)
        - 429/503 에러 시 Exponential Backoff로 자동 재시도 (최대 5회)
        """
        async with IMAGE_SEMAPHORE:
            logger.info(f"[Imagen] Acquired semaphore for job {job_id}")

            if LOAD_TEST_MODE:
                # Mock: 실제 API 대신 2~4초 대기
                await asyncio.sleep(random.uniform(2, 4))
                file_name = f"{job_id}.png"
                file_path = os.path.join(settings.storage_path, "images", file_name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(b"mock-image-data")
                logger.info(f"[Imagen] Mock generation completed for job {job_id}")
                return f"/storage/images/{file_name}"

            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.image_model.generate_images(
                        prompt=prompt,
                        number_of_images=1
                    )
                )
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    logger.warning(f"[Imagen] Rate limit hit, will retry: {error_str}")
                    raise RetryableAPIError(error_str)
                if "503" in error_str or "UNAVAILABLE" in error_str:
                    logger.warning(f"[Imagen] Service unavailable, will retry: {error_str}")
                    raise RetryableAPIError(error_str)
                if "500" in error_str or "INTERNAL" in error_str:
                    logger.warning(f"[Imagen] Internal error, will retry: {error_str}")
                    raise RetryableAPIError(error_str)
                # 400, 403 등은 재시도 불가 — 안전 정책이면 한글 변환
                korean = _to_korean_safety_message(error_str)
                if korean:
                    logger.warning(f"[Imagen] Safety policy error: {error_str}")
                    raise NonRetryableAPIError(korean)
                raise NonRetryableAPIError(error_str)

        # 파일 저장은 Semaphore 밖 (I/O가 슬롯을 점유할 필요 없음)
        file_name = f"{job_id}.png"
        file_path = os.path.join(settings.storage_path, "images", file_name)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(response.images[0]._image_bytes)

        return f"/storage/images/{file_name}"

    async def generate_video_from_text(self, prompt: str, job_id: str) -> str:
        """
        Text-to-Video: Veo로 텍스트에서 비디오 생성

        - Semaphore로 동시 실행 수 제한 (최대 3개)
        - LRO 요청 + 폴링 전체가 Semaphore 안에서 실행
        """
        logger.info(f"[Veo] Starting text-to-video generation for job {job_id}")

        async with VIDEO_SEMAPHORE:
            logger.info(f"[Veo] Acquired semaphore for job {job_id}")

            if LOAD_TEST_MODE:
                # Mock: 실제 API 대신 3~6초 대기
                await asyncio.sleep(random.uniform(3, 6))
                file_name = f"{job_id}.mp4"
                file_path = os.path.join(settings.storage_path, "videos", file_name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(b"mock-video-data")
                logger.info(f"[Veo] Mock generation completed for job {job_id}")
                return f"/storage/videos/{file_name}"

            # 1. LRO 요청 시작
            operation_name = await self._start_veo_operation(
                prompt=prompt,
                image_base64=None
            )

            # 2. Operation 완료까지 폴링
            result = await self._poll_operation(operation_name)

        # 3. 비디오 추출 및 저장 (Semaphore 밖)
        video_bytes = self._extract_video_from_result(result)

        file_name = f"{job_id}.mp4"
        file_path = os.path.join(settings.storage_path, "videos", file_name)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(video_bytes)

        logger.info(f"[Veo] Video saved to {file_path}")
        return f"/storage/videos/{file_name}"

    async def generate_video_from_image(self, prompt: str, image_bytes: bytes, job_id: str, mime_type: str = "image/png") -> str:
        """
        Image-to-Video: Veo로 이미지에서 비디오 생성

        - Semaphore로 동시 실행 수 제한 (최대 3개)
        - LRO 요청 + 폴링 전체가 Semaphore 안에서 실행
        """
        logger.info(f"[Veo] Starting image-to-video generation for job {job_id}")

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        async with VIDEO_SEMAPHORE:
            logger.info(f"[Veo] Acquired semaphore for job {job_id}")

            if LOAD_TEST_MODE:
                # Mock: 실제 API 대신 3~6초 대기
                await asyncio.sleep(random.uniform(3, 6))
                file_name = f"{job_id}.mp4"
                file_path = os.path.join(settings.storage_path, "videos", file_name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(b"mock-video-data")
                logger.info(f"[Veo] Mock generation completed for job {job_id}")
                return f"/storage/videos/{file_name}"

            # 1. LRO 요청 시작
            operation_name = await self._start_veo_operation(
                prompt=prompt,
                image_base64=image_base64,
                image_mime_type=mime_type
            )

            # 2. Operation 완료까지 폴링
            result = await self._poll_operation(operation_name)

        # 3. 비디오 추출 및 저장 (Semaphore 밖)
        video_bytes = self._extract_video_from_result(result)

        file_name = f"{job_id}.mp4"
        file_path = os.path.join(settings.storage_path, "videos", file_name)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(video_bytes)

        logger.info(f"[Veo] Video saved to {file_path}")
        return f"/storage/videos/{file_name}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        retry=retry_if_exception_type(RetryableAPIError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _start_veo_operation(self, prompt: str, image_base64: str = None, image_mime_type: str = None) -> str:
        """
        Veo LRO 작업 시작 (REST API)
        - 429/503 에러 시 Exponential Backoff로 자동 재시도 (최대 3회)

        Returns:
            str: Operation name (폴링에 사용)
        """
        url = f"{self.veo_base_url}/{self.veo_endpoint}:predictLongRunning"

        # 요청 본문 구성
        instance = {"prompt": prompt}

        if image_base64:
            instance["image"] = {
                "bytesBase64Encoded": image_base64,
                "mimeType": image_mime_type or "image/png"
            }

        payload = {
            "instances": [instance],
            "parameters": {
                "sampleCount": 1,
                "durationSeconds": 8,
                "aspectRatio": "16:9"
            }
        }

        headers = {
            "Authorization": f"Bearer {self._get_auth_token()}",
            "Content-Type": "application/json"
        }

        logger.info(f"[Veo LRO] Calling: {url}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            # HTTP 상태 코드별 분류
            if response.status_code == 429:
                raise RetryableAPIError(f"Rate limit exceeded: {response.text}")
            if response.status_code >= 500:
                raise RetryableAPIError(f"Server error {response.status_code}: {response.text}")
            if response.status_code != 200:
                korean = _to_korean_safety_message(response.text)
                if korean:
                    logger.warning(f"[Veo LRO] Safety policy error in request: {response.text}")
                    raise NonRetryableAPIError(korean)
                raise NonRetryableAPIError(f"Client error {response.status_code}: {response.text}")

            result = response.json()
            operation_name = result.get("name")

            if not operation_name:
                raise NonRetryableAPIError(f"No operation name in response: {result}")

            logger.info(f"[Veo LRO] Operation started: {operation_name}")
            return operation_name

    async def _poll_operation(self, operation_name: str) -> dict:
        """
        Operation 완료까지 폴링 (REST API)

        Veo LRO는 fetchPredictOperation 엔드포인트를 사용합니다.

        Args:
            operation_name: predictLongRunning에서 반환된 operation name

        Returns:
            dict: 완료된 Operation의 결과
        """
        # fetchPredictOperation 엔드포인트 사용
        url = f"{self.veo_base_url}/{self.veo_endpoint}:fetchPredictOperation"

        print(f"[Veo LRO] Polling URL: {url}")
        print(f"[Veo LRO] Operation name: {operation_name}")
        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self._get_auth_token()}",
            "Content-Type": "application/json"
        }

        # fetchPredictOperation 요청 본문
        payload = {
            "operationName": operation_name
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                elapsed = time.time() - start_time

                # 타임아웃 체크
                if elapsed > LRO_MAX_WAIT_TIME:
                    raise TimeoutError(f"Veo operation timed out after {LRO_MAX_WAIT_TIME} seconds")

                # Operation 상태 조회 (POST 요청)
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code != 200:
                    raise Exception(f"Failed to poll operation: {response.status_code} - {response.text}")

                result = response.json()

                # 완료 여부 확인
                if result.get("done"):
                    print(f"[Veo LRO] Operation completed after {elapsed:.1f}s")

                    # 에러 체크
                    if "error" in result:
                        error = result["error"]
                        raw_msg = error.get("message", str(error))
                        korean = _to_korean_safety_message(raw_msg)
                        if korean:
                            logger.warning(f"[Veo LRO] Safety policy error: {raw_msg}")
                            raise Exception(korean)
                        raise Exception(f"Veo operation failed: {raw_msg}")

                    # 응답 구조 로깅 (디버깅용)
                    print(f"[Veo LRO] Full response keys: {list(result.keys())}")
                    print(f"[Veo LRO] Full response: {result}")

                    return result.get("response", result)

                # 진행 상황 로깅
                metadata = result.get("metadata", {})
                state = metadata.get("state", "RUNNING")
                print(f"[Veo LRO] State: {state}, waiting... ({elapsed:.0f}s elapsed)")

                # 폴링 간격만큼 대기
                await asyncio.sleep(LRO_POLL_INTERVAL)

    def _extract_video_from_result(self, result: dict) -> bytes:
        """
        LRO 결과에서 비디오 바이트 추출

        Args:
            result: Operation response

        Returns:
            bytes: 비디오 파일 바이트
        """
        # RAI 안전 필터 체크 (try 밖 — 한글 메시지가 이중 래핑되지 않도록)
        rai_count = result.get("raiMediaFilteredCount", 0)
        if rai_count and int(rai_count) > 0:
            reasons = result.get("raiMediaFilteredReasons", [])
            reason_text = reasons[0] if reasons else "raiMediaFiltered"
            logger.warning(f"[Veo LRO] RAI filter blocked: {reasons}")
            korean = _to_korean_safety_message(reason_text)
            raise Exception(korean or "생성된 콘텐츠가 안전 정책에 의해 차단되었습니다. 프롬프트를 수정한 후 다시 시도해 주세요.")

        try:
            # 방법 1: predictions 배열에서 추출
            predictions = result.get("predictions", [])
            if predictions:
                prediction = predictions[0]

                # 직접 bytesBase64Encoded
                if "bytesBase64Encoded" in prediction:
                    print("[Veo LRO] Found video in predictions.bytesBase64Encoded")
                    return base64.b64decode(prediction["bytesBase64Encoded"])

                # video.bytesBase64Encoded
                if "video" in prediction:
                    video_data = prediction["video"]
                    if "bytesBase64Encoded" in video_data:
                        print("[Veo LRO] Found video in predictions.video.bytesBase64Encoded")
                        return base64.b64decode(video_data["bytesBase64Encoded"])

            # 방법 2: videos 배열에서 추출 (GenerateVideoResponse 형식)
            videos = result.get("videos", [])
            if videos:
                video = videos[0]
                if "bytesBase64Encoded" in video:
                    print("[Veo LRO] Found video in videos[0].bytesBase64Encoded")
                    return base64.b64decode(video["bytesBase64Encoded"])

            # 방법 3: generatedSamples에서 추출
            generated_samples = result.get("generatedSamples", [])
            if generated_samples:
                sample = generated_samples[0]
                if "video" in sample and "bytesBase64Encoded" in sample["video"]:
                    print("[Veo LRO] Found video in generatedSamples.video.bytesBase64Encoded")
                    return base64.b64decode(sample["video"]["bytesBase64Encoded"])

            # 방법 4: 직접 video 필드
            if "video" in result and "bytesBase64Encoded" in result["video"]:
                print("[Veo LRO] Found video in result.video.bytesBase64Encoded")
                return base64.b64decode(result["video"]["bytesBase64Encoded"])

            # 디버깅용 로깅
            print(f"[Veo LRO] Result structure: {list(result.keys())}")
            print(f"[Veo LRO] Full result: {result}")

            raise Exception("Could not find video data in result")

        except Exception as e:
            print(f"[Veo LRO] Error extracting video: {e}")
            raise Exception(f"Failed to extract video from response: {e}")


vertex_ai_service = VertexAIService()
