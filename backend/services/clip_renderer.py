"""Render selected highlight candidates into vertical MP4 clips with burned-in captions."""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from backend.services.ingestion import probe_video

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30
MIN_CLIP_SECONDS = 30.0
MAX_CLIP_SECONDS = 40.0


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{millis:03}"


def build_srt(segments: list[dict[str, Any]], clip_start: float, clip_end: float) -> str:
    """Create clip-relative SRT entries from the analysis transcript."""
    entries: list[str] = []
    cue_number = 1
    for segment in sorted(segments, key=lambda item: float(item.get("start", 0))):
        try:
            source_start = float(segment["start"])
            source_end = float(segment["end"])
            text = str(segment.get("text", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
        start = max(clip_start, source_start)
        end = min(clip_end, source_end)
        if end <= start or not text:
            continue
        # SRT is plain text; keep one cue readable and avoid malformed arrows/newlines.
        clean_text = re.sub(r"\s+", " ", text.replace("-->", "→")).strip()
        # Prevent transcript text from being interpreted as inline ASS override markup.
        clean_text = clean_text.replace("{", "(").replace("}", ")")
        lines = textwrap.wrap(clean_text, width=42, break_long_words=False, break_on_hyphens=False) or [clean_text]
        caption = "\n".join(lines[:2])
        entries.append(
            f"{cue_number}\n{_srt_timestamp(start - clip_start)} --> {_srt_timestamp(end - clip_start)}\n{caption}\n"
        )
        cue_number += 1
    return "\n".join(entries)


def build_video_filter(subtitle_filename: str | None = None) -> str:
    """Scale/crop without stretching; add readable captions when an SRT exists."""
    video_filter = (
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},setsar=1,fps={OUTPUT_FPS},format=yuv420p"
    )
    if subtitle_filename:
        # Filename is generated internally from a UUID and the worker runs in TEMP_DIR.
        style = (
            "FontName=Arial,FontSize=46,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=3,"
            "Outline=0,Shadow=0,Alignment=2,MarginV=120"
        )
        video_filter += f",subtitles=filename='{subtitle_filename}':force_style='{style}'"
    return video_filter


def _source_has_audio(source_path: Path, ffprobe_path: str) -> bool:
    result = subprocess.run(
        [
            ffprobe_path, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(source_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "FFprobe could not inspect source audio.").strip()[-400:]
        raise RuntimeError(f"Audio stream inspection failed: {detail}")
    return bool((result.stdout or "").strip())


def render_clip(
    *,
    source_path: Path,
    output_path: Path,
    temp_dir: Path,
    clip_id: str,
    clip_start: float,
    clip_end: float,
    transcript_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render one candidate. The source and output paths are supplied by trusted DB records."""
    if not source_path.is_file():
        raise FileNotFoundError("The original source video is missing.")
    duration = float(clip_end) - float(clip_start)
    if clip_start < 0 or duration < MIN_CLIP_SECONDS - 0.05 or duration > MAX_CLIP_SECONDS + 0.05:
        raise ValueError("Only highlight candidates between 30 and 40 seconds can be rendered.")

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError("FFmpeg and FFprobe must both be available on PATH.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    partial_path = temp_dir / f"{clip_id}.partial.mp4"
    srt_path = temp_dir / f"{clip_id}.srt"
    partial_path.unlink(missing_ok=True)
    srt_path.unlink(missing_ok=True)

    srt_text = build_srt(transcript_segments, clip_start, clip_end)
    subtitle_status = "burned_in" if srt_text.strip() else "no_speech_available"
    subtitle_filename: str | None = None
    if srt_text.strip():
        srt_path.write_text(srt_text, encoding="utf-8-sig", newline="\n")
        subtitle_filename = srt_path.name

    has_audio = _source_has_audio(source_path, ffprobe_path)
    command = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source_path),
        "-ss", f"{float(clip_start):.3f}",
        "-t", f"{duration:.3f}",
        "-map", "0:v:0",
    ]
    if has_audio:
        command.extend(["-map", "0:a:0", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
    command.extend(
        [
            "-vf", build_video_filter(subtitle_filename),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-r", str(OUTPUT_FPS),
        ]
    )
    if has_audio:
        command.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "48000"])
    command.extend(["-movflags", "+faststart", str(partial_path)])

    try:
        result = subprocess.run(
            command,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=60 * 30,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or "FFmpeg did not complete the render.").strip()[-900:]
            raise RuntimeError(f"Clip rendering failed: {detail}")
        if not partial_path.is_file() or partial_path.stat().st_size <= 0:
            raise RuntimeError("FFmpeg finished without producing a valid MP4 file.")

        metadata = probe_video(partial_path)
        if not metadata:
            raise RuntimeError("FFprobe could not verify the generated MP4.")
        if metadata.get("width") != OUTPUT_WIDTH or metadata.get("height") != OUTPUT_HEIGHT:
            raise RuntimeError("Rendered output did not match the required 1080 x 1920 resolution.")
        if metadata.get("video_codec") != "h264":
            raise RuntimeError("Rendered output did not use the required H.264 video codec.")
        if not (MIN_CLIP_SECONDS - 0.5 <= float(metadata["duration_seconds"]) <= MAX_CLIP_SECONDS + 0.5):
            raise RuntimeError("Rendered output duration fell outside the 30-40 second target.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.replace(output_path)
        return {
            "metadata": metadata,
            "subtitle_status": subtitle_status,
            "size_bytes": output_path.stat().st_size,
            "audio_included": has_audio,
        }
    finally:
        partial_path.unlink(missing_ok=True)
        srt_path.unlink(missing_ok=True)
