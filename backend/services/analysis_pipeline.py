"""Background analysis pipeline for one stored source video."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import ORIGINALS_DIR, TEMP_DIR, WHISPER_MODEL
from backend.database.database import database_connection
from backend.services.highlight_selection import select_highlights
from backend.services.ingestion import probe_video
from backend.services.scene_detection import detect_scenes
from backend.services.transcription import transcribe_audio

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _update_analysis(analysis_id: str, **fields: Any) -> None:
    allowed = {"status", "stage", "progress", "message", "model_name", "language", "result_json", "error_message"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [analysis_id]
    with database_connection() as connection:
        connection.execute(f"UPDATE analyses SET {assignments} WHERE id = ?", values)


def _extract_audio(video_path: Path, audio_path: Path) -> bool:
    """Extract a compact mono audio track. Return False for a video with no audio."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and FFprobe must both be available on PATH before analysis.")

    audio_check = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if audio_check.returncode != 0:
        raise RuntimeError("FFprobe could not inspect the source audio stream.")
    if not (audio_check.stdout or "").strip():
        return False

    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path),
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k",
        str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60 * 30, check=False)
    if result.returncode != 0 or not audio_path.is_file() or audio_path.stat().st_size == 0:
        detail = (result.stderr or "FFmpeg did not produce an audio file.").strip()[-500:]
        raise RuntimeError(f"Audio extraction failed: {detail}")
    return True


def run_analysis(analysis_id: str) -> None:
    """Process a queued analysis. Errors are stored on its database record."""
    audio_path: Path | None = None
    try:
        with database_connection() as connection:
            analysis = connection.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            if not analysis:
                return
            source = connection.execute("SELECT * FROM sources WHERE id = ?", (analysis["source_id"],)).fetchone()
        if not source:
            raise RuntimeError("The source record no longer exists.")
        if not bool(source["rights_confirmed"]):
            raise RuntimeError("The source does not have a valid rights confirmation.")

        video_path = Path(source["storage_path"]).resolve()
        originals_root = ORIGINALS_DIR.resolve()
        if originals_root not in video_path.parents:
            raise RuntimeError("The stored source path is outside the approved originals folder.")
        if not video_path.is_file():
            raise FileNotFoundError("The stored source video could not be found.")

        _update_analysis(analysis_id, status="RUNNING", stage="validating", progress=5, message="Checking the stored video and refreshing its metadata.")
        metadata = probe_video(video_path)
        if metadata is None:
            raise RuntimeError("FFprobe is not available in this backend process. Restart the app after configuring PATH.")
        with database_connection() as connection:
            connection.execute(
                """UPDATE sources SET validation_status = 'verified', duration_seconds = ?, width = ?,
                   height = ?, video_codec = ?, error_message = NULL WHERE id = ?""",
                (metadata["duration_seconds"], metadata["width"], metadata["height"], metadata["video_codec"], source["id"]),
            )

        audio_path = TEMP_DIR / f"{source['id']}_{analysis_id}.mp3"
        _update_analysis(analysis_id, stage="extracting_audio", progress=15, message="Extracting a lightweight audio track.")
        has_audio = _extract_audio(video_path, audio_path)

        transcript: dict[str, Any]
        if has_audio:
            _update_analysis(analysis_id, stage="transcribing", progress=30, message=f"Running local Faster-Whisper ({WHISPER_MODEL}, CPU int8). First run downloads the model once.")
            transcript = transcribe_audio(audio_path)
        else:
            transcript = {"model": WHISPER_MODEL, "language": None, "language_probability": 0.0, "segments": []}

        _update_analysis(analysis_id, stage="scene_detection", progress=75, message="Detecting visual scene changes.")
        scenes = detect_scenes(video_path)

        _update_analysis(analysis_id, stage="highlight_selection", progress=90, message="Ranking possible 30-40 second moments.")
        highlights = select_highlights(transcript["segments"], scenes)
        if not has_audio:
            highlights["note"] = "No audio stream was found. Scene detection completed, but speech-based highlight ranking was skipped."

        result = {
            "source_id": source["id"],
            "source_filename": source["original_filename"],
            "metadata": metadata,
            "transcript": transcript,
            "scene_count": len(scenes),
            "scenes": scenes,
            "highlights": highlights,
            "warnings": [] if has_audio else ["No audio stream was found."],
        }
        _update_analysis(
            analysis_id,
            status="COMPLETED",
            stage="completed",
            progress=100,
            message="Analysis completed. Transcript, scenes and highlight candidates are ready.",
            model_name=transcript.get("model"),
            language=transcript.get("language"),
            result_json=json.dumps(result, ensure_ascii=False),
            error_message=None,
        )
    except Exception as exc:
        logger.exception("Analysis %s failed", analysis_id)
        _update_analysis(
            analysis_id,
            status="FAILED",
            stage="failed",
            progress=0,
            message="Analysis failed. Read the error below, fix the issue and retry.",
            error_message=str(exc)[:1200],
        )
    finally:
        if audio_path:
            audio_path.unlink(missing_ok=True)
