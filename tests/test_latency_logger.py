import logging
from unittest.mock import patch

import pytest

from latency_logger import finalize_call, handle_event, reset_trackers

CALL_ID = "test-call-abc"
CALL = {"id": CALL_ID}


def _body(event_type: str, **fields) -> dict:
    return {"message": {"type": event_type, "call": CALL, **fields}}


@pytest.fixture(autouse=True)
def clear_trackers():
    reset_trackers()
    yield
    reset_trackers()


@pytest.fixture
def cap_latency(caplog):
    with caplog.at_level(logging.DEBUG, logger="vapi_latency"):
        yield caplog


def test_response_latency_on_clean_turn(cap_latency):
    times = iter([0.0, 0.5, 0.84])

    with patch("latency_logger.time.monotonic", side_effect=lambda: next(times)):
        handle_event(_body("speech-update", role="user", status="started", turn=0))
        handle_event(_body("speech-update", role="user", status="stopped", turn=0))
        handle_event(_body("speech-update", role="assistant", status="started", turn=1))

    assert any("response_latency" in r.message and "ms=339" in r.message for r in cap_latency.records)


def test_barge_in_when_user_starts_during_assistant_speech(cap_latency):
    with patch("latency_logger.time.monotonic", side_effect=[0.0, 0.1, 0.2]):
        handle_event(_body("speech-update", role="assistant", status="started", turn=0))
        handle_event(_body("speech-update", role="user", status="started", turn=1))

    warnings = [r for r in cap_latency.records if r.levelno == logging.WARNING]
    assert any("BARGE_IN" in r.message and "user_started_while_assistant_speaking" in r.message for r in warnings)


def test_double_speak_when_assistant_restarts(cap_latency):
    with patch("latency_logger.time.monotonic", side_effect=[0.0, 0.1]):
        handle_event(_body("speech-update", role="assistant", status="started", turn=0))
        handle_event(_body("speech-update", role="assistant", status="started", turn=0))

    warnings = [r for r in cap_latency.records if r.levelno == logging.WARNING]
    assert any("DOUBLE_SPEAK" in r.message for r in warnings)


def test_finalize_call_summary(cap_latency):
    times = iter([0.0, 0.5, 0.9, 1.0, 1.4])

    with patch("latency_logger.time.monotonic", side_effect=lambda: next(times)):
        handle_event(_body("speech-update", role="user", status="started", turn=0))
        handle_event(_body("speech-update", role="user", status="stopped", turn=0))
        handle_event(_body("speech-update", role="assistant", status="started", turn=1))
        handle_event(_body("speech-update", role="assistant", status="started", turn=1))
        handle_event(_body("user-interrupted", turnId="turn-1"))

    summary = finalize_call(CALL_ID)

    assert "barge_ins=1" in summary
    assert "double_speaks=1" in summary
    assert "avg_response_ms=400" in summary
    assert any("call_summary" in r.message for r in cap_latency.records)
