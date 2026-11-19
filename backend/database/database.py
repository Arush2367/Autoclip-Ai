"""Small SQLite data layer; no external database server is required."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from backend.config import DATABASE_PATH


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    """Create new tables without changing or deleting existing source records."""
    with database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                file_extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'upload',
                rights_confirmed INTEGER NOT NULL CHECK (rights_confirmed IN (0, 1)),
                validation_status TEXT NOT NULL,
                duration_seconds REAL,
                width INTEGER,
                height INTEGER,
                video_codec TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                job_type TEXT NOT NULL DEFAULT 'INGESTION',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                model_name TEXT,
                language TEXT,
                result_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sources_created_at
                ON sources(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_source_id
                ON jobs(source_id);
            CREATE INDEX IF NOT EXISTS idx_analyses_source_id
                ON analyses(source_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_analyses_status
                ON analyses(status);

            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                start_seconds REAL NOT NULL,
                end_seconds REAL NOT NULL,
                duration_seconds REAL NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                output_filename TEXT NOT NULL UNIQUE,
                storage_path TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                video_codec TEXT,
                subtitle_status TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(analysis_id, start_seconds, end_seconds)
            );

            CREATE INDEX IF NOT EXISTS idx_clips_analysis_id
                ON clips(analysis_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_clips_status
                ON clips(status);

            CREATE TABLE IF NOT EXISTS youtube_publications (
                id TEXT PRIMARY KEY,
                clip_id TEXT NOT NULL UNIQUE REFERENCES clips(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                privacy_status TEXT NOT NULL,
                made_for_kids INTEGER NOT NULL CHECK (made_for_kids IN (0, 1)),
                contains_synthetic_media INTEGER,
                rights_confirmed INTEGER NOT NULL CHECK (rights_confirmed IN (0, 1)),
                guidelines_confirmed INTEGER NOT NULL CHECK (guidelines_confirmed IN (0, 1)),
                user_approved INTEGER NOT NULL CHECK (user_approved IN (0, 1)),
                youtube_video_id TEXT,
                youtube_url TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_youtube_publications_status
                ON youtube_publications(status, updated_at DESC);
            """
        )
