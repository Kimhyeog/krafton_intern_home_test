"""
Phase 7 검증: Semaphore 기반 Rate Limit 동시 실행 제한 테스트

vertex_ai.py에 적용된 것과 동일한 Semaphore 설정으로
동시 실행 제한 동작을 검증합니다. (Vertex AI 모듈을 직접 import하지 않음)

테스트 전략:
- vertex_ai.py의 IMAGE_SEMAPHORE(10), VIDEO_SEMAPHORE(3) 설정을 재현
- asyncio.gather로 동시 요청을 시뮬레이션
- "현재 동시 실행 중인 수"를 카운터로 추적하여 최대치 검증
- 디트로이트파: "동시 실행이 N개를 초과하지 않는가?"(행위)를 검증
"""
import pytest
import asyncio


# ================================================================
#   vertex_ai.py와 동일한 Semaphore 설정 재현
# ================================================================

IMAGE_SEMAPHORE = asyncio.Semaphore(10)  # 이미지 동시 최대 10개
VIDEO_SEMAPHORE = asyncio.Semaphore(3)   # 비디오 동시 최대 3개


async def simulate_api_call_with_semaphore(
    semaphore: asyncio.Semaphore,
    task_id: int,
    duration: float,
    tracker: dict,
):
    """
    vertex_ai.py의 generate_image / generate_video_from_text 구조를 재현:

    async with SEMAPHORE:          ← Semaphore 안: API 호출
        await vertex_ai_call()

    file_save()                    ← Semaphore 밖: 파일 저장

    tracker로 "현재 동시 실행 수"의 최대값을 추적한다.
    """
    async with semaphore:
        tracker["current"] += 1
        if tracker["current"] > tracker["max"]:
            tracker["max"] = tracker["current"]
        # API 호출 시뮬레이션
        await asyncio.sleep(duration)
        tracker["current"] -= 1
    # Semaphore 밖: 파일 저장 시뮬레이션 (동시 실행 수에 영향 없음)
    tracker["completed"] += 1


async def simulate_api_call_with_exception(
    semaphore: asyncio.Semaphore,
    tracker: dict,
):
    """
    API 호출 중 예외 발생 시에도 Semaphore가 정상 반납되는지 검증.
    async with 블록이 __aexit__에서 자동 release() 하는 것을 확인.
    """
    async with semaphore:
        tracker["current"] += 1
        if tracker["current"] > tracker["max"]:
            tracker["max"] = tracker["current"]
        raise RuntimeError("Simulated API failure")


# ================================================================
#   IMAGE_SEMAPHORE(10) 테스트
# ================================================================

@pytest.mark.asyncio
async def test_image_semaphore_limits_to_10():
    """
    시나리오: 이미지 요청 20개 동시 실행
    기대: Semaphore(10)에 의해 동시 실행이 최대 10개로 제한됨
    """
    sem = asyncio.Semaphore(10)
    tracker = {"current": 0, "max": 0, "completed": 0}

    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.05, tracker)
        for i in range(20)
    ]
    await asyncio.gather(*tasks)

    assert tracker["max"] <= 10
    assert tracker["completed"] == 20
    print(f"\n✅ [Image] 20개 동시 요청 → 최대 동시 실행 {tracker['max']}개 (제한: 10)")


@pytest.mark.asyncio
async def test_image_semaphore_allows_up_to_10():
    """
    시나리오: 이미지 요청 10개 동시 실행
    기대: 10개 이하이므로 전부 즉시 실행 (대기 없음), 최대값 = 10
    """
    sem = asyncio.Semaphore(10)
    tracker = {"current": 0, "max": 0, "completed": 0}

    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.05, tracker)
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    assert tracker["max"] == 10
    assert tracker["completed"] == 10
    print(f"\n✅ [Image] 10개 동시 요청 → 전부 즉시 실행 (최대 {tracker['max']}개)")


# ================================================================
#   VIDEO_SEMAPHORE(3) 테스트
# ================================================================

@pytest.mark.asyncio
async def test_video_semaphore_limits_to_3():
    """
    시나리오: 비디오 요청 10개 동시 실행
    기대: Semaphore(3)에 의해 동시 실행이 최대 3개로 제한됨
    """
    sem = asyncio.Semaphore(3)
    tracker = {"current": 0, "max": 0, "completed": 0}

    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.05, tracker)
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    assert tracker["max"] <= 3
    assert tracker["completed"] == 10
    print(f"\n✅ [Video] 10개 동시 요청 → 최대 동시 실행 {tracker['max']}개 (제한: 3)")


