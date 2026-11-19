import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database import database as database_module


class DatabaseMigrationTests(unittest.TestCase):
    def test_legacy_source_and_job_records_survive_upgrade(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "legacy.sqlite3"

            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE sources (
                    id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL UNIQUE,
                    file_extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO sources (
                    id, original_filename, stored_filename, file_extension,
                    size_bytes, sha256, storage_path, status, created_at
                ) VALUES (
                    'source-old', 'old.mp4', 'old.mp4', '.mp4',
                    12, 'checksum', 'storage/original/old.mp4', 'UPLOADED', '2026-01-01'
                );
                INSERT INTO jobs (id, source_id, status, created_at)
                VALUES ('job-old', 'source-old', 'RECEIVED', '2026-01-01');
                """
            )
            connection.commit()
            connection.close()

            with patch.object(database_module, "DATABASE_PATH", db_path):
                database_module.initialize_database()
                with database_module.database_connection() as upgraded:
                    source = upgraded.execute(
                        "SELECT * FROM sources WHERE id = 'source-old'"
                    ).fetchone()
                    job = upgraded.execute(
                        "SELECT * FROM jobs WHERE id = 'job-old'"
                    ).fetchone()
                    tables = {
                        row["name"]
                        for row in upgraded.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }

            self.assertEqual(source["original_filename"], "old.mp4")
            self.assertEqual(source["rights_confirmed"], 0)
            self.assertEqual(source["source_type"], "upload")
            self.assertEqual(source["validation_status"], "legacy_unverified")
            self.assertEqual(job["job_type"], "INGESTION")
            self.assertEqual(job["updated_at"], "2026-01-01")
            self.assertIn("analyses", tables)
            self.assertIn("clips", tables)
            self.assertIn("youtube_publications", tables)

    def test_initialize_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "fresh.sqlite3"
            with patch.object(database_module, "DATABASE_PATH", db_path):
                database_module.initialize_database()
                database_module.initialize_database()
                with database_module.database_connection() as connection:
                    tables = {
                        row["name"]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
            self.assertIn("sources", tables)
            self.assertIn("youtube_publications", tables)


if __name__ == "__main__":
    unittest.main()
