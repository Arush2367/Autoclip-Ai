# AutoClips AI security audit and hardening update

Audit target: public repository `Arush2367/Autoclip-Ai`, branch `feature/meta-integration-ready`, plus the later Meta publishing source delivered in the user's local update ZIPs. The GitHub branch inspected still contains the preparation-stage Meta code, while the user's local working copy has the later API publishing implementation from the update ZIPs; apply this patch to that existing local working copy, not to a fresh clone of the remote branch. The default `main` branch is also behind that feature branch. This is a targeted application review, not a guarantee that every possible vulnerability has been found.

## Findings fixed in this update

1. **Remote exposure / local API trust boundary.** The dashboard and its state-changing endpoints had no app-level check to stop access if Uvicorn was accidentally started on `0.0.0.0`. `LocalOnlySecurityMiddleware` now allows loopback clients only, validates local Host names, rejects cross-origin browser requests, and blocks cross-site Fetch Metadata. The Windows launcher explicitly binds to `127.0.0.1` and no longer uses the development reloader.
2. **Bearer-token leakage through URLs.** Meta Graph API access tokens were sent as `access_token` query parameters. The connector now sends them in the `Authorization: Bearer` header instead. Tokens are not added to Graph URL query strings.
3. **Local token files at rest.** Meta and YouTube OAuth/token JSON are now read/written through shared secure storage. On Windows, files are encrypted with the current user's DPAPI key; old plaintext token files are migrated on their first successful read. On POSIX, token files use owner-only `0600` permissions. `storage/secrets` and `secrets` directories are hardened with user-only permissions / Windows ACLs. The local `.env` and Google OAuth client JSON are also ACL-hardened on Windows when present.
4. **Incomplete secret ignore patterns.** `.gitignore` now ignores `.env` and all `.env.*` variants while explicitly allowing `.env.example`; it also ignores common private-key, token, database, and log artifacts.
5. **Missing continuous security checks.** GitHub Actions now runs `pip-audit`, Bandit, and the unit-test suite. Dependabot checks Python and GitHub Actions dependencies weekly.
6. **Browser hardening.** Responses receive restrictive CSP, frame denial, `nosniff`, no-referrer, permissions, same-origin resource, and no-store headers for API responses.
7. **Meta upload URL validation.** Resumable video uploads now reject unexpected hosts, non-HTTPS URLs, user-info in URLs, and nonstandard ports; redirect following is disabled to avoid forwarding credentials to a redirect destination.
8. **Facebook Page preflight compatibility.** The upload preflight no longer requests the optional/legacy `category` field; it verifies the returned Page ID and relies on the Page token/permissions instead.

## Safeguards already present in the reviewed source

- Source uploads use an extension allowlist, signature checks, generated UUID filenames, bounded chunked writes, and SHA-256 hashes.
- The local storage root is restricted to the current user on POSIX / ACL-hardened on Windows; credential files receive additional encryption or file permissions.
- FFmpeg / FFprobe are invoked with argument arrays rather than shell command strings and have operation timeouts.
- Clip and source paths are checked against their expected storage roots before preview, rendering, and publishing.
- SQL statements use bound parameters for request-controlled values.
- Meta and YouTube credentials are not stored in SQLite publication rows or returned in status responses.
- Publishing requires explicit rights, platform-guidelines, and clip-specific approval flags; retry paths require an explicit confirmation after checking the destination.

## Remaining risks and operational rules

- **This remains a single-user local desktop application.** The middleware blocks non-loopback requests, but there is no multi-user login/session system. Do not deploy it publicly, place it behind a public reverse proxy, or bind it to a LAN interface. A hosted product needs proper user authentication, per-user authorization, CSRF protection, tenant isolation, HTTPS, secrets management, and rate limiting.
- DPAPI protects token files against other Windows users and offline file disclosure, but it does not protect a token from malware or another process running as the same Windows account while AutoClips is unlocked. The Windows ACL helper uses the current user, SYSTEM and local Administrators; storage-folder ACL changes are applied at the directory boundary so new content inherits the restricted ACL.
- Google `client_secret.json` and Meta App Secret remain local application credentials; do not commit them or paste them into chats. Access tokens previously pasted into a chat should be revoked and replaced.
- GitHub repository content searches and the checked branch tree showed no obvious `.env`, OAuth token, or private-key files in the tracked source. This is not equivalent to GitHub's server-side secret scanning and does not prove secrets were never present on another branch, in deleted history, or in a release artifact. Enable GitHub secret scanning / push protection where available and inspect any historical alerts. The rulesets endpoint returned an empty list; branch-protection status could not be verified through the connected GitHub integration (403), so configure branch protection manually if available.
- The GitHub commit metadata currently exposes the commit author email recorded in history. Use GitHub's `noreply` commit email for future commits if you do not want your personal email displayed. Removing it from old commits requires rewriting history and is not included in this update.
- CI dependency scanning has been added but has not yet run on GitHub. Its result depends on the dependency versions resolved at workflow time. Keep dependencies updated and review generated Dependabot alerts.
- A local code review cannot verify Meta/Google account security settings, token revocation state, Windows malware posture, or third-party FFmpeg binary provenance.

## Required action after installing this update

1. Revoke the Instagram access token that was pasted into the chat and generate a replacement directly in Meta. Enter it only into AutoClips on the local computer. Revoke any other access token or app secret ever pasted into chats, screenshots, GitHub, or issue comments.
2. Keep `.env`, `secrets/client_secret.json`, `storage/secrets/`, and `storage/autoclips.sqlite3` out of Git.
3. Run the full project test suite locally and inspect `git status --short` before committing.
4. Review GitHub Actions' Security checks and Dependabot alerts after pushing this update.

## Test scope for this update

New tests cover loopback/Host/Origin policy, POSIX/DPAPI secure-storage behavior (DPAPI is mocked in cross-platform tests), Meta token placement in the Authorization header, and existing Meta publishing behavior. The full existing project suite and the Windows DPAPI native calls must be verified on the user's Windows machine before treating this as production-ready.
