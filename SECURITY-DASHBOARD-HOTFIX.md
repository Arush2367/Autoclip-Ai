# AutoClips AI — Dashboard 403 hotfix

This targeted patch adjusts the local-only request middleware so a browser can
open the dashboard root from an external link without opening cross-site access
to the API.

## Files

- `backend/security.py`
- `tests/test_local_security.py`

## Install

1. Stop Uvicorn with `Ctrl+C`.
2. Extract this ZIP into the AutoClips AI project root (the folder containing
   `backend`, `frontend`, `tests`, and `requirements.txt`).
3. Allow replacement of the two files above.
4. Run the focused tests:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest tests.test_local_security -v
   ```

   Confirm that all 10 tests pass.

5. Run the full test suite:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

6. Start the app:

   ```powershell
   python -m uvicorn backend.main:app --reload
   ```

7. Open `http://127.0.0.1:8000/` directly in your browser.

## What remains blocked

- Non-loopback clients.
- Untrusted Host names, including arbitrary hostnames that could be used for
  DNS-rebinding attempts.
- Mismatched or non-local Origin headers.
- Cross-site API calls, static subresources, and state-changing requests.

Only a `GET` or `HEAD` top-level document navigation to `/` is exempted from the
cross-site Fetch Metadata rejection. Keep Uvicorn bound to `127.0.0.1`; do not
run it with `--host 0.0.0.0`.

This is a targeted fix, not a formal penetration test or a guarantee that all
security risks have been eliminated.
