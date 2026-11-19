"""Scene-boundary detection using PySceneDetect."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_scenes(video_path: Path) -> list[dict[str, Any]]:
    if not video_path.is_file():
        raise FileNotFoundError("The original video file is missing from storage.")

    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import ContentDetector
    except ImportError as exc:
        raise RuntimeError(
            "PySceneDetect is not installed. Run setup_windows.bat to install the Milestone 2 dependencies."
        ) from exc

    try:
        video = open_video(str(video_path))
        manager = SceneManager()
        manager.downscale = 2
        manager.add_detector(ContentDetector(threshold=27.0, min_scene_len=15))
        manager.detect_scenes(video, show_progress=False)
        scene_list = manager.get_scene_list()
    except Exception as exc:
        raise RuntimeError(f"Scene detection failed: {str(exc)[:240]}") from exc

    scenes: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(scene_list, start=1):
        # PySceneDetect 0.7 exposes seconds as a property; older 0.6 builds used get_seconds().
        start_seconds = float(start.seconds if hasattr(start, "seconds") else start.get_seconds())
        end_seconds = float(end.seconds if hasattr(end, "seconds") else end.get_seconds())
        scenes.append(
            {
                "scene_number": index,
                "start": round(start_seconds, 3),
                "end": round(end_seconds, 3),
                "duration": round(max(0.0, end_seconds - start_seconds), 3),
            }
        )
    return scenes
