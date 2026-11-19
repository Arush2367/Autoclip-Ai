import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database import database as database_module


class YouTubeMigrationTests(unittest.TestCase):
    def test_initialize_adds_youtube_table_and_preserves_existing_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "autoclips.sqlite3"
            with patch.object(database_module, "DATABASE_PATH", db_path):
                database_module.initialize_database()
                with database_module.database_connection() as connection:
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                self.assertIn("sources", tables)
                self.assertIn("clips", tables)
                self.assertIn("youtube_publications", tables)


if __name__ == "__main__":
    unittest.main()
