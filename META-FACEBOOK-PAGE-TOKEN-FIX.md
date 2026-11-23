# Facebook Reels: Page token validation fix

The previous validator treated any token that returned `/me` with an `id` and `name` as a Page token. A Facebook User access token also returns those fields, so it could be incorrectly saved as a Page connection. The first `POST /{id}/video_reels` then fails because the user ID is not a Page ID.

This patch requests the Page-only `category` field when validating `/me` and preflights the exact Page ID with the same token before starting a Reel upload. It does not change Instagram token handling or YouTube.

## Reconnect Facebook only

1. In Graph API Explorer, select your Facebook User token and ensure `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts` are granted.
2. Run `GET /me/accounts?fields=id,name,access_token,tasks`.
3. In the `Ashu` object, verify `tasks` contains `CREATE_CONTENT` or `MANAGE`.
4. Copy the nested `access_token` from that `Ashu` object. It is the Page access token. Do not use the top-level User token or Instagram token.
5. In AutoClips, replace only the Facebook Page access token and validate/save. The app should identify the Page as `Ashu`.
6. Test Facebook again with one reviewed clip.

Never send access tokens in chat or commit them to GitHub.
