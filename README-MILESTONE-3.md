# AutoClips AI — Milestone 3: Automatic Clip Production

This additive update turns selected highlight timestamps from Milestone 2 into vertical MP4 files. It remains local-first and free to run with the existing tools.

## Requirements

- Existing AutoClips AI Milestone 2.1 project
- Existing `.venv/` and `storage/` folders
- FFmpeg and FFprobe available on PATH
- No additional Python packages are required

## Install

1. Stop the app with `Ctrl+C`.
2. Extract this update ZIP into the existing project root and allow the included application files to be replaced.
3. Do not delete `.venv/`, `storage/`, the SQLite database, original uploads or cached Whisper models.
4. From PowerShell in the project root, run `.\run_windows.bat`
5. Open `http://127.0.0.1:8000`.

## Render clips

1. Open a completed analysis with highlight candidates.
2. Select **Generate N vertical clips**. This first version renders all non-overlapping candidates from that analysis.
3. The dashboard polls render status and displays each finished clip with an inline preview and MP4 download link.
4. Generated files are saved under `storage/clips/` and their metadata is stored in the `clips` SQLite table.

## Output profile

| Property | Output |
|---|---|
| Container | MP4 |
| Video | H.264 / yuv420p |
| Resolution | 1080 × 1920 |
| Frame rate | 30 FPS |
| Audio | AAC 128 kbps / 48 kHz when present |
| Audio level | FFmpeg `loudnorm` one-pass target |
| Subtitles | Burned-in SRT from transcript segments, if available |
| Duration | 30–40 seconds |

The renderer does not stretch video. It scales and center-crops to fill 9:16. This can crop people near the edges of landscape footage; intelligent subject tracking is future work.

## API

- `POST /api/v1/analysis/{analysis_id}/render` — queue all highlight candidates for rendering.
- `GET /api/v1/analysis/{analysis_id}/clips` — list rendered clip jobs.
- `GET /api/v1/clips/{clip_id}/file` — inline preview.
- `GET /api/v1/clips/{clip_id}/download` — download MP4.

Open `http://127.0.0.1:8000/docs` for interactive API documentation.

## Retry and recovery

Failed clips can be retried by clicking the render button again. If the app closes while a clip is queued or rendering, the next startup marks it failed and retryable. Keep the app running during a render.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

This milestone performs clip rendering only. It does not publish content to YouTube, Instagram or Facebook. Continue to process only source videos you own or are authorized to edit and distribute.
