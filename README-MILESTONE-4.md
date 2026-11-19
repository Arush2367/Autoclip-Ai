# AutoClips AI — Milestone 4

Milestone 4 adds an official YouTube Data API v3 publisher to the existing local-first pipeline.

## Install

1. Stop the running backend with `Ctrl+C`.
2. Extract this update into the existing project folder. Merge folders and replace files when prompted.
3. Keep `.venv` and all of `storage/` intact.
4. Run `setup_windows.bat` to install the three Google API dependencies added to `requirements.txt`.
5. Configure OAuth credentials as described below.
6. Start the app with `run_windows.bat` and visit `http://127.0.0.1:8000`.

## Google Cloud setup

1. Create or select a Google Cloud project.
2. Enable **YouTube Data API v3**.
3. Configure Google Auth Platform app information and choose the audience appropriate for the account. For an individual Google account, this is commonly **External**; when in **Testing** mode, add the authorizing account as a test user.
4. Under Clients, create an OAuth 2.0 client ID with application type **Desktop app**.
5. Download its JSON and place it at `secrets/client_secret.json` (create the `secrets` folder if needed).
6. Click **Connect YouTube account** in the local dashboard and complete the Google-hosted consent flow.

Google's official documentation:

- [Upload a video with YouTube Data API](https://developers.google.com/youtube/data/guides/uploading_a_video)
- [Create credentials and a Desktop OAuth client](https://developers.google.com/workspace/guides/create-credentials)
- [YouTube API developer policies](https://developers.google.com/youtube/terms/developer-policies)

The app requests two OAuth scopes: `youtube.upload` to publish videos and `youtube.readonly` only to display the authorized channel name and ID. The dashboard shows the channel title and ID so you can confirm the destination before uploading. AutoClips AI never asks for your Google password. The client-secret JSON and OAuth token are local secrets and are excluded from Git by `.gitignore`. Do not upload or send either file.

If the OAuth app is configured as External / Testing, Google documents a 7-day refresh-token lifetime for scopes beyond basic profile/email. Reconnect if Google expires the local authorization during testing. A public release may require OAuth verification and a privacy policy, depending on distribution and scope requirements.

If Google's age rules require a parent or guardian to approve account use, have them handle the required consent and authorization. Do not bypass age or account restrictions.

## Upload workflow

1. Open a completed analysis and locate a completed generated clip.
2. Edit the title (required), description and tags as desired.
3. Choose the made-for-kids audience setting and visibility. The initial selection is **Private**. You can explicitly choose Unlisted or Public.
4. Set altered/synthetic disclosure when appropriate. Leaving it unspecified means you must review the disclosure in YouTube Studio.
5. Confirm the source rights, YouTube Community Guidelines, and approval for this exact clip and its selected metadata/visibility.
6. Click **Upload this clip to YouTube** and keep the local app running until it reports completion.

A YouTube upload is a clearly identified, user-initiated action; this milestone does not silently upload every clip. YouTube's API policies require clear user consent and final user control over uploaded metadata and visibility.

If an upload is marked `FAILED` or `INTERRUPTED`, inspect YouTube Studio first. Only check the retry confirmation and retry once you have verified that the previous attempt did not create a video. This guards against duplicates after interrupted network sessions.

## API endpoints

- `GET /api/v1/youtube/status`
- `POST /api/v1/youtube/connect`
- `POST /api/v1/youtube/disconnect`
- `POST /api/v1/clips/{clip_id}/youtube-upload`
- `GET /api/v1/clips/{clip_id}/youtube-upload`

## Quota and costs

The Google API libraries and local app code are free. YouTube Data API usage is controlled by project quota. Google's current quota documentation lists 100 `videos.insert` calls per day by default; check your Google Cloud Console quota page because allocations can change.

This project cannot guarantee account standing, monetization, audience growth, or that YouTube will accept every upload. Use only footage and audio you own or are authorized to publish, and comply with YouTube policies.
