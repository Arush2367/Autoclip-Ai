"""Local credential connection and user-approved Meta Reels publishing."""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr, field_validator

from backend.config import CLIPS_DIR
from backend.database.database import database_connection
from backend.services import meta_publisher
from backend.services.meta_publisher import MetaPublisherError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/meta", tags=["meta-publishing"])
meta_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="autoclips-meta")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _update_connection(platform: str, *, connected: bool, account_id: str | None = None,
                       account_name: str | None = None, error: str | None = None) -> None:
    status = "CONNECTED" if connected else "NOT_CONNECTED"
    with database_connection() as connection:
        connection.execute(
            """INSERT INTO meta_connections
               (platform, status, account_id, account_name, token_expires_at,
                last_checked_at, last_error, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
               ON CONFLICT(platform) DO UPDATE SET
                 status=excluded.status, account_id=excluded.account_id,
                 account_name=excluded.account_name, token_expires_at=NULL,
                 last_checked_at=excluded.last_checked_at, last_error=excluded.last_error,
                 updated_at=excluded.updated_at""",
            (platform, status, account_id, account_name, _now(), error, _now(), _now()),
        )


def _get_clip(clip_id: str):
    with database_connection() as connection:
        clip = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Generated clip not found.")
        if clip["status"] != "COMPLETED":
            raise HTTPException(status_code=409, detail="Only completed clips can be published.")
        source = connection.execute(
            "SELECT rights_confirmed FROM sources WHERE id = ?", (clip["source_id"],)
        ).fetchone()
    if not source or not bool(source["rights_confirmed"]):
        raise HTTPException(status_code=403, detail="The source video does not have a valid rights confirmation.")
    path = Path(clip["storage_path"]).resolve()
    if CLIPS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Generated MP4 is missing or outside clip storage.")
    return clip, path


class MetaConnectRequest(BaseModel):
    # Credentials are posted only to the user's local AutoClips server and are
    # saved under storage/secrets. They are never echoed in an API response.
    instagram_access_token: SecretStr | None = None
    facebook_page_access_token: SecretStr | None = None
    preferred_instagram_account_id: str | None = Field(default=None, max_length=100)

    @field_validator("instagram_access_token", "facebook_page_access_token", mode="before")
    @classmethod
    def trim_secret(cls, value):
        return value.strip() if isinstance(value, str) else value


class MetaPublishRequest(BaseModel):
    platforms: list[Literal["instagram", "facebook"]] = Field(min_length=1, max_length=2)
    caption: str = Field(default="", max_length=2200)
    rights_confirmed: bool
    guidelines_confirmed: bool
    consent_to_publish: bool
    is_ai_generated: bool = False
    confirm_retry_after_check: bool = False

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Select each platform only once.")
        return value


def _serialize_publication(row) -> dict:
    item = dict(row)
    item.pop("rights_confirmed", None)
    item.pop("guidelines_confirmed", None)
    item.pop("user_approved", None)
    return item


def get_meta_status() -> dict:
    auth = meta_publisher.load_auth_data()
    metadata = meta_publisher.safe_connection_metadata(auth)
    with database_connection() as connection:
        saved = {
            row["platform"]: dict(row)
            for row in connection.execute("SELECT * FROM meta_connections").fetchall()
        }

    platforms = {}
    for platform, label, description in (
        ("instagram", "Instagram Reels", "Instagram Professional account via Unified Login (SUAT)"),
        ("facebook", "Facebook Reels", "Facebook Page via a separate Page access token"),
    ):
        item = metadata[platform]
        connected = bool(item["connected"])
        row = saved.get(platform, {})
        platforms[platform] = {
            "name": label,
            "destination": description,
            "status": "CONNECTED" if connected else "NOT_CONNECTED",
            "connected": connected,
            "account_id": item.get("account_id"),
            "account_name": item.get("account_name"),
            "last_error": row.get("last_error"),
        }

    publishing_enabled = any(item["connected"] for item in platforms.values())
    instagram_connected = platforms["instagram"]["connected"]
    facebook_connected = platforms["facebook"]["connected"]
    if instagram_connected and facebook_connected:
        message = "Instagram and Facebook are connected. Review each clip and explicitly approve the destinations before publishing."
    elif instagram_connected:
        message = "Instagram is connected. Facebook Reels needs a separate Facebook Page access token; you can add it later."
    elif facebook_connected:
        message = "Facebook is connected. Add your Instagram Unified Login token to enable Instagram Reels."
    else:
        message = "Enter the Instagram Unified Login test access token. A Facebook Page access token is optional and can be connected separately."

    return {
        "integration_ready": True,
        "connection_flow_implemented": True,
        "publishing_enabled": publishing_enabled,
        "credentials": {
            "instagram_token_saved": instagram_connected,
            "facebook_page_token_saved": facebook_connected,
            "token_storage": "local storage/secrets/meta_auth.json",
        },
        "platforms": platforms,
        "message": message,
    }


