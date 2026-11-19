"""Meta integration readiness and publication-history endpoints.

Account OAuth and publishing endpoints are intentionally deferred to the next
phase. These routes only expose local readiness and stored publication history.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.database.database import database_connection
from backend.services.meta_publisher import configuration_status, platform_definitions

router = APIRouter(prefix="/api/v1/meta", tags=["meta-publishing"])


def get_meta_status() -> dict:
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM meta_connections ORDER BY platform"
        ).fetchall()

    saved = {row["platform"]: dict(row) for row in rows}
    platforms = {}
    for platform, definition in platform_definitions().items():
        row = saved.get(platform, {})
        connected = row.get("status") == "CONNECTED"
        platforms[platform] = {
            **definition,
            "status": row.get("status", "NOT_CONNECTED"),
            "connected": connected,
            "account_id": row.get("account_id"),
            "account_name": row.get("account_name"),
            "token_expires_at": row.get("token_expires_at"),
            "last_checked_at": row.get("last_checked_at"),
            "last_error": row.get("last_error"),
        }

    return {
        "integration_ready": True,
        "connection_flow_implemented": False,
        "publishing_enabled": False,
        "credentials": configuration_status(),
        "platforms": platforms,
        "message": (
            "The app is prepared for Instagram and Facebook Reels integration. "
            "Meta account connection and publishing will be enabled in the next phase."
        ),
    }


@router.get("/status")
def meta_status():
    return get_meta_status()


@router.get("/clips/{clip_id}/publications")
def get_meta_clip_publications(clip_id: str):
    with database_connection() as connection:
        clip = connection.execute(
            "SELECT id FROM clips WHERE id = ?", (clip_id,)
        ).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Generated clip not found.")
        rows = connection.execute(
            "SELECT * FROM meta_publications WHERE clip_id = ? ORDER BY platform",
            (clip_id,),
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        # Consent evidence is retained locally but is not returned by the status API.
        item.pop("rights_confirmed", None)
        item.pop("guidelines_confirmed", None)
        item.pop("user_approved", None)
        items.append(item)
    return {"clip_id": clip_id, "items": items, "count": len(items)}
