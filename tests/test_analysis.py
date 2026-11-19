import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services.highlight_selection import select_highlights


class HighlightSelectionTests(unittest.TestCase):
    def test_returns_candidate_within_target_duration(self):
        transcript = [
            {"start": 0.0, "end": 8.0, "text": "Wait, why did this happen?"},
            {"start": 8.0, "end": 17.0, "text": "I never expected the result to be so amazing!"},
            {"start": 17.0, "end": 26.0, "text": "Here is the secret and the reason it changed everything."},
            {"start": 26.0, "end": 36.0, "text": "Listen carefully, because this is the truth."},
        ]
        scenes = [
            {"start": 0.0, "end": 12.0},
            {"start": 12.0, "end": 24.0},
            {"start": 24.0, "end": 36.0},
        ]

        result = select_highlights(transcript, scenes)

        self.assertTrue(result["items"])
        clip = result["items"][0]
        self.assertGreaterEqual(clip["duration"], 30.0)
        self.assertLessEqual(clip["duration"], 40.0)
        self.assertIn("score", clip)

    def test_short_source_returns_clear_note(self):
        result = select_highlights(
            [{"start": 0.0, "end": 12.4, "text": "This is a short test video."}],
            [],
        )
        self.assertEqual(result["items"], [])
        self.assertIn("at least 30 seconds", result["note"])

    def test_empty_transcript_returns_no_candidates(self):
        result = select_highlights([], [])
        self.assertEqual(result["items"], [])
        self.assertIn("No speech transcript", result["note"])

    def test_selected_highlights_never_overlap(self):
        # 80 seconds of continuous transcript creates many possible 30-40s windows.
        transcript = [
            {"start": float(i * 5), "end": float((i + 1) * 5),
             "text": "Wait, this is the truth and it changed everything!"}
            for i in range(16)
        ]
        result = select_highlights(transcript, [], max_clips=12)
        items = result["items"]

        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(result["overlap_policy"], "strict_non_overlapping")
        for previous, current in zip(items, items[1:]):
            self.assertLessEqual(previous["end"], current["start"])


class DatabaseMigrationTests(unittest.TestCase):
    def test_initialize_adds_analyses_table_without_deleting_existing_tables(self):
        from backend.database import database

        with tempfile.TemporaryDirectory() as folder:
            temp_db = Path(folder) / "test.sqlite3"
            with patch.object(database, "DATABASE_PATH", temp_db):
                database.initialize_database()
                with database.database_connection() as connection:
                    names = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
        self.assertIn("sources", names)
        self.assertIn("jobs", names)
        self.assertIn("analyses", names)
        self.assertIn("clips", names)


if __name__ == "__main__":
    unittest.main()