@pytest.mark.asyncio
async def test_video_semaphore_allows_up_to_3():
    """
    시나리오: 비디오 요청 3개 동시 실행
    기대: 3개 이하이므로 전부 즉시 실행 (대기 없음), 최대값 = 3
    """
    sem = asyncio.Semaphore(3)
    tracker = {"current": 0, "max": 0, "completed": 0}

    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.05, tracker)
        for i in range(3)
    ]
    await asyncio.gather(*tasks)

    assert tracker["max"] == 3
    assert tracker["completed"] == 3
    print(f"\n✅ [Video] 3개 동시 요청 → 전부 즉시 실행 (최대 {tracker['max']}개)")


# ================================================================
#   Semaphore 안전성 테스트 (예외 시 반납, 독립성)
# ================================================================

@pytest.mark.asyncio
async def test_semaphore_released_on_exception():
    """
    시나리오: Semaphore 내부에서 예외 발생
    기대: async with가 __aexit__에서 자동 release → 슬롯 복구
          이후 작업이 정상적으로 슬롯을 획득할 수 있음
    """
    sem = asyncio.Semaphore(2)
    tracker = {"current": 0, "max": 0, "completed": 0}

    # 1) 예외를 발생시켜서 슬롯 2개를 "사용 후 반납" 시킴
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await simulate_api_call_with_exception(sem, tracker)

    # 2) 슬롯이 제대로 반납됐으면, 이후 작업이 정상 실행되어야 함
    tracker = {"current": 0, "max": 0, "completed": 0}
    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.01, tracker)
        for i in range(2)
    ]
    await asyncio.gather(*tasks)

    assert tracker["completed"] == 2
    assert sem._value == 2  # 슬롯 전부 복구됨
    print(f"\n✅ [안전성] 예외 발생 후에도 Semaphore 슬롯 정상 복구 (남은 슬롯: {sem._value})")


@pytest.mark.asyncio
async def test_image_and_video_semaphores_are_independent():
    """
    시나리오: 이미지 10개 + 비디오 5개 동시 실행
    기대: IMAGE_SEMAPHORE(10)와 VIDEO_SEMAPHORE(3)가 서로 간섭하지 않음
          이미지 동시 최대 10개, 비디오 동시 최대 3개 — 각각 독립
    """
    img_sem = asyncio.Semaphore(10)
    vid_sem = asyncio.Semaphore(3)
    img_tracker = {"current": 0, "max": 0, "completed": 0}
    vid_tracker = {"current": 0, "max": 0, "completed": 0}

    img_tasks = [
        simulate_api_call_with_semaphore(img_sem, i, 0.05, img_tracker)
        for i in range(10)
    ]
    vid_tasks = [
        simulate_api_call_with_semaphore(vid_sem, i, 0.05, vid_tracker)
        for i in range(5)
    ]

    await asyncio.gather(*img_tasks, *vid_tasks)

    assert img_tracker["max"] <= 10
    assert vid_tracker["max"] <= 3
    assert img_tracker["completed"] == 10
    assert vid_tracker["completed"] == 5
    print(
        f"\n✅ [독립성] 이미지 최대 {img_tracker['max']}개 (제한:10), "
        f"비디오 최대 {vid_tracker['max']}개 (제한:3) — 서로 간섭 없음"
    )


@pytest.mark.asyncio
async def test_all_tasks_eventually_complete():
    """
    시나리오: Semaphore(3)에 요청 100개 동시 실행
    기대: 동시 3개씩 순차 처리하여 100개 전부 완료 (누락 없음)
    """
    sem = asyncio.Semaphore(3)
    tracker = {"current": 0, "max": 0, "completed": 0}

    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.01, tracker)
        for i in range(100)
    ]
    await asyncio.gather(*tasks)

    assert tracker["max"] <= 3
    assert tracker["completed"] == 100
    print(
        f"\n✅ [완료 보장] 100개 요청 → 최대 동시 {tracker['max']}개, "
        f"전부 완료 ({tracker['completed']}개)"
    )


@pytest.mark.asyncio
async def test_semaphore_value_restored_after_all_complete():
    """
    시나리오: Semaphore(3)에 요청 10개 실행 후 전부 완료
    기대: 완료 후 _value가 초기값(3)으로 복구됨
    """
    sem = asyncio.Semaphore(3)
    tracker = {"current": 0, "max": 0, "completed": 0}

    tasks = [
        simulate_api_call_with_semaphore(sem, i, 0.01, tracker)
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    assert sem._value == 3
    assert tracker["completed"] == 10
    print(f"\n✅ [복구] 10개 완료 후 Semaphore._value = {sem._value} (초기값으로 복구)")
