"""Meta Instagram Unified Login and Facebook Page Reels publishing.

The Unified Login token is a Business Integration System User Access Token
(SUAT). It is supplied locally by the user, validated with Meta, and stored
only in the ignored storage/secrets/meta_auth.json file. Facebook Page access
is stored separately because an Instagram Unified Login token does not
implicitly grant Page publishing access.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from backend.config import META_APP_ID, META_APP_SECRET, META_GRAPH_API_VERSION, META_TOKEN_FILE
from backend.services.secure_storage import load_secure_json, save_secure_json, secure_delete

GRAPH_BASE = "https://graph.facebook.com"
INSTAGRAM_UPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload"
REQUEST_TIMEOUT = (15, 90)


class MetaPublisherError(RuntimeError):
    """Safe-to-display Meta integration error."""


def _decode_response(response: requests.Response, secrets_to_redact: tuple[str, ...] = ()) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaPublisherError("Meta returned an unreadable response. Check your token permissions and try again.") from exc
    if not isinstance(payload, dict):
        raise MetaPublisherError("Meta returned an unexpected response format.")
    error = payload.get("error")
    if response.status_code >= 400 or error:
        message = "Meta API request failed."
        if isinstance(error, dict):
            message = str(error.get("message") or message)
        elif payload.get("message"):
            message = str(payload["message"])
        for secret in secrets_to_redact:
            if secret:
                message = message.replace(secret, "[redacted]")
        raise MetaPublisherError(message[:700])
    return payload


def graph_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    access_token: str | None = None,
    timeout: tuple[int, int] = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    """Call the versioned Graph API without logging or returning credentials."""
    url = f"{GRAPH_BASE}/{META_GRAPH_API_VERSION}/{path.strip('/')}"
    query = dict(params or {})
    # Never put bearer tokens in URLs: URL query strings are commonly captured
    # by HTTP logs, diagnostics, reverse proxies and monitoring systems.
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    try:
        response = requests.request(
            method.upper(), url, params=query, data=data, headers=headers,
            timeout=timeout, allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise MetaPublisherError(f"Could not reach Meta: {exc.__class__.__name__}.") from exc
    secrets_to_redact = [access_token or ""]
    if access_token and META_APP_SECRET and access_token.endswith(f"|{META_APP_SECRET}"):
        secrets_to_redact.append(META_APP_SECRET)
    return _decode_response(response, tuple(secrets_to_redact))


def fetch_unified_instagram_accounts(access_token: str) -> tuple[str | None, list[dict[str, str]]]:
    """Resolve Instagram assets shared with the Unified Login system user.

    The assigned_instagram_accounts edge is the authoritative asset lookup for
    this token type. Avoid requesting optional business fields from /me here:
    those fields vary by token/app setup and are not required to publish.
    """
    result = graph_request(
        "GET", "me/assigned_instagram_accounts",
        params={"fields": "id,username", "limit": 100}, access_token=access_token,
    )
    raw_accounts = result.get("data", [])
    if not isinstance(raw_accounts, list):
        raise MetaPublisherError("Meta returned an invalid Instagram account list.")
    accounts = [
        {"id": str(item["id"]), "username": str(item.get("username") or "Instagram professional account")}
        for item in raw_accounts if isinstance(item, dict) and item.get("id")
    ]
    if not accounts:
        raise MetaPublisherError(
            "Meta accepted the token but returned no Instagram accounts. Confirm this is the Unified Login token and that the Instagram account is shared with the app configuration."
        )
    return None, accounts


def fetch_facebook_page(page_access_token: str) -> dict[str, str]:
    """Validate a Page token with Meta's debug-token endpoint, then resolve /me.

    Do not request the legacy `category` field: Meta may reject it for newer
    Page/token configurations with Graph API error #100. The debug-token
    endpoint distinguishes PAGE from USER tokens without relying on that field.
    """
    if not META_APP_ID or not META_APP_SECRET:
        raise MetaPublisherError(
            "Set META_APP_ID and META_APP_SECRET in your local .env before validating a Facebook Page token."
        )

    app_access_token = f"{META_APP_ID}|{META_APP_SECRET}"
    debug = graph_request(
        "GET", "debug_token", params={"input_token": page_access_token},
        access_token=app_access_token,
    )
    token_data = debug.get("data") or {}
    if not token_data.get("is_valid"):
        raise MetaPublisherError("The Facebook Page token is invalid or expired. Generate a fresh Page token.")
    if str(token_data.get("app_id") or "") != str(META_APP_ID):
        raise MetaPublisherError("This Facebook Page token was generated for a different Meta app. Select AutoClip-Ai and generate it again.")

    token_type = str(token_data.get("type") or "").upper()
    profile_id = str(token_data.get("profile_id") or "")
    if token_type != "PAGE" and not profile_id:
        raise MetaPublisherError(
            "This is a Facebook User token, not a Page token. In Graph API Explorer request "
            "GET /me/accounts?fields=id,name,access_token,tasks, then copy the access_token inside the Ashu Page row."
        )

    page = graph_request(
        "GET", "me", params={"fields": "id,name"}, access_token=page_access_token,
    )
    page_id = str(page.get("id") or "")
    if not page_id or (profile_id and page_id != profile_id):
        raise MetaPublisherError("Meta could not verify that this token belongs to the expected Facebook Page. Generate the Ashu Page token again.")
    return {"id": page_id, "name": str(page.get("name") or "Facebook Page")}


def load_auth_data() -> dict[str, Any] | None:
    try:
        payload = load_secure_json(Path(META_TOKEN_FILE))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MetaPublisherError("The local Meta credential file cannot be read. Reconnect the accounts.") from exc
    return payload if isinstance(payload, dict) else None


def save_auth_data(payload: dict[str, Any]) -> None:
    try:
        save_secure_json(Path(META_TOKEN_FILE), payload)
    except (OSError, RuntimeError, ValueError) as exc:
        raise MetaPublisherError("AutoClips could not securely store the Meta credentials. Check folder permissions and reconnect.") from exc


def delete_auth_data() -> None:
    secure_delete(Path(META_TOKEN_FILE))


def connect_with_tokens(
    *, instagram_access_token: str | None,
    facebook_page_access_token: str | None = None,
    preferred_instagram_account_id: str | None = None,
) -> dict[str, Any]:
    """Validate provided local credentials and persist them outside the database."""
    instagram_access_token = (instagram_access_token or "").strip()
    facebook_page_access_token = (facebook_page_access_token or "").strip()
    previous = load_auth_data() or {}
    previous_ig = (previous.get("instagram") or {}).get("access_token")
    previous_fb = (previous.get("facebook") or {}).get("access_token")
    instagram_access_token = instagram_access_token or str(previous_ig or "")
    facebook_page_access_token = facebook_page_access_token or str(previous_fb or "")
    if not instagram_access_token and not facebook_page_access_token:
        raise MetaPublisherError("Enter the Instagram Unified Login access token. A Facebook Page token is optional.")

    auth: dict[str, Any] = {"connected_at": int(time.time())}
    if instagram_access_token:
        business_id, accounts = fetch_unified_instagram_accounts(instagram_access_token)
        selected = next(
            (account for account in accounts if account["id"] == str(preferred_instagram_account_id)),
            accounts[0],
        )
        auth["instagram"] = {
            "access_token": instagram_access_token,
            "business_id": business_id,
            "accounts": accounts,
            "account_id": selected["id"],
            "account_name": selected["username"],
        }
    if facebook_page_access_token:
        page = fetch_facebook_page(facebook_page_access_token)
        auth["facebook"] = {
            "access_token": facebook_page_access_token,
            "page_id": page["id"],
            "page_name": page["name"],
        }

    save_auth_data(auth)
    return safe_connection_status(auth)


def safe_connection_status(auth: dict[str, Any] | None) -> dict[str, Any]:
    auth = auth or {}
    instagram = auth.get("instagram") or {}
    facebook = auth.get("facebook") or {}
    return {
        "instagram": {
            "connected": bool(instagram.get("access_token") and instagram.get("account_id")),
            "account_id": instagram.get("account_id"),
            "account_name": instagram.get("account_name"),
            "business_id": instagram.get("business_id"),
            "available_accounts": [
                {"id": item.get("id"), "username": item.get("username")}
                for item in instagram.get("accounts", []) if isinstance(item, dict)
            ],
        },
        "facebook": {
            "connected": bool(facebook.get("access_token") and facebook.get("page_id")),
            "account_id": facebook.get("page_id"),
            "account_name": facebook.get("page_name"),
        },
    }


def safe_connection_metadata(auth: dict[str, Any] | None) -> dict[str, Any]:
    """Alias retained for API code clarity; never returns access tokens."""
    return safe_connection_status(auth)


def upload_local_video(upload_url: str, access_token: str, video_path: Path) -> dict[str, Any]:
    size = video_path.stat().st_size
    parsed = urlparse(upload_url)
    try:
        upload_port = parsed.port
    except ValueError:
        upload_port = -1
    if (
        parsed.scheme != "https"
        or parsed.hostname != "rupload.facebook.com"
        or parsed.username is not None
        or parsed.password is not None
        or upload_port not in (None, 443)
    ):
        raise MetaPublisherError("Meta returned an unexpected media upload URL. Reconnect and try again.")
    with video_path.open("rb") as video_file:
        try:
            response = requests.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {access_token}",
                    "offset": "0",
                    "file_size": str(size),
                    "Content-Type": "application/octet-stream",
                },
                data=video_file,
                timeout=(30, 600),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise MetaPublisherError(f"Meta media upload failed: {exc.__class__.__name__}.") from exc
    return _decode_response(response, (access_token,))


def publish_instagram_reel(
    *, instagram_account_id: str, instagram_access_token: str, video_path: Path,
    caption: str, is_ai_generated: bool = False,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Publish a Reel using the Instagram API with Unified Login (SUAT)."""
    if video_path.stat().st_size > 300 * 1024 * 1024:
        raise MetaPublisherError("Instagram Reels API requires the video file to be 300 MB or smaller.")
    params: dict[str, Any] = {"media_type": "REELS", "upload_type": "resumable", "caption": caption}
    if is_ai_generated:
        params["is_ai_generated"] = "true"
    container = graph_request(
        "POST", f"{instagram_account_id}/media", params=params, access_token=instagram_access_token,
    )
    container_id = container.get("id")
    if not container_id:
        raise MetaPublisherError("Meta did not return an Instagram media container ID.")
    upload_url = f"{INSTAGRAM_UPLOAD_BASE}/{META_GRAPH_API_VERSION}/{container_id}"
    upload_local_video(upload_url, instagram_access_token, video_path)
    if progress:
        progress(70)

    status = "IN_PROGRESS"
    for attempt in range(5):
        if attempt:
            time.sleep(60)
        status_data = graph_request(
            "GET", str(container_id), params={"fields": "status_code"}, access_token=instagram_access_token,
        )
        status = str(status_data.get("status_code") or "UNKNOWN").upper()
        if status == "FINISHED":
            break
        if status in {"ERROR", "EXPIRED"}:
            raise MetaPublisherError(f"Instagram rejected the Reel container: {status}.")
    if status != "FINISHED":
        raise MetaPublisherError("Instagram is still processing this Reel. Check Instagram before retrying to avoid duplicates.")
    if progress:
        progress(90)
    published = graph_request(
        "POST", f"{instagram_account_id}/media_publish",
        data={"creation_id": str(container_id)}, access_token=instagram_access_token,
    )
    media_id = published.get("id")
    if not media_id:
        raise MetaPublisherError("Instagram did not return a published media ID.")
    media = graph_request(
        "GET", str(media_id), params={"fields": "id,permalink"}, access_token=instagram_access_token,
    )
    if progress:
        progress(100)
    return {"media_id": str(media_id), "url": media.get("permalink")}


