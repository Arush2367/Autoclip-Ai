"""Application configuration for the local development build."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Read local secrets/configuration from .env without overriding explicitly-set OS variables.
load_dotenv(PROJECT_ROOT / ".env", override=False)

STORAGE_ROOT = Path(os.getenv("AUTOCLIPS_STORAGE", PROJECT_ROOT / "storage")).resolve()
ORIGINALS_DIR = STORAGE_ROOT / "original"
TEMP_DIR = STORAGE_ROOT / "temp"
CLIPS_DIR = STORAGE_ROOT / "clips"
MODEL_CACHE_DIR = STORAGE_ROOT / "models"
SECRETS_DIR = PROJECT_ROOT / "secrets"
YOUTUBE_CLIENT_SECRETS_FILE = SECRETS_DIR / "client_secret.json"
YOUTUBE_TOKEN_FILE = STORAGE_ROOT / "secrets" / "youtube_token.json"
YOUTUBE_CHANNEL_FILE = STORAGE_ROOT / "secrets" / "youtube_channel.json"
META_APP_ID = os.getenv("META_APP_ID", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "").strip()
META_TOKEN_DIR = STORAGE_ROOT / "secrets"
META_INSTAGRAM_TOKEN_FILE = META_TOKEN_DIR / "meta_instagram_token.json"
META_FACEBOOK_TOKEN_FILE = META_TOKEN_DIR / "meta_facebook_token.json"
DATABASE_PATH = Path(
    os.getenv("AUTOCLIPS_DATABASE", PROJECT_ROOT / "storage" / "autoclips.sqlite3")
).resolve()

MAX_UPLOAD_MB = int(os.getenv("AUTOCLIPS_MAX_UPLOAD_MB", "2048"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

# CPU/int8 is deliberately the default: it is compatible with ordinary Windows
# laptops and avoids a CUDA/toolkit dependency on the user's GTX 1650.
WHISPER_MODEL = os.getenv("AUTOCLIPS_WHISPER_MODEL", "base").strip() or "base"
WHISPER_DEVICE = os.getenv("AUTOCLIPS_WHISPER_DEVICE", "cpu").strip() or "cpu"
WHISPER_COMPUTE_TYPE = os.getenv("AUTOCLIPS_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
WHISPER_CPU_THREADS = max(2, min(6, os.cpu_count() or 4))

for directory in (
    ORIGINALS_DIR,
    TEMP_DIR,
    CLIPS_DIR,
    MODEL_CACHE_DIR,
    DATABASE_PATH.parent,
    SECRETS_DIR,
    YOUTUBE_TOKEN_FILE.parent,
    META_TOKEN_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