@router.get("/status")
def meta_status():
    try:
        return get_meta_status()
    except MetaPublisherError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/connect")
def connect_meta(payload: MetaConnectRequest):
    instagram_token = (payload.instagram_access_token.get_secret_value()
                       if payload.instagram_access_token else None)
    facebook_token = (payload.facebook_page_access_token.get_secret_value()
                      if payload.facebook_page_access_token else None)
    if any(token and len(token) > 20000 for token in (instagram_token, facebook_token)):
        raise HTTPException(status_code=413, detail="A Meta access token exceeded the supported length.")
    try:
        result = meta_publisher.connect_with_tokens(
            instagram_access_token=instagram_token,
            facebook_page_access_token=facebook_token,
            preferred_instagram_account_id=payload.preferred_instagram_account_id,
        )
        _update_connection(
            "instagram", connected=result["instagram"]["connected"],
            account_id=result["instagram"].get("account_id"),
            account_name=result["instagram"].get("account_name"),
        )
        _update_connection(
            "facebook", connected=result["facebook"]["connected"],
            account_id=result["facebook"].get("account_id"),
            account_name=result["facebook"].get("account_name"),
        )
        return {"message": "Meta credentials validated and saved locally.", "status": get_meta_status()}
    except MetaPublisherError as exc:
        # Never log or echo credentials. MetaPublisherError messages are sanitized.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/disconnect")
def disconnect_meta():
    meta_publisher.delete_auth_data()
    with database_connection() as connection:
        connection.execute(
            """UPDATE meta_connections SET status='NOT_CONNECTED', account_id=NULL,
               account_name=NULL, token_expires_at=NULL, last_checked_at=?, last_error=NULL,
               updated_at=?""", (_now(), _now())
        )
    return {"connected": False, "message": "Local Meta credentials were removed. Previously published Reels were not deleted."}


def _get_publication(publication_id: str):
    with database_connection() as connection:
        return connection.execute("SELECT * FROM meta_publications WHERE id = ?", (publication_id,)).fetchone()


