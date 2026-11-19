"""Helpers for safely accepting and validating uploaded video files."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.config import ALLOWED_EXTENSIONS


def safe_display_filename(filename: str | None) -> str:
    """Return a display-only filename without path components or control chars."""
    raw_name = (filename or "uploaded_video").replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_name).strip(" .")
    return cleaned[:180] or "uploaded_video"


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def signature_matches(extension: str, header: bytes) -> bool:
    """Check common container signatures; this is a first-pass check, not a codec decode."""
    if extension in {".mp4", ".mov", ".m4v"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if extension in {".mkv", ".webm"}:
        return header.startswith(bytes.fromhex("1A45DFA3"))
    if extension == ".avi":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    return False


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(file_path: Path) -> dict[str, Any] | None:
    """Read media metadata with ffprobe. Return None when ffprobe is not installed."""
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None

    command = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,codec_name,width,height",
        "-of", "json",
        str(file_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Video inspection timed out. Try a shorter or smaller file.") from exc

    if result.returncode != 0:
        safe_error = (result.stderr or "Unable to inspect this video.").strip()[:300]
        raise ValueError(f"Video could not be decoded by FFprobe: {safe_error}")

    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("FFprobe returned invalid metadata for this video.") from exc

    streams = metadata.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not video_stream:
        raise ValueError("The uploaded file does not contain a video stream.")

    try:
        duration = float(metadata.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0.0

    if duration <= 0:
        raise ValueError("The video duration could not be read or is zero.")

    return {
        "duration_seconds": duration,
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "video_codec": video_stream.get("codec_name"),
    }
