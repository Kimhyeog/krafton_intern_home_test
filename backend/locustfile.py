"""
부하 테스트: 큐잉 시스템(Semaphore) 순차 처리 검증

- 200명 동시 요청으로 Semaphore 한도(이미지 10, 비디오 3) 초과 시
  대기열에서 유실 없이 순차 처리되는지 검증

실행 방법:
  1. LOAD_TEST_MODE=true uvicorn app.main:app --host 0.0.0.0 --port 8000
  2. locust -f locustfile.py
  3. http://localhost:8089 접속 → Users=200, Ramp up=10, Host=http://localhost:8000

Headless 모드 (소규모 빠른 확인):
  locust -f locustfile.py --headless -u 10 -r 5 -t 30s --host http://localhost:8000
"""

import json
import time
import random
import uuid
from locust import HttpUser, task, between, events


# 베이스 프롬프트 — 매 요청마다 UUID를 붙여 캐시 미스 강제
IMAGE_BASE_PROMPTS = [
    "a fantasy sword in dark background",
    "a sci-fi spaceship in nebula",
    "a medieval castle on a cliff",
    "a crystal potion bottle glowing blue",
    "a dragon scale armor set",
]

VIDEO_BASE_PROMPTS = [
    "a dragon flying over mountains",
    "a knight riding through a forest",
    "an explosion of magical particles",
]


class GameAssetUser(HttpUser):
    """게임 에셋 생성 사용자 시뮬레이션"""

    # 요청 간 대기 시간: 1~3초 (실제 사용자 행동 모방)
    wait_time = between(1, 3)

    @task(7)
    def generate_image(self):
        """이미지 생성 요청 (70% 비율)"""
        # UUID suffix로 매 요청마다 고유 프롬프트 → 캐시 미스 강제 → Semaphore 큐잉 검증
        prompt = f"{random.choice(IMAGE_BASE_PROMPTS)} {uuid.uuid4().hex[:8]}"
        start = time.time()

        # 1. 생성 요청
        with self.client.post(
            "/api/generate/text-to-image",
            json={
                "prompt": prompt,
                "model": "imagen-3.0-fast-generate-001",
            },
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"POST failed: {response.status_code}")
                return
            data = response.json()
            job_id = data["job_id"]

        # 2. 캐시 히트 시 즉시 완료
        if data["status"] == "completed":
            return

        # 3. SSE로 완료 대기
        self._wait_for_completion(job_id, "image", start)

    @task(3)
    def generate_video(self):
        """비디오 생성 요청 (30% 비율)"""
        # UUID suffix로 매 요청마다 고유 프롬프트 → 캐시 미스 강제 → Semaphore 큐잉 검증
        prompt = f"{random.choice(VIDEO_BASE_PROMPTS)} {uuid.uuid4().hex[:8]}"
        start = time.time()

        with self.client.post(
            "/api/generate/text-to-video",
            json={
                "prompt": prompt,
                "model": "veo-3.0-fast-generate-001",
            },
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"POST failed: {response.status_code}")
                return
            data = response.json()
            job_id = data["job_id"]

        if data["status"] == "completed":
            return

        self._wait_for_completion(job_id, "video", start)

    def _wait_for_completion(self, job_id: str, asset_type: str, start: float):
        """SSE 스트림으로 작업 완료 대기"""
        try:
            with self.client.get(
                f"/api/generate/jobs/{job_id}/stream",
                stream=True,
                catch_response=True,
                name=f"/api/generate/jobs/[id]/stream ({asset_type})",
                timeout=120,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"SSE failed: {response.status_code}")
                    return

                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line.startswith("data: "):
                        data = json.loads(line[6:])

                        if data["status"] == "completed":
                            response.success()
                            return

                        if data["status"] == "failed":
                            response.failure(
                                f"Job failed: {data.get('error_message')}"
                            )
                            return

                response.failure("SSE stream ended without completion")

        except Exception as e:
            # 타임아웃 등의 에러
            events.request.fire(
                request_type="SSE",
                name=f"/api/generate/jobs/[id]/stream ({asset_type})",
                response_time=(time.time() - start) * 1000,
                response_length=0,
                exception=e,
            )
