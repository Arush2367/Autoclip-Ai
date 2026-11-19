"""Local OAuth and resumable upload adapter for the official YouTube Data API v3."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

from backend.config import YOUTUBE_CHANNEL_FILE, YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE]


class YouTubePublisherError(RuntimeError):
    """A safe, user-displayable YouTube integration error."""


def google_libraries_installed() -> bool:
    try:
        import googleapiclient.discovery  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
        return True
    except ImportError:
        return False


def connection_status() -> dict:
    libraries_installed = google_libraries_installed()
    client_configured = YOUTUBE_CLIENT_SECRETS_FILE.is_file()
    token_exists = YOUTUBE_TOKEN_FILE.is_file()
    connected = False
    token_error = None

    if libraries_installed and token_exists:
        try:
            credentials = _load_credentials(refresh=False)
            connected = bool(credentials and (credentials.valid or credentials.refresh_token))
        except Exception as exc:  # Status must never expose token or secret contents.
            token_error = "Saved YouTube authorization needs to be reconnected."

    channel = _load_cached_channel()
    if connected and not channel:
        connected = False
        token_error = "The authorized channel identity is missing. Disconnect and connect the intended YouTube channel again."
    return {
        "libraries_installed": libraries_installed,
        "client_configured": client_configured,
        "token_saved": token_exists,
        "connected": connected,
        "ready_to_connect": libraries_installed and client_configured,
        "channel_id": channel.get("id") if channel else None,
        "channel_title": channel.get("title") if channel else None,
        "message": token_error or None,
    }


def _load_credentials(refresh: bool = True):
    if not google_libraries_installed():
        raise YouTubePublisherError(
            "YouTube API libraries are missing. Run setup_windows.bat to install requirements."
        )
    if not YOUTUBE_TOKEN_FILE.is_file():
        raise YouTubePublisherError("YouTube is not connected. Connect your account first.")

    from google.oauth2.credentials import Credentials

    try:
        credentials = Credentials.from_authorized_user_file(
            str(YOUTUBE_TOKEN_FILE), YOUTUBE_SCOPES
        )
    except Exception as exc:
        raise YouTubePublisherError(
            "The saved YouTube authorization is unreadable. Disconnect and connect again."
        ) from exc

    if not credentials.valid and credentials.expired and credentials.refresh_token and refresh:
        from google.auth.transport.requests import Request
        try:
            credentials.refresh(Request())
            _save_credentials(credentials)
        except Exception as exc:
            raise YouTubePublisherError(
                "YouTube authorization expired or was revoked. Reconnect the account."
            ) from exc

    if not credentials.valid and not (credentials.expired and credentials.refresh_token and not refresh):
        raise YouTubePublisherError("YouTube authorization is no longer valid. Reconnect the account.")
    return credentials


def _save_credentials(credentials) -> None:
    YOUTUBE_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = YOUTUBE_TOKEN_FILE.with_suffix(".tmp")
    temporary.write_text(credentials.to_json(), encoding="utf-8")
    os.replace(temporary, YOUTUBE_TOKEN_FILE)


def connect_youtube() -> dict:
    """Run Google's installed-app OAuth flow after the user clicks Connect."""
    if not google_libraries_installed():
        raise YouTubePublisherError(
            "YouTube API libraries are not installed. Run setup_windows.bat first."
        )
    if not YOUTUBE_CLIENT_SECRETS_FILE.is_file():
        raise YouTubePublisherError(
            "OAuth client file not found. Put your downloaded Desktop-app JSON at secrets/client_secret.json."
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(YOUTUBE_CLIENT_SECRETS_FILE), YOUTUBE_SCOPES
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            authorization_prompt_message="Complete Google authorization in the browser that opens.",
            success_message="YouTube authorization completed. You may close this browser tab and return to AutoClips AI.",
            access_type="offline",
            prompt="consent",
        )
        # A newly authorized Google account may point to a different channel.
        YOUTUBE_CHANNEL_FILE.unlink(missing_ok=True)
        _save_credentials(credentials)
        service = _build_service(credentials)
        response = service.channels().list(part="snippet", mine=True).execute()
        items = response.get("items", [])
        if not items:
            raise YouTubePublisherError(
                "Google authorization succeeded, but this account has no accessible YouTube channel. Set up a channel with the account holder, then reconnect."
            )
        channel = {
            "id": items[0].get("id"),
            "title": items[0].get("snippet", {}).get("title", "YouTube channel"),
        }
        if not channel["id"]:
            raise YouTubePublisherError("Google authorization succeeded, but YouTube did not return a channel ID.")
        _save_cached_channel(channel)
        return channel
    except YouTubePublisherError:
        raise
    except Exception as exc:
        raise YouTubePublisherError(
            "Google authorization did not complete or the channel could not be identified. Check the OAuth Desktop client, enabled API and channel access, then try again."
        ) from exc


