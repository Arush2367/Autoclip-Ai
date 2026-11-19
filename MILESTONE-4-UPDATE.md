# AutoClips AI — Milestone 4: YouTube Publisher

This is an incremental update for the existing Milestone 3 project. It does not replace the project, `.venv`, source videos, rendered clips, or SQLite database.

## What it adds

- Official YouTube Data API v3 integration using the minimal upload and read-only channel-identification OAuth scopes (`youtube.upload` and `youtube.readonly`).
- Google OAuth Desktop-app connection flow. AutoClips AI never asks for a Google password.
- Resumable MP4 uploads with chunk progress.
- Per-clip title, description, tags, visibility, required made-for-kids audience selection, and optional altered/synthetic-content disclosure.
- Explicit per-upload confirmations for content rights, YouTube Community Guidelines, and approval of that exact upload.
- SQLite publication history and duplicate prevention for clips already uploaded.
- Manual review before retrying an interrupted/failed upload, to reduce accidental duplicates.
- Local token storage under ignored `storage/secrets/`; the downloaded OAuth client JSON belongs in ignored `secrets/`.

## Install the update

1. Stop AutoClips AI with `Ctrl+C` in the backend terminal.
2. Extract this ZIP into the existing `AutoClips-AI-Milestone-1` project directory and allow files to merge/replace.
3. Do not delete `.venv`, `storage/`, original videos, clips, or `storage/autoclips.sqlite3`.
4. Run `setup_windows.bat` to install the additional Google API dependencies.
5. Follow **Google OAuth setup** below.
6. Run `run_windows.bat` and open `http://127.0.0.1:8000`.

## Google OAuth setup

This is a local desktop integration. You must create your own Google Cloud project and OAuth client; AutoClips AI does not provide or share credentials.

1. In Google Cloud Console, create/select a project.
2. Enable **YouTube Data API v3** for that project.
3. Open Google Auth Platform, set up the app information and choose the audience applicable to the account. For an individual Google account, this is commonly **External**; when the app is in **Testing**, add the authorizing account as a test user.
4. Under Clients, create an OAuth 2.0 client with application type **Desktop app**.
5. Download the JSON file and place it at:

   `secrets/client_secret.json`

6. Restart AutoClips AI if it was running, then click **Connect YouTube account** in the dashboard.
7. Complete Google's hosted consent flow in the browser. The app requests `youtube.upload` to publish videos and `youtube.readonly` only to display the authorized channel name and ID. The dashboard shows the channel title and channel ID so you can confirm the destination before uploading.

Official guides:

- YouTube Data API upload guide: https://developers.google.com/youtube/data/guides/uploading_a_video
- Create a Desktop OAuth client: https://developers.google.com/workspace/guides/create-credentials
- YouTube API developer policies: https://developers.google.com/youtube/terms/developer-policies

Keep `secrets/client_secret.json` and `storage/secrets/youtube_token.json` private. Never paste them into a chat, commit them to GitHub, or send them to anyone. The `.gitignore` in this update excludes both locations.

If the Google Auth Platform app is in **External / Testing** mode, Google documents that refresh tokens generally expire after 7 days for scopes beyond basic profile/email. Reauthorization may therefore be needed during local testing. A production release may require OAuth verification and a privacy policy depending on distribution and the scopes used.

If the account holder's age requires parent or guardian permission under Google's terms, have the parent/guardian handle the required consent and account authorization. Do not bypass age or account restrictions.

## How to test

1. Confirm the YouTube panel reports **CONNECTED** after OAuth.
2. Open a completed analysis and its generated clips.
3. In one clip card, edit the title and optional description/tags.
4. Choose the made-for-kids audience setting and leave visibility at **Private** for the first test.
5. Confirm rights, Community Guidelines, and approval for this exact clip.
6. Click **Upload this clip to YouTube**.
7. Keep AutoClips AI running until status reaches `COMPLETED` and the video link appears.
8. Check the uploaded video in YouTube Studio.

The upload is a user-initiated action. The interface requires explicit approval for the specific clip and displays the selected visibility. The backend never silently uploads a batch or changes a selected privacy setting.

## Operational notes

- `videos.insert` uses the YouTube Data API's resumable upload protocol.
- YouTube's published default quota currently lists 100 `videos.insert` calls per day; quota allocation and policy can change. Check the Google Cloud Console quota page for this project.
- Uploads interrupted by closing the app are marked `INTERRUPTED`. Check YouTube Studio before retrying. This avoids blind retries that could create duplicate uploads.
- Disconnecting in AutoClips AI removes the locally stored token; it does not delete videos already uploaded. You can separately revoke the app in your Google Account's third-party connections settings.
- This milestone uploads only user-authorized clips. It does not guarantee account standing, reach, monetization, or platform approval.
