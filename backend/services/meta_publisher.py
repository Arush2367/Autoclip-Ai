"""Meta publishing integration contract.

This milestone prepares configuration and local status only. It intentionally
makes no Meta Graph API calls and cannot connect or publish yet.
"""

from backend.config import META_APP_ID, META_APP_SECRET, META_GRAPH_API_VERSION


SUPPORTED_PLATFORMS = {
    "instagram": {
        "name": "Instagram Reels",
        "media_type": "REELS",
        "destination": "Instagram professional account",
    },
    "facebook": {
        "name": "Facebook Reels",
        "media_type": "REELS",
        "destination": "Facebook Page",
    },
}


def configuration_status() -> dict:
    """Return safe booleans only; never return app secrets or access tokens."""
    app_id_configured = bool(META_APP_ID)
    app_secret_configured = bool(META_APP_SECRET)
    graph_version_configured = bool(META_GRAPH_API_VERSION)
    return {
        "app_id_configured": app_id_configured,
        "app_secret_configured": app_secret_configured,
        "graph_api_version_configured": graph_version_configured,
        "credentials_configured": (
            app_id_configured and app_secret_configured and graph_version_configured
        ),
        "api_calls_enabled": False,
    }


def platform_definitions() -> dict:
    """Return a copy of the supported destinations for API/UI consumers."""
    return {key: value.copy() for key, value in SUPPORTED_PLATFORMS.items()}
