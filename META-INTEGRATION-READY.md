# Meta publishing integration — OAuth and Reels API

This update implements a Facebook Login connection shared by Instagram Reels and Facebook Page Reels. It performs real Meta requests only after the user explicitly clicks Connect or Publish in AutoClips AI.

## Local configuration

Add the following to the private project-root `.env` file (do not commit it):

```dotenv
META_APP_ID=YOUR_META_APP_ID
META_APP_SECRET=YOUR_META_APP_SECRET
META_GRAPH_API_VERSION=v27.0
META_REDIRECT_URI=http://127.0.0.1:8000/api/v1/meta/oauth/callback
# Optional, only if your Meta app has a saved Facebook Login for Business configuration:
META_LOGIN_CONFIG_ID=
```

In the Meta App Dashboard, configure the exact same callback URL under the Facebook Login / OAuth redirect URI allowlist. The app must have Facebook Login enabled and the Instagram API / Reels publishing use case configured.

## Permissions requested

- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`
- `instagram_basic`
- `instagram_content_publish`

The connected Facebook user must have `CREATE_CONTENT` or `MANAGE` task access to the Page. For an Instagram destination, the selected Page must have an Instagram Professional account linked. Consumer Instagram accounts are not supported by this Facebook Login publishing path.

In Development mode, the Facebook user must be an app role/tester with access to the app and the assets. For other users, Meta may require Advanced Access and App Review for the requested permissions.

## Connect

1. Start the local app at `http://127.0.0.1:8000`.
2. Click **Connect Meta accounts** in the Instagram & Facebook panel.
3. Complete Meta's consent screen.
4. Return to AutoClips AI and choose the Facebook Page. The app detects whether an Instagram Professional account is linked to that Page.
5. The user access token and Page token are saved only in `storage/secrets/meta_auth.json`, which must remain private and is covered by the existing `storage/*` Git ignore rule.

OAuth state is short-lived and single-use. Tokens are not returned by the API or stored in SQLite. Disconnect removes the local token file; it does not remove previously published Reels or revoke the app from Meta's account settings.

## Publish

Each generated clip card has a Meta publishing form. Select Instagram, Facebook, or both; review the caption; confirm rights and platform rules; and approve that exact clip before clicking Publish. The app keeps one status row per clip and platform and blocks automatic retries after an interrupted/failed attempt until the destination is checked.

- Instagram uses the official media-container, resumable-upload, container-status, and `media_publish` flow. The Instagram Reels API file limit is 300 MB.
- Facebook uses the official Page `video_reels` start, binary upload, and finish flow. Facebook Reels can only be published to Pages.

## Troubleshooting notes

- `redirect_uri` mismatch: make the URI in `.env` match the Meta dashboard exactly, including `127.0.0.1` vs `localhost` and the port.
- No Pages listed: confirm `pages_show_list`, Page permissions, and the user's Page `CREATE_CONTENT`/`MANAGE` task.
- Facebook works but Instagram does not appear: link the Instagram Professional account to the selected Facebook Page, then reconnect.
- Permission errors: confirm the requested permissions are enabled for the app. App Review / Advanced Access may be required outside app-role testing.
- Instagram publishing may fail if Page Publishing Authorization is required and not completed.

## Security

Never paste `META_APP_SECRET`, access tokens, or the contents of `storage/secrets/meta_auth.json` into chat or GitHub. The app secret and user/page tokens remain local. No password scraping, session-cookie reuse, or permission bypass is used.
