# AutoClips AI — Milestone 2: Local Video Intelligence

A free, local-first Windows project for accepting authorized source videos, transcribing speech with Faster-Whisper, detecting scene boundaries with PySceneDetect and ranking possible 30-40 second highlights.

## Requirements

- Windows 10/11
- Python 3.10 or newer (Python 3.11 or 3.12 is a good compatibility choice if a native package wheel is unavailable for your Python version)
- FFmpeg and FFprobe installed and available on PATH
- VS Code (recommended)
- Internet access for the first Whisper model download; after it is cached, transcription runs locally

No paid AI API, subscription or cloud inference is used by this milestone.

## Install or update

1. Extract this update into your existing AutoClips project folder and allow code files to be replaced.
2. Keep your existing `storage/` folder and `.venv/`; they contain your uploaded videos, SQLite database and Python environment.
3. Run `setup_windows.bat` to install the Milestone 2 Python dependencies.
4. Run `run_windows.bat` and open `http://127.0.0.1:8000`.

If PowerShell blocks virtual-environment activation, run this in the terminal first:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## Run analysis

1. Select a source under **Recent source videos**.
2. Click **Analyze video**.
3. Wait for the local worker to validate the video, extract audio, transcribe speech, detect scenes and rank highlight candidates.
4. The analysis panel displays transcript count, scene count and suggested timestamps.

The first analysis downloads the selected Faster-Whisper `base` model into `storage/models/`. This download is free but requires internet access once. The default uses CPU + int8 to work on ordinary laptops without CUDA setup. The Whisper weights are not bundled in the ZIP.

## What this milestone does

- Keeps the Milestone 1 upload and SQLite source library.
- Refreshes older source metadata with FFprobe when analysis begins. This also updates records that were first uploaded while FFprobe was unavailable.
- Extracts a compact mono audio track using FFmpeg.
- Transcribes speech locally with Faster-Whisper.
- Detects scene boundaries with PySceneDetect.
- Ranks non-overlapping transcript windows between 30 and 40 seconds.
- Stores analysis status and results in SQLite so the dashboard can poll progress.
- Cleans up temporary extracted audio after each job.

## Important limitation of highlight ranking

This first version uses transcript signals (phrases, punctuation and speech coverage) plus scene-change counts. It is transparent and free, but it is a heuristic ranking baseline, not a large language model judging story context. Scores are not predictions of views, retention or monetization. A later milestone can add an optional local semantic model after the basic pipeline is proven stable.

A source shorter than 30 seconds can still be transcribed and scene-detected, but cannot produce a 30-40 second candidate. The earlier 12.4-second test video is useful for verifying FFprobe, transcription and scene detection; use a longer video you own or are licensed to process to test highlight selection.

## API endpoints

- `GET /api/v1/health` — backend and media-tool status.
- `GET /api/v1/analysis/capabilities` — installed analysis dependencies and device settings.
- `POST /api/v1/sources/{source_id}/analyze` — queue a local analysis.
- `GET /api/v1/analysis/{analysis_id}` — poll status and retrieve completed results.
- `GET /api/v1/sources/{source_id}/analysis` — latest analysis for a source.
- `GET /docs` — interactive API documentation.

## Tests

From the project root, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover upload helpers, highlight-window duration rules, short-video behavior and additive SQLite schema setup. They do not download Whisper weights or process a full sample video.

## Data safety and known limitations

- Existing `storage/original/` videos and `storage/autoclips.sqlite3` are not included in the update ZIP and should be preserved.
- Analysis runs locally in a single background worker. Closing the app during a job marks it `INTERRUPTED`; start the analysis again from the dashboard.
- The first model download requires internet. The resulting transcript and scene data remain on the local machine.
- The upload rights checkbox is a workflow safeguard, not legal verification. Only analyze and later publish videos you own or are authorized to edit and distribute.
- Do not expose this local development service to the public internet.
- Do not add API keys, OAuth tokens or passwords to source files or GitHub.

## Milestone 4 — YouTube Publisher

See `MILESTONE-4-UPDATE.md` for installation and Google OAuth Desktop-app setup. This update adds user-approved YouTube Data API uploads and keeps OAuth secrets out of source control. Do not share `secrets/client_secret.json` or the local OAuth token.

## Ponytail

See `PONYTAIL_SETUP.md`. `AGENTS.md` provides project-level coding guidance for compatible agents; it does not install the full external plugin into ChatGPT.
