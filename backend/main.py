"""AutoClips AI local development API."""

from __future__ import annotations

import shutil
from fastapi import FastAPI
from fastapi.responses import FileResponse

from backend.security import LocalOnlySecurityMiddleware

from backend.api.analysis import router as analysis_router
from backend.api.clips import router as clips_router
from backend.api.meta import router as meta_router
from backend.api.sources import router as sources_router
from backend.api.youtube import router as youtube_router
from backend.config import PROJECT_ROOT, STORAGE_ROOT, MAX_UPLOAD_MB
from backend.database.database import database_connection, initialize_database

app = FastAPI(
    title="AutoClips AI",
    version="0.6.1",
    description=(
        "Local-first video ingestion, AI analysis, vertical clip rendering, "
        "YouTube publishing, and Instagram/Facebook Reels publishing."
    ),
)

# This is a local desktop application, not an internet-facing service. Enforce
# loopback clients and same-origin browser requests even if Uvicorn is started
# manually with an unsafe --host value.
app.add_middleware(LocalOnlySecurityMiddleware)


@app.on_event("startup")
def startup() -> None:
    initialize_database()
    # Jobs interrupted by closing the local app are marked clearly; the user can retry them.
    with database_connection() as connection:
        connection.execute(
            """UPDATE analyses SET status = 'INTERRUPTED', stage = 'interrupted',
               message = 'The app stopped before this analysis finished. Start it again to retry.',
               updated_at = datetime('now')
               WHERE status IN ('QUEUED', 'RUNNING')"""
        )
        connection.execute(
            """UPDATE clips SET status = 'FAILED',
               error_message = 'The app stopped before rendering finished. Press Generate vertical clips to retry.',
               updated_at = datetime('now')
               WHERE status IN ('QUEUED', 'RENDERING')"""
        )
        connection.execute(
            """UPDATE youtube_publications SET status = 'INTERRUPTED',
               error_message = 'The app stopped during upload. Check YouTube Studio before retrying to avoid duplicates.',
               updated_at = datetime('now')
               WHERE status IN ('QUEUED', 'UPLOADING')"""
        )
        connection.execute(
            """UPDATE meta_publications SET status = 'INTERRUPTED',
               error_message = 'The app stopped during Meta publishing. Check the destination before retrying.',
               updated_at = datetime('now')
               WHERE status IN ('QUEUED', 'UPLOADING', 'PROCESSING')"""
        )


@app.get("/api/v1/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "app": "AutoClips AI",
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "ffprobe_available": shutil.which("ffprobe") is not None,
        "max_upload_mb": MAX_UPLOAD_MB,
        "storage_directory_exists": STORAGE_ROOT.exists(),
    }


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(PROJECT_ROOT / "frontend" / "index.html")


@app.get("/style.css", include_in_schema=False)
def stylesheet():
    return FileResponse(PROJECT_ROOT / "frontend" / "style.css", media_type="text/css")


@app.get("/meta-publishing.css", include_in_schema=False)
def meta_stylesheet():
    return FileResponse(
        PROJECT_ROOT / "frontend" / "meta-publishing.css", media_type="text/css"
    )


@app.get("/app.js", include_in_schema=False)
def javascript():
    return FileResponse(PROJECT_ROOT / "frontend" / "app.js", media_type="application/javascript")


@app.get("/meta-publishing.js", include_in_schema=False)
def meta_javascript():
    return FileResponse(
        PROJECT_ROOT / "frontend" / "meta-publishing.js",
        media_type="application/javascript",
    )


app.include_router(sources_router)
app.include_router(analysis_router)
app.include_router(clips_router)
app.include_router(youtube_router)
app.include_router(meta_router)
