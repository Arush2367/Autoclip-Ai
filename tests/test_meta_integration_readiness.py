import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database import database as database_module
from backend.api import meta as meta_api


class MetaIntegrationReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "autoclips.sqlite3"
        self.database_patch = patch.object(database_module, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        database_module.initialize_database()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_meta_tables_and_default_connection_rows_are_created(self):
        with database_module.database_connection() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            connections = connection.execute(
                "SELECT platform, status FROM meta_connections ORDER BY platform"
            ).fetchall()
            publication_columns = {
                row["name"] for row in connection.execute(
                    "PRAGMA table_info(meta_publications)"
                ).fetchall()
            }

        self.assertIn("meta_connections", tables)
        self.assertIn("meta_publications", tables)
        self.assertEqual(
            [(row["platform"], row["status"]) for row in connections],
            [("facebook", "NOT_CONNECTED"), ("instagram", "NOT_CONNECTED")],
        )
        self.assertNotIn("access_token", publication_columns)
        self.assertNotIn("app_secret", publication_columns)

    def test_initialize_is_idempotent_for_meta_connection_rows(self):
        database_module.initialize_database()
        database_module.initialize_database()
        with database_module.database_connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM meta_connections"
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_status_reports_prepared_but_not_connected_or_publish_enabled(self):
        with patch.object(
            meta_api,
            "configuration_status",
            return_value={
                "app_id_configured": False,
                "app_secret_configured": False,
                "graph_api_version_configured": False,
                "credentials_configured": False,
                "api_calls_enabled": False,
            },
        ):
            result = meta_api.get_meta_status()

        self.assertTrue(result["integration_ready"])
        self.assertFalse(result["connection_flow_implemented"])
        self.assertFalse(result["publishing_enabled"])
        self.assertFalse(result["platforms"]["instagram"]["connected"])
        self.assertFalse(result["platforms"]["facebook"]["connected"])
        self.assertFalse(result["credentials"]["api_calls_enabled"])


if __name__ == "__main__":
    unittest.main()
