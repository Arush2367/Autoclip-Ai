# Milestone 3 — Automatic clip production

## Added
- A local FFmpeg renderer for analysis-selected 30–40 second highlights.
- Center-cropped vertical 1080×1920, 30 FPS, H.264/yuv420p MP4 output.
- AAC audio with one-pass loudness normalization when the source has audio.
- Transcript-derived SRT captions burned into clips when speech segments exist.
- SQLite `clips` table with an additive migration; existing sources, analyses and uploads are preserved.
- Background render queue, status polling, inline clip preview and MP4 download endpoints.
- Dashboard controls for generating all candidates and previewing completed clips.
- Per-clip failures and retry behavior; interrupted renders are made retryable at next startup.

## Boundaries
- This milestone renders only. It does not connect to or publish on social platforms.
- Landscape videos use a centered crop. Active-speaker tracking / intelligent reframing is future work.
- Caption timing follows transcript segment timestamps; editable captions and word-level animation are not included.

## Verification
- Unit tests cover subtitle clipping, video-filter construction, output validation and database migration.
- A real FFmpeg integration render was verified at 1080×1920, H.264 + AAC, 35.0 seconds, with subtitles burned in.
