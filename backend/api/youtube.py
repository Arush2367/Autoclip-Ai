"""Explicitly authorized YouTube upload endpoints."""

from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.config import CLIPS_DIR
from backend.database.database import database_connection
from backend.services import youtube_publisher
from backend.services.youtube_publisher import YouTubePublisherError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["youtube"])
upload_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autoclips-youtube")


class YouTubeUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: str = Field(default="", max_length=500)
    privacy_status: Literal["private", "unlisted", "public"]
    made_for_kids: bool
    contains_synthetic_media: bool | None = None
    rights_confirmed: bool
    guidelines_confirmed: bool
    consent_to_upload: bool
    confirm_retry_after_check: bool = False

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("YouTube title cannot be blank.")
        return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _serialize(row) -> dict:
    item = dict(row)
    item.pop("rights_confirmed", None)
    item.pop("guidelines_confirmed", None)
    item.pop("user_approved", None)
    tags_json = item.pop("tags_json", "[]")
    item["tags"] = json.loads(tags_json or "[]")
    return item


def _get_publication(publication_id: str):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM youtube_publications WHERE id = ?", (publication_id,)
        ).fetchone()
    return row


def _update_publication(publication_id: str, **fields) -> None:
    allowed = {
        "status", "progress", "youtube_video_id", "youtube_url", "error_message", "updated_at"
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    updates["updated_at"] = _now()
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [publication_id]
    with database_connection() as connection:
        connection.execute(
            f"UPDATE youtube_publications SET {assignments} WHERE id = ?", values
        )


def _run_upload(publication_id: str) -> None:
    row = _get_publication(publication_id)
    if not row or row["status"] != "QUEUED":
        return

    with database_connection() as connection:
        clip = connection.execute(
            "SELECT * FROM clips WHERE id = ?", (row["clip_id"],)
        ).fetchone()
        source = connection.execute(
            "SELECT s.* FROM sources s JOIN clips c ON c.source_id = s.id WHERE c.id = ?",
            (row["clip_id"],),
        ).fetchone()

    if not clip or clip["status"] != "COMPLETED":
        _update_publication(publication_id, status="FAILED", error_message="The generated clip is not available.")
        return
    if not source or not bool(source["rights_confirmed"]):
        _update_publication(publication_id, status="FAILED", error_message="The source is missing its rights confirmation.")
        return

    path = Path(clip["storage_path"]).resolve()
    if CLIPS_DIR.resolve() not in path.parents or not path.is_file():
        _update_publication(publication_id, status="FAILED", error_message="The generated MP4 is missing or outside clip storage.")
        return

    _update_publication(publication_id, status="UPLOADING", progress=0, error_message=None)
    try:
        tags = json.loads(row["tags_json"] or "[]")
        result = youtube_publisher.upload_video(
            video_path=path,
            title=row["title"],
            description=row["description"],
            tags=tags,
            privacy_status=row["privacy_status"],
            made_for_kids=bool(row["made_for_kids"]),
            contains_synthetic_media=(
                None if row["contains_synthetic_media"] is None
                else bool(row["contains_synthetic_media"])
            ),
            progress_callback=lambda value: _update_publication(
                publication_id, progress=value
            ),
        )
        video_id = result["id"]
        _update_publication(
            publication_id,
            status="COMPLETED",
            progress=100,
            youtube_video_id=video_id,
            youtube_url=f"https://www.youtube.com/watch?v={video_id}",
            error_message=None,
        )
    except Exception as exc:
        logger.exception("YouTube upload %s failed", publication_id)
        # No automatic retry: the user must inspect YouTube Studio before another attempt.
        safe_message = str(exc).replace("\n", " ").strip()[:1000]
        if not safe_message:
            safe_message = "YouTube upload failed. Check the backend terminal for details."
        _update_publication(publication_id, status="FAILED", error_message=safe_message)


@router.get("/youtube/status")
def get_youtube_status():
    return youtube_publisher.connection_status()


@router.post("/youtube/connect")
def connect_youtube():
    try:
        channel = youtube_publisher.connect_youtube()
    except YouTubePublisherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected YouTube OAuth error")
        raise HTTPException(status_code=500, detail="YouTube authorization failed. Check the backend terminal.") from exc
    return {
        "connected": True,
        "channel_id": channel.get("id"),
        "channel_title": channel.get("title"),
        "message": "YouTube authorization completed.",
    }


@router.post("/youtube/disconnect")
def disconnect_youtube():
    try:
        youtube_publisher.disconnect_youtube()
    except YouTubePublisherError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"connected": False, "message": "The local YouTube token was removed. This did not delete uploaded videos."}


