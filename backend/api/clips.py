"""Queue, monitor and retrieve rendered highlight clips."""

from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.config import CLIPS_DIR, ORIGINALS_DIR, TEMP_DIR
from backend.database.database import database_connection
from backend.services.clip_renderer import render_clip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["clips"])
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autoclips-render")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _serialize_clip(row) -> dict[str, Any]:
    item = dict(row)
    item.pop("storage_path", None)
    item["preview_url"] = f"/api/v1/clips/{item['id']}/file"
    item["download_url"] = f"/api/v1/clips/{item['id']}/download"
    return item


def _update_clip(clip_id: str, **fields: Any) -> None:
    allowed = {
        "status", "width", "height", "video_codec", "subtitle_status", "error_message",
        "duration_seconds", "updated_at",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [clip_id]
    with database_connection() as connection:
        connection.execute(f"UPDATE clips SET {assignments} WHERE id = ?", values)


def _run_render_batch(analysis_id: str) -> None:
    """Render every queued clip independently so one failed candidate does not stop the batch."""
    with database_connection() as connection:
        analysis = connection.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not analysis:
            return
        source = connection.execute("SELECT * FROM sources WHERE id = ?", (analysis["source_id"],)).fetchone()
        rows = connection.execute(
            "SELECT * FROM clips WHERE analysis_id = ? AND status = 'QUEUED' ORDER BY start_seconds ASC",
            (analysis_id,),
        ).fetchall()
    if not source:
        for row in rows:
            _update_clip(row["id"], status="FAILED", error_message="The source record no longer exists.")
        return

    source_path = Path(source["storage_path"]).resolve()
    originals_root = ORIGINALS_DIR.resolve()
    if originals_root not in source_path.parents or not source_path.is_file():
        for row in rows:
            _update_clip(row["id"], status="FAILED", error_message="The original source file is missing or outside source storage.")
        return
    if not bool(source["rights_confirmed"]):
        for row in rows:
            _update_clip(row["id"], status="FAILED", error_message="The source does not have a valid rights confirmation.")
        return

    try:
        analysis_result = json.loads(analysis["result_json"] or "{}")
        transcript_segments = analysis_result.get("transcript", {}).get("segments", [])
    except (TypeError, json.JSONDecodeError):
        transcript_segments = []

    for row in rows:
        clip_id = row["id"]
        output_path = Path(row["storage_path"]).resolve()
        clips_root = CLIPS_DIR.resolve()
        if clips_root not in output_path.parents:
            _update_clip(clip_id, status="FAILED", error_message="The generated output path is outside clip storage.")
            continue
        _update_clip(clip_id, status="RENDERING", error_message=None)
        try:
            result = render_clip(
                source_path=source_path,
                output_path=output_path,
                temp_dir=TEMP_DIR,
                clip_id=clip_id,
                clip_start=float(row["start_seconds"]),
                clip_end=float(row["end_seconds"]),
                transcript_segments=transcript_segments,
            )
            metadata = result["metadata"]
            _update_clip(
                clip_id,
                status="COMPLETED",
                duration_seconds=metadata["duration_seconds"],
                width=metadata["width"],
                height=metadata["height"],
                video_codec=metadata["video_codec"],
                subtitle_status=result["subtitle_status"],
                error_message=None,
            )
        except Exception as exc:
            logger.exception("Clip render %s failed", clip_id)
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove incomplete clip file %s", output_path)
            _update_clip(clip_id, status="FAILED", error_message=str(exc)[:1200])


@router.post("/analysis/{analysis_id}/render", status_code=202)
def start_render(analysis_id: str):
    with database_connection() as connection:
        analysis = connection.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis job not found.")
        if analysis["status"] != "COMPLETED" or not analysis["result_json"]:
            raise HTTPException(status_code=409, detail="Wait for a completed analysis before rendering clips.")
        source = connection.execute("SELECT * FROM sources WHERE id = ?", (analysis["source_id"],)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="Source video not found.")
        if not bool(source["rights_confirmed"]):
            raise HTTPException(status_code=403, detail="This source does not have a rights confirmation.")

        try:
            result = json.loads(analysis["result_json"])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="The saved analysis result is invalid JSON.") from exc
        candidates = result.get("highlights", {}).get("items", [])
        if not candidates:
            raise HTTPException(status_code=400, detail="No eligible highlight candidates are available to render.")

        existing = connection.execute(
            "SELECT * FROM clips WHERE analysis_id = ? ORDER BY start_seconds ASC",
            (analysis_id,),
        ).fetchall()
        if existing:
            failed = [item for item in existing if item["status"] == "FAILED"]
            if failed:
                for item in failed:
                    connection.execute(
                        "UPDATE clips SET status = 'QUEUED', error_message = NULL, updated_at = ? WHERE id = ?",
                        (_now(), item["id"]),
                    )
                queued = True
            else:
                return {
                    "message": "This analysis already has generated or queued clips.",
                    "clips": [_serialize_clip(item) for item in existing],
                }
        else:
            source_duration = float(source["duration_seconds"] or result.get("metadata", {}).get("duration_seconds") or 0)
            normalized: list[dict[str, Any]] = []
            for candidate in candidates:
                try:
                    start = float(candidate["start"])
                    end = float(candidate["end"])
                except (KeyError, TypeError, ValueError):
                    raise HTTPException(status_code=422, detail="A highlight candidate has invalid timestamps.")
                duration = end - start
                if start < 0 or end > source_duration + 0.25 or duration < 30.0 or duration > 40.0:
                    raise HTTPException(status_code=422, detail="A highlight candidate falls outside the source duration or 30-40 second limit.")
                normalized.append({
                    "start": start,
                    "end": end,
                    "duration": duration,
                    "title": str(candidate.get("title") or "Untitled highlight")[:120],
                    "score": max(0, min(100, int(candidate.get("score", 0)))),
                })
            normalized.sort(key=lambda item: item["start"])
            for previous, current in zip(normalized, normalized[1:]):
                if current["start"] < previous["end"]:
                    raise HTTPException(status_code=422, detail="Selected highlights overlap. Re-run the highlight selector before rendering.")

            now = _now()
            for candidate in normalized:
                clip_id = str(uuid.uuid4())
                filename = f"{clip_id}.mp4"
                output_path = CLIPS_DIR / filename
                connection.execute(
                    """INSERT INTO clips (
                        id, source_id, analysis_id, title, start_seconds, end_seconds, duration_seconds,
                        score, status, output_filename, storage_path, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?)""",
                    (
                        clip_id, source["id"], analysis_id, candidate["title"], candidate["start"],
                        candidate["end"], candidate["duration"], candidate["score"], filename,
                        str(output_path), now, now,
                    ),
                )
            queued = True

        clip_rows = connection.execute(
            "SELECT * FROM clips WHERE analysis_id = ? ORDER BY start_seconds ASC", (analysis_id,)
        ).fetchall()

    if queued:
        executor.submit(_run_render_batch, analysis_id)
    return {
        "message": "Clip rendering has been queued.",
        "clips": [_serialize_clip(item) for item in clip_rows],
    }


@router.get("/analysis/{analysis_id}/clips")
def list_analysis_clips(analysis_id: str):
    with database_connection() as connection:
        analysis = connection.execute("SELECT id FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis job not found.")
        rows = connection.execute(
            "SELECT * FROM clips WHERE analysis_id = ? ORDER BY start_seconds ASC", (analysis_id,)
        ).fetchall()
    return {"items": [_serialize_clip(row) for row in rows], "count": len(rows)}


def _get_completed_clip(clip_id: str):
    with database_connection() as connection:
        row = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Generated clip not found.")
    if row["status"] != "COMPLETED":
        raise HTTPException(status_code=409, detail="This clip is not ready yet.")
    path = Path(row["storage_path"]).resolve()
    if CLIPS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Generated clip file is missing.")
    return row, path


@router.get("/clips/{clip_id}/file")
def preview_clip(clip_id: str):
    row, path = _get_completed_clip(clip_id)
    return FileResponse(path, media_type="video/mp4", filename=row["output_filename"], content_disposition_type="inline")


@router.get("/clips/{clip_id}/download")
def download_clip(clip_id: str):
    row, path = _get_completed_clip(clip_id)
    return FileResponse(path, media_type="video/mp4", filename=row["output_filename"], content_disposition_type="attachment")
