"""Small SQLite data layer with additive, non-destructive schema migrations."""

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


def _ensure_columns(
    connection: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    """Add missing columns without dropping or rebuilding existing user tables."""
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, declaration in columns.items():
        if column_name not in existing:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"
            )


def initialize_database() -> None:
    """Create new tables and safely upgrade databases from earlier milestones."""
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

            -- Meta connection rows contain account metadata only, never access tokens.
            CREATE TABLE IF NOT EXISTS meta_connections (
                platform TEXT PRIMARY KEY CHECK (platform IN ('instagram', 'facebook')),
                status TEXT NOT NULL DEFAULT 'NOT_CONNECTED',
                account_id TEXT,
                account_name TEXT,
                token_expires_at TEXT,
                last_checked_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- One clip can have a separate publication record for each Meta destination.
            -- Tokens/secrets are deliberately not stored in this table.
            CREATE TABLE IF NOT EXISTS meta_publications (
                id TEXT PRIMARY KEY,
                clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
                platform TEXT NOT NULL CHECK (platform IN ('instagram', 'facebook')),
                status TEXT NOT NULL DEFAULT 'PENDING_CONNECTION',
                progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
                caption TEXT NOT NULL DEFAULT '',
                is_ai_generated INTEGER NOT NULL DEFAULT 0 CHECK (is_ai_generated IN (0, 1)),
                published_media_id TEXT,
                published_url TEXT,
                error_message TEXT,
                rights_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (rights_confirmed IN (0, 1)),
                guidelines_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (guidelines_confirmed IN (0, 1)),
                user_approved INTEGER NOT NULL DEFAULT 0 CHECK (user_approved IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(clip_id, platform)
            );

            CREATE INDEX IF NOT EXISTS idx_meta_publications_status
                ON meta_publications(platform, status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_meta_publications_clip
                ON meta_publications(clip_id, created_at DESC);

            -- Short-lived OAuth state values are single-use and contain no credentials.
            CREATE TABLE IF NOT EXISTS meta_oauth_states (
                state TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        # Milestone 1 databases predate some of the source-library fields. Existing
        # videos remain available, but missing rights history is deliberately NOT
        # assumed: the user must explicitly reconfirm rights before processing.
        _ensure_columns(
            connection,
            "sources",
            {
                "source_type": "TEXT NOT NULL DEFAULT 'upload'",
                "rights_confirmed": "INTEGER NOT NULL DEFAULT 0 CHECK (rights_confirmed IN (0, 1))",
                "validation_status": "TEXT NOT NULL DEFAULT 'legacy_unverified'",
                "duration_seconds": "REAL",
                "width": "INTEGER",
                "height": "INTEGER",
                "video_codec": "TEXT",
                "error_message": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "jobs",
            {
                "job_type": "TEXT NOT NULL DEFAULT 'INGESTION'",
                "updated_at": "TEXT",
                "error_message": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "analyses",
            {
                "stage": "TEXT NOT NULL DEFAULT 'queued'",
                "progress": "INTEGER NOT NULL DEFAULT 0",
                "message": "TEXT",
                "model_name": "TEXT",
                "language": "TEXT",
                "result_json": "TEXT",
                "error_message": "TEXT",
                "updated_at": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "clips",
            {
                "title": "TEXT NOT NULL DEFAULT 'Untitled highlight'",
                "start_seconds": "REAL NOT NULL DEFAULT 0",
                "end_seconds": "REAL NOT NULL DEFAULT 0",
                "duration_seconds": "REAL NOT NULL DEFAULT 0",
                "score": "INTEGER NOT NULL DEFAULT 0",
                "status": "TEXT NOT NULL DEFAULT 'FAILED'",
                "output_filename": "TEXT",
                "storage_path": "TEXT",
                "width": "INTEGER",
                "height": "INTEGER",
                "video_codec": "TEXT",
                "subtitle_status": "TEXT",
                "error_message": "TEXT",
                "updated_at": "TEXT",
            },
        )

        # Create one not-connected row for each Meta destination, without claiming
        # that an account has been authorized inside this application.
        connection.execute(
            """INSERT OR IGNORE INTO meta_connections
               (platform, status, created_at, updated_at)
               VALUES ('instagram', 'NOT_CONNECTED', datetime('now'), datetime('now'))"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO meta_connections
               (platform, status, created_at, updated_at)
               VALUES ('facebook', 'NOT_CONNECTED', datetime('now'), datetime('now'))"""
        )

        _ensure_columns(
            connection,
            "meta_publications",
            {"is_ai_generated": "INTEGER NOT NULL DEFAULT 0 CHECK (is_ai_generated IN (0, 1))"},
        )

        # Backfill timestamps for rows from schemas that did not track updates.
        connection.execute(
            "UPDATE jobs SET updated_at = COALESCE(updated_at, created_at, datetime('now'))"
        )
        connection.execute(
            "UPDATE analyses SET updated_at = COALESCE(updated_at, created_at, datetime('now'))"
        )
        connection.execute(
            "UPDATE clips SET updated_at = COALESCE(updated_at, created_at, datetime('now'))"
        )