def disconnect_youtube() -> None:
    """Remove the locally cached token. This does not delete channel content."""
    try:
        YOUTUBE_TOKEN_FILE.unlink(missing_ok=True)
        YOUTUBE_CHANNEL_FILE.unlink(missing_ok=True)
    except OSError as exc:
        raise YouTubePublisherError("Could not remove the local YouTube authorization files.") from exc


def _load_cached_channel() -> dict | None:
    try:
        payload = json.loads(YOUTUBE_CHANNEL_FILE.read_text(encoding="utf-8"))
        if payload.get("id") and payload.get("title"):
            return {"id": str(payload["id"]), "title": str(payload["title"])}
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return None


def _save_cached_channel(channel: dict) -> None:
    YOUTUBE_CHANNEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = YOUTUBE_CHANNEL_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(channel, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, YOUTUBE_CHANNEL_FILE)


def _build_service(credentials):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def parse_tags(tags_text: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in (tags_text or "").split(","):
        tag = raw_tag.strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    if sum(len(tag) for tag in tags) + max(0, len(tags) - 1) > 500:
        raise YouTubePublisherError("Combined YouTube tags must be 500 characters or fewer.")
    return tags


def build_video_body(
    *,
    title: str,
    description: str,
    tags: Iterable[str],
    privacy_status: str,
    made_for_kids: bool,
    contains_synthetic_media: bool | None = None,
) -> dict:
    if not title or not title.strip() or len(title) > 100:
        raise YouTubePublisherError("YouTube title must contain 1–100 characters.")
    if len(description or "") > 5000:
        raise YouTubePublisherError("YouTube description must be 5,000 characters or fewer.")
    if privacy_status not in {"private", "unlisted", "public"}:
        raise YouTubePublisherError("Choose Private, Unlisted or Public visibility.")

    snippet = {
        "title": title,
        "description": description or "",
    }
    clean_tags = [tag.strip() for tag in tags if tag and tag.strip()]
    if clean_tags:
        snippet["tags"] = clean_tags

    status = {
        "privacyStatus": privacy_status,
        "selfDeclaredMadeForKids": bool(made_for_kids),
    }
    if contains_synthetic_media is not None:
        status["containsSyntheticMedia"] = bool(contains_synthetic_media)
    return {"snippet": snippet, "status": status}


def upload_video(
    *,
    video_path: Path,
    title: str,
    description: str,
    tags: Iterable[str],
    privacy_status: str,
    made_for_kids: bool,
    contains_synthetic_media: bool | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> dict:
    """Upload a local MP4 with Google's resumable media-upload client."""
    video_path = Path(video_path).resolve()
    if not video_path.is_file():
        raise YouTubePublisherError("The generated MP4 file no longer exists.")
    if video_path.suffix.lower() != ".mp4":
        raise YouTubePublisherError("YouTube publisher expects a generated MP4 file.")

    body = build_video_body(
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
        made_for_kids=made_for_kids,
        contains_synthetic_media=contains_synthetic_media,
    )

    from googleapiclient.http import MediaFileUpload

    credentials = _load_credentials(refresh=True)
    service = _build_service(credentials)
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        upload_status, response = request.next_chunk(num_retries=5)
        if upload_status is not None and progress_callback is not None:
            progress_callback(max(0, min(99, int(upload_status.progress() * 100))))

    if not isinstance(response, dict) or not response.get("id"):
        raise YouTubePublisherError("YouTube did not return a video ID after upload.")
    return response
