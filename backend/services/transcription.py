"""Local speech-to-text using Faster-Whisper; model downloads are cached locally."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import (
    MODEL_CACHE_DIR,
    WHISPER_COMPUTE_TYPE,
    WHISPER_CPU_THREADS,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)


@lru_cache(maxsize=1)
def _load_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Faster-Whisper is not installed. Run setup_windows.bat to install the Milestone 2 dependencies."
        ) from exc

    return WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
        cpu_threads=WHISPER_CPU_THREADS,
        num_workers=1,
        download_root=str(MODEL_CACHE_DIR),
    )


def transcribe_audio(audio_path: Path) -> dict[str, Any]:
    """Transcribe one extracted audio file and return timestamped speech segments."""
    if not audio_path.is_file():
        raise FileNotFoundError("The temporary audio file was not created.")

    model = _load_model()
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
        word_timestamps=False,
    )

    segments: list[dict[str, Any]] = []
    for segment in segments_iter:
        text = (segment.text or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": text,
            }
        )

    return {
        "model": WHISPER_MODEL,
        "language": getattr(info, "language", None),
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 4),
        "segments": segments,
    }