@router.post("/clips/{clip_id}/youtube-upload", status_code=202)
def start_youtube_upload(clip_id: str, payload: YouTubeUploadRequest):
    if not (payload.rights_confirmed and payload.guidelines_confirmed and payload.consent_to_upload):
        raise HTTPException(
            status_code=400,
            detail="Confirm content rights, YouTube Community Guidelines, and approval for this specific upload.",
        )
    status = youtube_publisher.connection_status()
    if not status["connected"]:
        raise HTTPException(status_code=401, detail="Connect YouTube before uploading.")
    try:
        tags = youtube_publisher.parse_tags(payload.tags)
        youtube_publisher.build_video_body(
            title=payload.title,
            description=payload.description,
            tags=tags,
            privacy_status=payload.privacy_status,
            made_for_kids=payload.made_for_kids,
            contains_synthetic_media=payload.contains_synthetic_media,
        )
    except YouTubePublisherError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with database_connection() as connection:
        clip = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Generated clip not found.")
        if clip["status"] != "COMPLETED":
            raise HTTPException(status_code=409, detail="Only completed MP4 clips can be uploaded.")
        source = connection.execute(
            "SELECT rights_confirmed FROM sources WHERE id = ?", (clip["source_id"],)
        ).fetchone()
        if not source or not bool(source["rights_confirmed"]):
            raise HTTPException(status_code=403, detail="The source is not cleared for republishing.")

        existing = connection.execute(
            "SELECT * FROM youtube_publications WHERE clip_id = ?", (clip_id,)
        ).fetchone()
        if existing:
            if existing["status"] == "COMPLETED":
                return {"message": "This clip has already been uploaded to YouTube.", "publication": _serialize(existing)}
            if existing["status"] in {"QUEUED", "UPLOADING"}:
                return {"message": "This clip is already being uploaded.", "publication": _serialize(existing)}
            if not payload.confirm_retry_after_check:
                raise HTTPException(
                    status_code=409,
                    detail="A previous upload attempt did not finish cleanly. Check YouTube Studio first, then confirm that it was not uploaded before retrying.",
                )
            publication_id = existing["id"]
            connection.execute(
                """UPDATE youtube_publications SET status = 'QUEUED', progress = 0,
                   title = ?, description = ?, tags_json = ?, privacy_status = ?, made_for_kids = ?,
                   contains_synthetic_media = ?, rights_confirmed = 1,
                   guidelines_confirmed = 1, user_approved = 1,
                   youtube_video_id = NULL, youtube_url = NULL, error_message = NULL,
                   updated_at = ? WHERE id = ?""",
                (
                    payload.title, payload.description, json.dumps(tags), payload.privacy_status,
                    int(payload.made_for_kids),
                    None if payload.contains_synthetic_media is None else int(payload.contains_synthetic_media),
                    _now(), publication_id,
                ),
            )
        else:
            publication_id = str(uuid.uuid4())
            now = _now()
            connection.execute(
                """INSERT INTO youtube_publications (
                    id, clip_id, status, progress, title, description, tags_json,
                    privacy_status, made_for_kids, contains_synthetic_media, rights_confirmed,
                    guidelines_confirmed, user_approved, created_at, updated_at
                ) VALUES (?, ?, 'QUEUED', 0, ?, ?, ?, ?, ?, ?, 1, 1, 1, ?, ?)""",
                (
                    publication_id, clip_id, payload.title, payload.description,
                    json.dumps(tags), payload.privacy_status, int(payload.made_for_kids),
                    None if payload.contains_synthetic_media is None else int(payload.contains_synthetic_media),
                    now, now,
                ),
            )

    upload_executor.submit(_run_upload, publication_id)
    return {
        "message": "YouTube upload queued. Keep AutoClips AI running until it finishes.",
        "publication": {"id": publication_id, "clip_id": clip_id, "status": "QUEUED", "progress": 0},
    }


@router.get("/clips/{clip_id}/youtube-upload")
def get_youtube_upload(clip_id: str):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM youtube_publications WHERE clip_id = ?", (clip_id,)
        ).fetchone()
    return {"publication": _serialize(row) if row else None}
