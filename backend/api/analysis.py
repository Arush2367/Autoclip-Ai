"""API endpoints for starting and monitoring local AI video analysis."""

from __future__ import annotations

import importlib.util
import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.config import WHISPER_DEVICE, WHISPER_MODEL
from backend.database.database import database_connection
from backend.services.analysis_pipeline import run_analysis

router = APIRouter(prefix="/api/v1", tags=["analysis"])
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autoclips-analysis")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _serialize_analysis(row) -> dict:
    item = dict(row)
    result_json = item.pop("result_json", None)
    item["result"] = json.loads(result_json) if result_json else None
    return item


@router.get("/analysis/capabilities")
def analysis_capabilities():
    faster_whisper = importlib.util.find_spec("faster_whisper") is not None
    scenedetect = importlib.util.find_spec("scenedetect") is not None
    ffmpeg_available = shutil.which("ffmpeg") is not None
    ffprobe_available = shutil.which("ffprobe") is not None
    return {
        "ffmpeg_available": ffmpeg_available,
        "ffprobe_available": ffprobe_available,
        "faster_whisper_installed": faster_whisper,
        "scenedetect_installed": scenedetect,
        "whisper_model": WHISPER_MODEL,
        "device": WHISPER_DEVICE,
        "ready": all((ffmpeg_available, ffprobe_available, faster_whisper, scenedetect)),
        "model_download": "The selected Whisper model is downloaded once on the first analysis and cached under storage/models/.",
    }


@router.post("/sources/{source_id}/analyze", status_code=202)
def start_analysis(source_id: str):
    with database_connection() as connection:
        source = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="Source video not found.")
        if not bool(source["rights_confirmed"]):
            raise HTTPException(status_code=403, detail="This source does not have a rights confirmation.")

        active = connection.execute(
            "SELECT * FROM analyses WHERE source_id = ? AND status IN ('QUEUED', 'RUNNING') ORDER BY created_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        if active:
            return {"message": "An analysis is already queued or running.", "analysis": _serialize_analysis(active)}

        analysis_id = str(uuid.uuid4())
        now = _now()
        connection.execute(
            """INSERT INTO analyses (id, source_id, status, stage, progress, message, model_name, created_at, updated_at)
               VALUES (?, ?, 'QUEUED', 'queued', 0, ?, ?, ?, ?)""",
            (analysis_id, source_id, "Analysis is waiting for the local worker.", WHISPER_MODEL, now, now),
        )

    executor.submit(run_analysis, analysis_id)
    return {
        "message": "Analysis queued.",
        "analysis_id": analysis_id,
        "status": "QUEUED",
        "note": "The first run may take longer while the local Whisper model downloads.",
    }


@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str):
    with database_connection() as connection:
        row = connection.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return _serialize_analysis(row)


@router.get("/sources/{source_id}/analysis")
def get_latest_source_analysis(source_id: str):
    with database_connection() as connection:
        source = connection.execute("SELECT id FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="Source video not found.")
        row = connection.execute(
            "SELECT * FROM analyses WHERE source_id = ? ORDER BY created_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
    return {"analysis": _serialize_analysis(row) if row else None}