def _update_publication(publication_id: str, **fields) -> None:
    allowed = {"status", "progress", "published_media_id", "published_url", "error_message"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [publication_id]
    with database_connection() as connection:
        connection.execute(f"UPDATE meta_publications SET {assignments} WHERE id = ?", values)


def _run_meta_publication(publication_id: str) -> None:
    row = _get_publication(publication_id)
    if not row or row["status"] != "QUEUED":
        return
    try:
        clip, path = _get_clip(row["clip_id"])
        _update_publication(publication_id, status="UPLOADING", progress=5, error_message=None)
        result = meta_publisher.publish_clip(
            platform=row["platform"], video_path=path, caption=row["caption"],
            title=clip["title"], is_ai_generated=bool(row["is_ai_generated"]),
            progress=lambda value: _update_publication(publication_id, progress=value),
        )
        _update_publication(
            publication_id, status="COMPLETED", progress=100,
            published_media_id=result.get("media_id"), published_url=result.get("url"), error_message=None,
        )
    except HTTPException as exc:
        _update_publication(publication_id, status="FAILED", error_message=str(exc.detail)[:800])
    except Exception as exc:
        logger.exception("Meta publication %s failed", publication_id)
        safe_message = str(exc).replace("\n", " ").strip()[:800]
        _update_publication(publication_id, status="FAILED", error_message=safe_message or "Meta publishing failed. Check backend logs.")


@router.post("/clips/{clip_id}/publish", status_code=202)
def publish_meta_clip(clip_id: str, payload: MetaPublishRequest):
    if not (payload.rights_confirmed and payload.guidelines_confirmed and payload.consent_to_publish):
        raise HTTPException(status_code=400, detail="Confirm content rights, platform rules, and explicit approval for this exact clip.")
    clip, path = _get_clip(clip_id)
    if path.stat().st_size <= 0:
        raise HTTPException(status_code=422, detail="The generated clip file is empty.")
    status = get_meta_status()
    for platform in payload.platforms:
        if not status["platforms"][platform]["connected"]:
            raise HTTPException(status_code=409, detail=f"{platform.title()} is not connected. Add its Meta access token first.")
        if platform == "instagram" and path.stat().st_size > 300 * 1024 * 1024:
            raise HTTPException(status_code=422, detail="Instagram Reels API requires the video file to be 300 MB or smaller.")

    publication_ids: list[str] = []
    with database_connection() as connection:
        for platform in payload.platforms:
            existing = connection.execute(
                "SELECT * FROM meta_publications WHERE clip_id = ? AND platform = ?",
                (clip_id, platform),
            ).fetchone()
            if existing:
                if existing["status"] == "COMPLETED":
                    raise HTTPException(status_code=409, detail=f"This clip is already published to {platform.title()}.")
                if existing["status"] in {"QUEUED", "UPLOADING", "PROCESSING"}:
                    raise HTTPException(status_code=409, detail=f"This clip is already being published to {platform.title()}.")
                if not payload.confirm_retry_after_check:
                    raise HTTPException(status_code=409, detail=f"Previous {platform.title()} attempt did not finish cleanly. Check the destination first, then confirm retry.")
        now = _now()
        for platform in payload.platforms:
            existing = connection.execute(
                "SELECT id FROM meta_publications WHERE clip_id = ? AND platform = ?",
                (clip_id, platform),
            ).fetchone()
            if existing:
                publication_id = existing["id"]
                connection.execute(
                    """UPDATE meta_publications SET status='QUEUED', progress=0, caption=?,
                       is_ai_generated=?, rights_confirmed=1, guidelines_confirmed=1,
                       user_approved=1, published_media_id=NULL, published_url=NULL,
                       error_message=NULL, updated_at=? WHERE id=?""",
                    (payload.caption, int(payload.is_ai_generated), now, publication_id),
                )
            else:
                publication_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO meta_publications (
                       id, clip_id, platform, status, progress, caption, is_ai_generated,
                       rights_confirmed, guidelines_confirmed, user_approved, created_at, updated_at
                       ) VALUES (?, ?, ?, 'QUEUED', 0, ?, ?, 1, 1, 1, ?, ?)""",
                    (publication_id, clip_id, platform, payload.caption, int(payload.is_ai_generated), now, now),
                )
            publication_ids.append(publication_id)
    for publication_id in publication_ids:
        meta_executor.submit(_run_meta_publication, publication_id)
    return {"message": "Meta publishing was queued. Keep AutoClips AI running until the status becomes COMPLETED or FAILED.", "publication_ids": publication_ids}


@router.get("/clips/{clip_id}/publications")
def get_meta_clip_publications(clip_id: str):
    with database_connection() as connection:
        clip = connection.execute("SELECT id FROM clips WHERE id = ?", (clip_id,)).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Generated clip not found.")
        rows = connection.execute(
            "SELECT * FROM meta_publications WHERE clip_id = ? ORDER BY platform", (clip_id,)
        ).fetchall()
    return {"clip_id": clip_id, "items": [_serialize_publication(row) for row in rows], "count": len(rows)}
