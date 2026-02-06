"""
Phase 4 검증: Exponential Backoff 재시도 테스트

vertex_ai.py에 적용된 것과 동일한 tenacity 설정으로
재시도 동작을 검증합니다. (Vertex AI 모듈을 직접 import하지 않음)
"""
import pytest
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


# vertex_ai.py에 정의된 것과 동일한 예외 클래스
class RetryableAPIError(Exception):
    """429, 503 등 재시도 가능한 에러"""
    pass

class NonRetryableAPIError(Exception):
    """400 등 재시도 불가한 에러"""
    pass


# vertex_ai.py의 generate_image와 동일한 @retry 설정을 시뮬레이션
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1),  # 테스트용: 대기 시간 최소화
    retry=retry_if_exception_type(RetryableAPIError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def simulate_imagen_call(fake_api_func):
    """generate_image의 에러 분류 로직을 그대로 재현"""
    try:
        return fake_api_func()
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise RetryableAPIError(error_str)
        if "503" in error_str or "UNAVAILABLE" in error_str:
            raise RetryableAPIError(error_str)
        if "500" in error_str or "INTERNAL" in error_str:
            raise RetryableAPIError(error_str)
        raise NonRetryableAPIError(error_str)


# _start_veo_operation과 동일한 @retry 설정
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1),  # 테스트용
    retry=retry_if_exception_type(RetryableAPIError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def simulate_veo_start(fake_api_func):
    """_start_veo_operation의 에러 분류 로직을 재현"""
    status_code, body = fake_api_func()
    if status_code == 429:
        raise RetryableAPIError(f"Rate limit exceeded: {body}")
    if status_code >= 500:
        raise RetryableAPIError(f"Server error {status_code}: {body}")
    if status_code != 200:
        raise NonRetryableAPIError(f"Client error {status_code}: {body}")
    return body


# ================================================================
#   Imagen (generate_image) 재시도 테스트
# ================================================================

@pytest.mark.asyncio
async def test_imagen_429_retry_then_succeed():
    """
    시나리오: Imagen 호출 → 429 2번 → 3번째 성공
    기대: tenacity가 재시도하여 최종 성공, 총 3번 호출
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise Exception("429 Resource has been exhausted")
        return "image_bytes"

    result = await simulate_imagen_call(fake_api)

    assert result == "image_bytes"
    assert call_count == 3
    print(f"\n✅ [Imagen] 429 에러 2번 → 3번째 성공 (총 {call_count}번 호출)")


@pytest.mark.asyncio
async def test_imagen_503_retry_then_succeed():
    """
    시나리오: 503 1번 → 2번째 성공
    기대: 503도 재시도 대상
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise Exception("503 UNAVAILABLE: service temporarily down")
        return "image_bytes"

    result = await simulate_imagen_call(fake_api)

    assert result == "image_bytes"
    assert call_count == 2
    print(f"\n✅ [Imagen] 503 에러 1번 → 2번째 성공 (총 {call_count}번 호출)")


@pytest.mark.asyncio
async def test_imagen_500_retry_then_succeed():
    """
    시나리오: 500 INTERNAL 1번 → 2번째 성공
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise Exception("500 INTERNAL server error")
        return "image_bytes"

    result = await simulate_imagen_call(fake_api)

    assert result == "image_bytes"
    assert call_count == 2
    print(f"\n✅ [Imagen] 500 에러 1번 → 2번째 성공 (총 {call_count}번 호출)")


@pytest.mark.asyncio
async def test_imagen_400_no_retry():
    """
    시나리오: 400 Bad Request 발생
    기대: 재시도 없이 즉시 NonRetryableAPIError 발생
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        raise Exception("400 Bad Request: invalid prompt")

    with pytest.raises(NonRetryableAPIError):
        await simulate_imagen_call(fake_api)

    assert call_count == 1
    print(f"\n✅ [Imagen] 400 에러 → 재시도 없이 즉시 실패 ({call_count}번만 호출)")


@pytest.mark.asyncio
async def test_imagen_gives_up_after_5_attempts():
    """
    시나리오: 429가 계속 발생
    기대: 5번 시도 후 최종 포기 (stop_after_attempt=5)
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        raise Exception("429 RESOURCE_EXHAUSTED")

    with pytest.raises(RetryableAPIError):
        await simulate_imagen_call(fake_api)

    assert call_count == 5
    print(f"\n✅ [Imagen] 429 연속 → {call_count}번 시도 후 포기 (최대 5회)")


# ================================================================
#   Veo (_start_veo_operation) 재시도 테스트
# ================================================================

@pytest.mark.asyncio
async def test_veo_429_retry_then_succeed():
    """
    시나리오: Veo 시작 → 429 1번 → 2번째 성공
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return (429, "rate limit exceeded")
        return (200, "operation-name-123")

    result = await simulate_veo_start(fake_api)

    assert result == "operation-name-123"
    assert call_count == 2
    print(f"\n✅ [Veo] 429 에러 1번 → 2번째 성공 (총 {call_count}번 호출)")


@pytest.mark.asyncio
async def test_veo_500_retry_then_succeed():
    """
    시나리오: Veo 시작 → 500 1번 → 2번째 성공
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return (500, "internal server error")
        return (200, "operation-name-456")

    result = await simulate_veo_start(fake_api)

    assert result == "operation-name-456"
    assert call_count == 2
    print(f"\n✅ [Veo] 500 에러 1번 → 2번째 성공 (총 {call_count}번 호출)")


@pytest.mark.asyncio
async def test_veo_400_no_retry():
    """
    시나리오: Veo 시작 → 400 Bad Request
    기대: 재시도 없이 즉시 NonRetryableAPIError
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        return (400, "bad request")

    with pytest.raises(NonRetryableAPIError):
        await simulate_veo_start(fake_api)

    assert call_count == 1
    print(f"\n✅ [Veo] 400 에러 → 재시도 없이 즉시 실패 ({call_count}번만 호출)")


@pytest.mark.asyncio
async def test_veo_gives_up_after_3_attempts():
    """
    시나리오: Veo 시작 → 429 계속 발생
    기대: 3번 시도 후 포기 (stop_after_attempt=3, Imagen의 5회보다 보수적)
    """
    call_count = 0

    def fake_api():
        nonlocal call_count
        call_count += 1
        return (429, "rate limit")

    with pytest.raises(RetryableAPIError):
        await simulate_veo_start(fake_api)

    assert call_count == 3
    print(f"\n✅ [Veo] 429 연속 → {call_count}번 시도 후 포기 (최대 3회, Imagen보다 보수적)")
