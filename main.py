import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("vapi_webhook")

TRANSCRIPTS_DIR = Path("transcripts")

app = FastAPI(title="Vapi Webhook Receiver")


def _ensure_transcripts_dir() -> None:
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)


def _save_transcript(call_id: str, duration_seconds: float, transcript: str) -> Path:
    _ensure_transcripts_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = TRANSCRIPTS_DIR / f"{timestamp}_{call_id}.json"
    payload = {
        "call_id": call_id,
        "duration_seconds": duration_seconds,
        "transcript": transcript,
        "saved_at": timestamp,
    }
    filename.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Transcript saved | file='%s'", filename)
    return filename


def _parse_end_of_call_report(body: dict) -> tuple[str, float, str]:
    call_id: str = body.get("call", {}).get("id", "unknown")
    duration: float = body.get("durationSeconds", 0.0)
    transcript: str = body.get("transcript", "")
    return call_id, duration, transcript


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
    call_id, duration, transcript = _parse_end_of_call_report(message)

    logger.info(
        "Processing end-of-call-report | call_id='%s' | duration=%.2fs | "
        "transcript_length=%d chars",
        call_id,
        duration,
        len(transcript),
    )

    try:
        saved_path = _save_transcript(call_id, duration, transcript)
    except OSError as e:
        logger.error("Failed to write transcript to disk: %s", e)
        raise HTTPException(status_code=500, detail="Transcript write failure")

    return JSONResponse(
        content={
            "status": "ok",
            "call_id": call_id,
            "transcript_file": str(saved_path),
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "healthy"})
