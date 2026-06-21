import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("vapi_latency")

_trackers: dict[str, "CallTracker"] = {}


@dataclass
class SpeechState:
    status: str = "stopped"
    turn: int | None = None
    started_at: float | None = None


@dataclass
class CallTracker:
    call_id: str
    last_event_at: float | None = None
    user: SpeechState = field(default_factory=SpeechState)
    assistant: SpeechState = field(default_factory=SpeechState)
    barge_in_count: int = 0
    double_speak_count: int = 0
    response_latencies_ms: list[int] = field(default_factory=list)
    user_stopped_at: float | None = None
    user_stopped_turn: int | None = None
    turn_count: int = 0

    def touch(self, now: float) -> int | None:
        delta = None
        if self.last_event_at is not None:
            delta = int((now - self.last_event_at) * 1000)
        self.last_event_at = now
        return delta


def _get_call_id(message: dict) -> str:
    return message.get("call", {}).get("id", "unknown")


def _get_tracker(call_id: str) -> CallTracker:
    if call_id not in _trackers:
        _trackers[call_id] = CallTracker(call_id=call_id)
    return _trackers[call_id]


def _preview(text: str, max_len: int = 80) -> str:
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def _handle_speech_update(message: dict, now: float) -> None:
    call_id = _get_call_id(message)
    tracker = _get_tracker(call_id)
    delta = tracker.touch(now)

    role = message.get("role", "")
    status = message.get("status", "")
    turn = message.get("turn")

    logger.info(
        "speech-update | call_id='%s' | role='%s' | status='%s' | turn=%s | delta_ms=%s",
        call_id,
        role,
        status,
        turn,
        delta if delta is not None else "n/a",
    )

    if role not in ("user", "assistant"):
        return

    state: SpeechState = tracker.user if role == "user" else tracker.assistant
    other: SpeechState = tracker.assistant if role == "user" else tracker.user

    if status == "started":
        if role == "user" and other.status == "started":
            tracker.barge_in_count += 1
            logger.warning(
                "BARGE_IN | call_id='%s' | user_started_while_assistant_speaking | "
                "turn=%s | assistant_turn=%s",
                call_id,
                turn,
                other.turn,
            )
        if role == "assistant" and state.status == "started":
            tracker.double_speak_count += 1
            logger.warning(
                "DOUBLE_SPEAK | call_id='%s' | assistant_started_before_stopped | "
                "turn=%s | prior_turn=%s",
                call_id,
                turn,
                state.turn,
            )
        if role == "assistant" and tracker.user_stopped_at is not None:
            latency_ms = int((now - tracker.user_stopped_at) * 1000)
            tracker.response_latencies_ms.append(latency_ms)
            logger.info(
                "response_latency | call_id='%s' | ms=%d | user_turn=%s -> assistant_turn=%s",
                call_id,
                latency_ms,
                tracker.user_stopped_turn,
                turn,
            )
            tracker.user_stopped_at = None
            tracker.user_stopped_turn = None

        state.status = "started"
        state.turn = turn
        state.started_at = now
        if turn is not None:
            tracker.turn_count = max(tracker.turn_count, turn + 1)

    elif status == "stopped":
        if state.started_at is not None:
            duration_ms = int((now - state.started_at) * 1000)
            logger.info(
                "turn_duration | call_id='%s' | role='%s' | turn=%s | ms=%d",
                call_id,
                role,
                turn,
                duration_ms,
            )
        if role == "user":
            tracker.user_stopped_at = now
            tracker.user_stopped_turn = turn

        state.status = "stopped"
        state.started_at = None