def publish_facebook_reel(
    *, page_id: str, page_access_token: str, video_path: Path, title: str,
    caption: str, is_ai_generated: bool = False,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Publish a Reel to a Facebook Page using the Page video_reels edge."""
    # Preflight the exact Page ID with the same Page token before creating an
    # upload session. This catches a User token accidentally saved as a Page
    # token and stale/mismatched Page IDs before any upload starts.
    page = graph_request(
        "GET", str(page_id), params={"fields": "id,name"}, access_token=page_access_token,
    )
    if str(page.get("id") or "") != str(page_id):
        raise MetaPublisherError(
            "The saved Facebook token does not have access to the selected Page. Reconnect with the Page access_token "
            "from the Ashu row in GET /me/accounts?fields=id,name,access_token,tasks. Check that its tasks include CREATE_CONTENT or MANAGE."
        )
    started = graph_request(
        "POST", f"{page_id}/video_reels", data={"upload_phase": "start"}, access_token=page_access_token,
    )
    video_id, upload_url = started.get("video_id"), started.get("upload_url")
    if not video_id or not upload_url:
        raise MetaPublisherError("Meta did not return the Facebook Reels upload session details.")
    upload_local_video(str(upload_url), page_access_token, video_path)
    if progress:
        progress(75)
    finish: dict[str, Any] = {
        "upload_phase": "finish", "video_id": str(video_id),
        "video_state": "PUBLISHED", "description": caption,
    }
    if title.strip():
        finish["title"] = title.strip()[:255]
    if is_ai_generated:
        finish["is_ai_generated"] = "true"
    result = graph_request(
        "POST", f"{page_id}/video_reels", data=finish, access_token=page_access_token,
    )
    if result.get("success") is False:
        raise MetaPublisherError(str(result.get("message") or "Facebook did not publish the Reel."))
    if progress:
        progress(100)
    return {"media_id": str(result.get("post_id") or video_id), "url": None}


def publish_clip(
    *, platform: str, video_path: Path, caption: str, title: str,
    is_ai_generated: bool = False, progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    auth = load_auth_data() or {}
    if platform == "instagram":
        account = auth.get("instagram") or {}
        if not account.get("access_token") or not account.get("account_id"):
            raise MetaPublisherError("Instagram Unified Login is not connected.")
        return publish_instagram_reel(
            instagram_account_id=str(account["account_id"]),
            instagram_access_token=str(account["access_token"]),
            video_path=video_path, caption=caption, is_ai_generated=is_ai_generated, progress=progress,
        )
    if platform == "facebook":
        page = auth.get("facebook") or {}
        if not page.get("access_token") or not page.get("page_id"):
            raise MetaPublisherError("Facebook Page publishing is not connected. Add a Facebook Page access token separately.")
        return publish_facebook_reel(
            page_id=str(page["page_id"]), page_access_token=str(page["access_token"]),
            video_path=video_path, title=title, caption=caption,
            is_ai_generated=is_ai_generated, progress=progress,
        )
    raise MetaPublisherError("Unsupported Meta publishing destination.")
