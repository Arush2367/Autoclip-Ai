# AutoClips AI security hardening update

## Apply to your existing working project

This patch is an overlay for the existing AutoClips AI project that already has your working Instagram/Facebook publishing code installed. Do not apply it to a fresh clone of the remote branch: the remote branch checked during the audit is behind the local Meta API ZIP updates.

1. Stop AutoClips AI with `Ctrl+C`.
2. Make a backup of your `.env` file and `storage/` folder.
3. Extract this ZIP into the existing project root and allow the included source/test files to merge or replace.
4. Do not delete `.env`, `storage/`, `.venv/`, `secrets/`, your SQLite database, uploaded videos, generated clips, or Whisper model cache.
5. Install the declared direct HTTP dependency and keep the environment current:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

6. Run the complete project test suite:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

7. Start the application:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
   ```

8. Verify that YouTube, Instagram, and Facebook still report connected and that a test publication works. The normal local-only security middleware should still allow `http://127.0.0.1:8000`.

## Important credential action

Any Instagram, Facebook, Google, GitHub, or app secret that was pasted into a chat, issue, screenshot, log, or public repository must be considered exposed. Revoke/rotate those values at their provider and enter replacements only into local `.env` or AutoClips on your computer. Do not put replacement credentials in GitHub or chat.

On Windows, existing plaintext YouTube and Meta token JSON files are migrated to current-user DPAPI encryption the first time AutoClips reads them after this update. DPAPI files can only be decrypted by the same Windows user on the same Windows installation. Back up your account recovery path (not the token files) and do not copy the encrypted token files to a different PC/user.

## What this update does not do

- It does not turn AutoClips into a public multi-user web app. The application is now explicitly restricted to loopback access. Do not expose it with `--host 0.0.0.0`, a LAN binding, port forwarding, or a public reverse proxy.
- It does not remove secrets from old Git history. If any credential was ever committed, rotate it and separately inspect/clean the Git history.
- It does not replace provider account security, device security, or Windows malware protection.
- It does not guarantee that every possible vulnerability is absent. Review GitHub Actions security results and Dependabot alerts after pushing.