def _handle_conversation_update(message: dict, now: float) -> None:
    call_id = _get_call_id(message)
    tracker = _get_tracker(call_id)
    delta = tracker.touch(now)

    messages = message.get("messages") or message.get("messagesOpenAIFormatted") or []
    if not messages:
        logger.info(
            "conversation-update | call_id='%s' | delta_ms=%s | messages=0",
            call_id,
            delta if delta is not None else "n/a",
        )
        return

    last = messages[-1]
    role = last.get("role", "unknown")
    text = last.get("message") or last.get("content") or ""
    if isinstance(text, list):
        text = " ".join(str(part) for part in text)

    logger.info(
        "conversation-update | call_id='%s' | role='%s' | preview='%s' | delta_ms=%s",
        call_id,
        role,
        _preview(str(text)),
        delta if delta is not None else "n/a",
    )


def _handle_user_interrupted(message: dict, now: float) -> None:
    call_id = _get_call_id(message)
    tracker = _get_tracker(call_id)
    delta = tracker.touch(now)
    turn_id = message.get("turnId")
    tracker.barge_in_count += 1
    logger.warning(
        "BARGE_IN | call_id='%s' | user_interrupted | turnId='%s' | delta_ms=%s",
        call_id,
        turn_id or "n/a",
        delta if delta is not None else "n/a",
    )


def _handle_transcript(message: dict, now: float) -> None:
    call_id = _get_call_id(message)
    tracker = _get_tracker(call_id)
    delta = tracker.touch(now)
    logger.debug(
        "transcript | call_id='%s' | role='%s' | type='%s' | preview='%s' | delta_ms=%s",
        call_id,
        message.get("role", ""),
        message.get("transcriptType", ""),
        _preview(message.get("transcript", "")),
        delta if delta is not None else "n/a",
    )


def _handle_status_update(message: dict, now: float) -> None:
    call_id = _get_call_id(message)
    tracker = _get_tracker(call_id)
    delta = tracker.touch(now)
    logger.info(
        "status-update | call_id='%s' | status='%s' | delta_ms=%s",
        call_id,
        message.get("status", ""),
        delta if delta is not None else "n/a",
    )


def _handle_assistant_started(message: dict, now: float) -> None:
    call_id = _get_call_id(message)
    tracker = _get_tracker(call_id)
    delta = tracker.touch(now)
    logger.info(
        "assistant.started | call_id='%s' | delta_ms=%s",
        call_id,
        delta if delta is not None else "n/a",
    )


_HANDLERS = {
    "speech-update": _handle_speech_update,
    "conversation-update": _handle_conversation_update,
    "user-interrupted": _handle_user_interrupted,
    "transcript": _handle_transcript,
    "status-update": _handle_status_update,
    "assistant.started": _handle_assistant_started,
}


def handle_event(body: dict) -> None:
    message = body.get("message", {})
    event_type = message.get("type", "")
    handler = _HANDLERS.get(event_type)
    if handler:
        handler(message, time.monotonic())
    elif event_type and event_type != "end-of-call-report":
        call_id = _get_call_id(message)
        tracker = _get_tracker(call_id)
        delta = tracker.touch(time.monotonic())
        logger.info(
            "event | call_id='%s' | type='%s' | delta_ms=%s",
            call_id,
            event_type,
            delta if delta is not None else "n/a",
        )


def finalize_call(call_id: str) -> str:
    tracker = _trackers.pop(call_id, None)
    if tracker is None:
        summary = (
            f"call_summary | call_id='{call_id}' | barge_ins=0 | "
            f"double_speaks=0 | avg_response_ms=n/a | turns=0"
        )
        logger.info(summary)
        return summary

    avg_ms = "n/a"
    if tracker.response_latencies_ms:
        avg_ms = str(
            int(sum(tracker.response_latencies_ms) / len(tracker.response_latencies_ms))
        )

    summary = (
        f"call_summary | call_id='{call_id}' | barge_ins={tracker.barge_in_count} | "
        f"double_speaks={tracker.double_speak_count} | "
        f"avg_response_ms={avg_ms} | turns={tracker.turn_count}"
    )
    logger.info(summary)
    return summary


def reset_trackers() -> None:
    _trackers.clear()
