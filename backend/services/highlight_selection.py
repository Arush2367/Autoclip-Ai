"""Transparent transcript-based ranking for 30-40 second highlight candidates.

This first local version does not call a paid LLM. It ranks complete transcript
windows using hook phrases, expressive punctuation, speech density and scene
changes. It is a useful baseline, not a promise of virality or deep semantics.
"""

from __future__ import annotations

import re
from typing import Any

HOOK_TERMS = {
    "why", "how", "what", "secret", "truth", "never", "finally", "imagine",
    "wait", "listen", "look", "because", "suddenly", "actually", "remember",
    "discovered", "mistake", "changed", "amazing", "incredible", "unbelievable",
}


def _normalise_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for segment in segments:
        try:
            start = max(0.0, float(segment["start"]))
            end = float(segment["end"])
            text = str(segment.get("text", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if end > start and text:
            cleaned.append({"start": start, "end": end, "text": text})
    return sorted(cleaned, key=lambda item: (item["start"], item["end"]))


def _score_candidate(
    text: str,
    duration: float,
    scene_count: int,
) -> tuple[int, list[str]]:
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    if not words:
        return 0, []

    word_count = len(words)
    word_set = set(words)
    hook_hits = sorted(word_set.intersection(HOOK_TERMS))
    question_count = text.count("?")
    exclamation_count = text.count("!")
    speech_density = min(1.0, word_count / max(1.0, duration * 2.0))
    hook_signal = min(1.0, len(hook_hits) / 4.0)
    punctuation_signal = min(1.0, (question_count + exclamation_count) / 3.0)
    scene_signal = min(1.0, max(0, scene_count - 1) / 4.0)

    score = round(
        100 * (
            0.45 * speech_density
            + 0.25 * hook_signal
            + 0.15 * punctuation_signal
            + 0.15 * scene_signal
        )
    )
    reasons = []
    if hook_hits:
        reasons.append("hook words: " + ", ".join(hook_hits[:4]))
    if question_count or exclamation_count:
        reasons.append("expressive dialogue")
    if speech_density >= 0.55:
        reasons.append("strong speech coverage")
    if scene_count > 1:
        reasons.append(f"{scene_count} detected scenes")
    if not reasons:
        reasons.append("clear speech window")
    return min(100, max(0, score)), reasons


def select_highlights(
    transcript_segments: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    *,
    min_duration: float = 30.0,
    max_duration: float = 40.0,
    target_duration: float = 35.0,
    max_clips: int = 12,
) -> dict[str, Any]:
    """Return ranked, strictly non-overlapping transcript windows aligned to speech ends."""
    segments = _normalise_segments(transcript_segments)
    if not segments:
        return {
            "method": "transcript_heuristic_v1",
            "target_duration_seconds": [min_duration, max_duration],
            "items": [],
            "overlap_policy": "strict_non_overlapping",
            "note": "No speech transcript was found, so no dialogue-based highlights could be ranked.",
        }

    total_end = max(item["end"] for item in segments)
    if total_end < min_duration:
        return {
            "method": "transcript_heuristic_v1",
            "target_duration_seconds": [min_duration, max_duration],
            "items": [],
            "overlap_policy": "strict_non_overlapping",
            "note": f"This source is {total_end:.1f} seconds long; at least {min_duration:.0f} seconds are needed for a target clip.",
        }

    candidates: list[dict[str, Any]] = []
    for start_index, first in enumerate(segments):
        start_time = first["start"]
        best_window = None
        best_distance = float("inf")
        for end_index in range(start_index, len(segments)):
            last = segments[end_index]
            duration = last["end"] - start_time
            if duration > max_duration:
                break
            if duration < min_duration:
                continue
            distance = abs(duration - target_duration)
            if distance < best_distance:
                best_distance = distance
                best_window = (end_index, duration)
        if best_window is None:
            continue

        end_index, duration = best_window
        window_segments = segments[start_index : end_index + 1]
        text = " ".join(item["text"] for item in window_segments).strip()
        start_time = round(start_time, 3)
        end_time = round(window_segments[-1]["end"], 3)
        scene_count = sum(
            1 for scene in scenes
            if start_time < float(scene.get("end", 0)) and end_time > float(scene.get("start", 0))
        )
        score, reasons = _score_candidate(text, duration, scene_count)
        title_words = re.findall(r"\S+", text)
        title = " ".join(title_words[:8]).strip(" ,.!?;:") or "Untitled highlight"
        if len(title) > 72:
            title = title[:69].rsplit(" ", 1)[0] + "..."
        candidates.append(
            {
                "start": start_time,
                "end": end_time,
                "duration": round(duration, 3),
                "score": score,
                "title": title,
                "reason": "; ".join(reasons),
                "transcript_excerpt": text[:900],
                "scene_count": scene_count,
            }
        )

    candidates.sort(key=lambda item: (item["score"], -abs(item["duration"] - target_duration)), reverse=True)
    selected: list[dict[str, Any]] = []
    # A clip must not reuse footage already assigned to another selected clip.
    # Even small overlaps create repetitive reposts and make downstream scheduling
    # less useful, so the production default is strict (zero-second) overlap.
    for candidate in candidates:
        overlaps = any(
            min(candidate["end"], chosen["end"])
            > max(candidate["start"], chosen["start"])
            for chosen in selected
        )
        if not overlaps:
            selected.append(candidate)
        if len(selected) >= max(1, int(max_clips)):
            break

    selected.sort(key=lambda item: item["start"])
    note = (
        "Candidates are ranked locally from transcript signals and scene changes. "
        "Selected clips never share source footage. Scores are heuristic relevance estimates, "
        "not predicted views or guaranteed engagement."
    )
    if not selected:
        note = "Speech was detected, but no complete 30-40 second transcript windows were available."

    return {
        "method": "transcript_heuristic_v1",
        "target_duration_seconds": [min_duration, max_duration],
        "overlap_policy": "strict_non_overlapping",
        "items": selected,
        "note": note,
    }
