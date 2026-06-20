import logging
from datetime import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("vapi_webhook")

TRANSCRIPTS_DIR = Path("transcripts")
RECORDINGS_DIR = Path("recordings")

app = FastAPI(title="Vapi Webhook Receiver")


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _ensure_output_dirs() -> None:
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    RECORDINGS_DIR.mkdir(exist_ok=True)


def _extract_recording_url(artifact: dict) -> str | None:
    recording = artifact.get("recording")
    if isinstance(recording, dict):
        for key in ("monoUrl", "url", "recordingUrl"):
            url = recording.get(key)
            if url:
                return url
    elif isinstance(recording, str) and recording:
        return recording

    for key in ("recordingUrl", "stereoRecordingUrl"):
        url = artifact.get(key)
        if url:
            return url

    return None


def _save_transcript(
    call_id: str,
    duration_seconds: float,
    transcript: str,
    recording_file: str | None = None,
) -> Path:
    _ensure_output_dirs()
    timestamp = _timestamp()
    filename = TRANSCRIPTS_DIR / f"{timestamp}_{call_id}.md"

    content = (
        f"# Call Report: {call_id}\n\n"
        f"## Metrics\n"
        f"- **Call Duration:** {duration_seconds:.2f}s\n"
        f"- **Recording:** {recording_file or 'N/A'}\n"
        f"- **Saved At:** {timestamp}\n\n"
        f"## Transcript\n\n"
        f"{transcript}\n"
    )

    filename.write_text(content, encoding="utf-8")
    logger.info("Transcript saved | file='%s'", filename)
    return filename


def _save_recording(call_id: str, recording_url: str) -> Path:
    _ensure_output_dirs()
    timestamp = _timestamp()
    filename = RECORDINGS_DIR / f"{timestamp}_{call_id}.mp3"

    response = requests.get(recording_url, timeout=60)
    response.raise_for_status()
    filename.write_bytes(response.content)
    logger.info("Recording saved | file='%s' | bytes=%d", filename, len(response.content))
    return filename


def _parse_end_of_call_report(message: dict) -> tuple[str, float, str, dict]:
    call_id: str = message.get("call", {}).get("id", "unknown")
    duration: float = message.get("durationSeconds", 0.0)
    transcript: str = message.get("transcript", "")
    artifact: dict = message.get("artifact", {})
    return call_id, duration, transcript, artifact


@app.post("/vapi-webhook")
async def vapi_webhook(request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook payload as JSON: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type: str = body.get("message", {}).get("type", "")
    logger.info("Received webhook event | type='%s'", event_type)

    if event_type != "end-of-call-report":
        logger.info("Ignoring non-terminal event type: '%s'", event_type)
        return JSONResponse(content={"status": "ignored", "event_type": event_type})

    message: dict = body.get("message", {})
    call_id, duration, transcript, artifact = _parse_end_of_call_report(message)

    logger.info(
        "Processing end-of-call-report | call_id='%s' | duration=%.2fs | "
        "transcript_length=%d chars",
        call_id,
        duration,
        len(transcript),
    )

    recording_path: Path | None = None
    recording_url = _extract_recording_url(artifact)
    if recording_url:
        try:
            recording_path = _save_recording(call_id, recording_url)
        except requests.RequestException as e:
            logger.error("Failed to download recording for call '%s': %s", call_id, e)
        except OSError as e:
            logger.error("Failed to write recording to disk: %s", e)
    else:
        logger.warning("No recording URL in end-of-call-report for call '%s'", call_id)

    try:
        saved_path = _save_transcript(
            call_id,
            duration,
            transcript,
            recording_file=str(recording_path) if recording_path else None,
        )
    except OSError as e:
        logger.error("Failed to write transcript to disk: %s", e)
        raise HTTPException(status_code=500, detail="Transcript write failure")

    return JSONResponse(
        content={
            "status": "ok",
            "call_id": call_id,
            "transcript_file": str(saved_path),
            "recording_file": str(recording_path) if recording_path else None,
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "healthy"})
