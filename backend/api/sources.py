"""Source upload and listing endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    ORIGINALS_DIR,
    TEMP_DIR,
    UPLOAD_CHUNK_BYTES,
)
from backend.database.database import database_connection
from backend.services.ingestion import (
    get_extension,
    probe_video,
    safe_display_filename,
    sha256_file,
    signature_matches,
)

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def serialize_source(row) -> dict:
    data = dict(row)
    data.pop("storage_path", None)
    data["rights_confirmed"] = bool(data["rights_confirmed"])
    return data


@router.post("/upload", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
):
    """Stream an authorized source video to disk and record it in SQLite."""
    if not rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Please confirm that you own or are authorized to republish this video.",
        )

    original_filename = safe_display_filename(file.filename)
    extension = get_extension(original_filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    source_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    stored_filename = f"{source_id}{extension}"
    temporary_path = TEMP_DIR / f"{source_id}.uploading"
    final_path = ORIGINALS_DIR / stored_filename

    total_bytes = 0
    header = bytearray()
    import hashlib
    digest = hashlib.sha256()

    try:
        with temporary_path.open("wb") as output_file:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is too large. Maximum upload size is {MAX_UPLOAD_MB} MB.",
                    )

                if len(header) < 32:
                    header.extend(chunk[: 32 - len(header)])
                digest.update(chunk)
                output_file.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        if not signature_matches(extension, bytes(header)):
            raise HTTPException(
                status_code=415,
                detail="The file content does not match its extension or is not a supported video container.",
            )

        # Keep an independently generated checksum for later integrity checks.
        checksum = digest.hexdigest()
        temporary_path.replace(final_path)

        metadata = probe_video(final_path)
        validation_status = "verified" if metadata else "signature_only_ffprobe_missing"
        now = utc_now()

        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO sources (
                    id, original_filename, stored_filename, file_extension,
                    size_bytes, sha256, storage_path, source_type,
                    rights_confirmed, validation_status, duration_seconds,
                    width, height, video_codec, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'upload', 1, ?, ?, ?, ?, ?, 'UPLOADED', ?)
                """,
                (
                    source_id,
                    original_filename,
                    stored_filename,
                    extension,
                    total_bytes,
                    checksum,
                    str(final_path),
                    validation_status,
                    metadata.get("duration_seconds") if metadata else None,
                    metadata.get("width") if metadata else None,
                    metadata.get("height") if metadata else None,
                    metadata.get("video_codec") if metadata else None,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (id, source_id, job_type, status, created_at, updated_at)
                VALUES (?, ?, 'INGESTION', 'RECEIVED', ?, ?)
                """,
                (job_id, source_id, now, now),
            )

        return {
            "message": "Video uploaded and registered successfully.",
            "source_id": source_id,
            "job_id": job_id,
            "original_filename": original_filename,
            "size_bytes": total_bytes,
            "sha256": checksum,
            "validation_status": validation_status,
            "metadata": metadata,
            "next_step": "Install FFmpeg/FFprobe to verify the video stream before analysis." if not metadata else "Source is ready for the next processing milestone.",
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to store the uploaded file. Check available disk space.") from exc
    finally:
        await file.close()
        temporary_path.unlink(missing_ok=True)
        # If the database write failed after the file was moved, remove the orphan.
        # The path remains only when a matching source record was committed.
        if final_path.exists():
            try:
                with database_connection() as connection:
                    found = connection.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone()
                if not found:
                    final_path.unlink(missing_ok=True)
            except Exception:
                # Do not mask the original request error; an orphan can be cleaned manually.
                pass


@router.get("")
def list_sources(limit: int = 50):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    with database_connection() as connection:
        rows = connection.execute(
            """SELECT sources.*,
                      (SELECT id FROM analyses WHERE analyses.source_id = sources.id
                       ORDER BY created_at DESC LIMIT 1) AS latest_analysis_id,
                      (SELECT status FROM analyses WHERE analyses.source_id = sources.id
                       ORDER BY created_at DESC LIMIT 1) AS latest_analysis_status
               FROM sources ORDER BY sources.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return {"items": [serialize_source(row) for row in rows], "count": len(rows)}


@router.get("/{source_id}")
def get_source(source_id: str):
    with database_connection() as connection:
        row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    return serialize_source(row)
