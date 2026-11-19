# Meta integration preparation (Instagram Reels + Facebook Reels)

This update prepares the AutoClips AI application structure for the next phase of Meta API connection. It does **not** connect an account, call the Meta Graph API, or publish content.

## Included in this phase

- Separate Meta API router with a safe integration-status endpoint.
- Separate Instagram and Facebook connection records in SQLite.
- Per-clip, per-platform publication-history table with duplicate-prevention key (`clip_id`, `platform`).
- No Meta app secret or access token columns in SQLite.
- Local `.env` loading and placeholder Meta app configuration variables.
- Dashboard status panel for Instagram Reels and Facebook Reels.
- Startup recovery marks an interrupted Meta publication clearly if one exists in a later phase.
- The existing YouTube publisher and YouTube routes remain separate and unchanged.

## New status endpoints

- `GET /api/v1/meta/status`
- `GET /api/v1/meta/clips/{clip_id}/publications`

The status endpoint reports that the app-side integration foundation is ready while clearly reporting that Meta authorization and publishing are not yet enabled.

## Next phase

The next implementation will connect the Meta developer app using the details already prepared by the user, implement authorized account selection/OAuth, then wire official publishing flows for Instagram Reels and Facebook Reels. At that point we will verify current Meta permissions, supported account types, Graph API version, and media-publishing requirements against Meta's official documentation before making API calls.

Keep any real `.env`, app secret, and future access tokens private. `.env`, `secrets/`, and `storage/secrets/` are already excluded from Git by the project's ignore rules. Never paste secret values into chat or commit them to GitHub.
