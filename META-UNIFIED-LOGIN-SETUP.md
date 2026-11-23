# AutoClips AI — Meta Unified Login integration

This update corrects the earlier Meta connection implementation for the **Instagram API with Unified Login**. Unified Login uses a Business Integration System User Access Token (SUAT) and the `graph.facebook.com` host. It does not use the Instagram Login `graph.instagram.com` flow, nor can the Instagram token automatically be used as a Facebook Page token.

## Before connecting

A token was pasted into a chat during setup. Treat that token as exposed and do not reuse it. In Meta Business Settings, open **Integrations → Connected apps** and remove/revoke the AutoClip-Ai app connection for that business, then generate a fresh test access token from Meta Developers. Do not paste the replacement into chat, email, GitHub, or a source file.

## Connect Instagram first

1. Start AutoClips AI locally:

   ```powershell
   python -m uvicorn backend.main:app --reload
   ```

2. Open `http://127.0.0.1:8000`.
3. In **Instagram & Facebook Reels**, paste the freshly generated token from **Meta Developers → Instagram API → API setup with Unified Login → Generate access tokens** into **Instagram Unified Login access token**.
4. Leave **Facebook Page access token** empty for now.
5. Click **Validate & save locally**.
6. The app validates the token using `/me?fields=client_business_id` and `/me/assigned_instagram_accounts?fields=id,username`. It selects the first shared Instagram account if more than one is returned. For this setup, confirm the displayed account is `reel_for_everything`.

No Meta App ID, App Secret, callback URL, or Configuration ID needs to be copied into `.env` for this manual generated-token workflow; the app validates the generated token directly. The Configuration ID `1143855745286498` remains part of the Meta-side configuration, not a secret field in AutoClips. The app stores the token only in `storage/secrets/meta_auth.json`, which is ignored by Git. The API uses Pydantic `SecretStr` inputs, does not return the token to the browser, and the frontend clears both password fields after every request (success or failure). Keep the local app bound to `127.0.0.1`; do not expose its development server publicly.

## Facebook Reels is a separate connection

The Instagram Unified Login token grants access to the Instagram asset(s) shared through that configuration. It is not automatically a Facebook Page access token. To enable Facebook Reels, generate a **Page access token** for the Ashu Page with these Page permissions:

- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`

The person authorizing the token must have the Page's `CREATE_CONTENT` or `MANAGE` task. With a Facebook user token that has the above permissions, the Graph API `GET /me/accounts?fields=id,name,access_token,tasks` response includes the Page access token for the Pages the user can manage. Copy the `access_token` for **Ashu** into the local dashboard's **Facebook Page access token** field and click **Validate & save locally** again. The app validates that token against `/me?fields=id,name` and stores it alongside the Instagram credential.

This token must also stay private. Never paste either token into chat or commit it to GitHub. You can connect Instagram now and add the Facebook Page token later; the two platform statuses are independent.

## Publishing

Each completed clip card has its own Meta publishing controls. Select Instagram, Facebook, or both, review the caption, confirm rights and platform rules, and approve the exact clip. The app creates a separate publication record per platform and prevents automatic retries after failed or interrupted attempts until the destination has been checked.

Instagram publishing uses the Unified Login token and the Reels media-container/resumable-upload/`media_publish` flow. Facebook publishing uses the Facebook Page access token and the Page `video_reels` start/upload/finish flow. Webhooks remain optional for this upload-only workflow; the current update does not add message/comment event subscriptions.

## Troubleshooting

- **Invalid OAuth access token:** revoke the exposed token and generate a fresh token from the Unified Login setup; verify that `instagram_basic` and `instagram_content_publish` are included in the configuration.
- **No Instagram accounts returned:** confirm the configuration shared `reel_for_everything` with the app and that the account appears under Generate access tokens. Re-generate the token after changing asset access or configuration permissions.
- **Facebook token does not resolve to a Page:** make sure it is a *Page access token* for Ashu, not the Instagram SUAT, a Facebook app secret, or a Facebook user token.
- **Permission error on Facebook publishing:** check that the Facebook user has `CREATE_CONTENT` or `MANAGE` on the Page and that the token includes the required Page permissions.
- **Publishing error after container upload:** inspect the destination before retrying; do not submit repeated attempts without checking for a partially completed Reel.

## Verification performed for this update

- 12 Meta integration unit tests pass.
- Python compilation checks pass for the updated backend modules.
- JavaScript syntax check passes for the updated Meta frontend.

A real API connection and public Reel upload still require the user's replacement Meta token and Page token, plus a real test clip. Those live actions have not been performed by this package build.
