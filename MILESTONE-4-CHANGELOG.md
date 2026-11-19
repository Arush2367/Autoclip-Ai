# Milestone 4 changelog

- Added `youtube_publications` SQLite table using additive `CREATE TABLE IF NOT EXISTS` migration.
- Added minimal-scope Google OAuth Desktop-app flow.
- Added YouTube Data API v3 resumable upload adapter.
- Added explicit rights, Community Guidelines, exact-upload, and visibility confirmations.
- Added per-clip upload status/progress and YouTube result link.
- Added duplicate protection and manual review before retrying interrupted/failed uploads.
- Added ignored storage paths for OAuth client secrets and local token files.
- Added unit tests for metadata validation, tag normalization and database migration.
