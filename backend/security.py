"""Local-only request protection for the AutoClips AI dashboard.

The application is designed to run on the same machine as its browser. This
middleware rejects non-loopback clients, untrusted Host headers, mismatched
Origins, and cross-site requests. The only cross-site exception is a safe
GET/HEAD navigation to the dashboard document itself, so a user can open the
local URL from a link without enabling cross-site API access.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (
        b"content-security-policy",
        b"default-src 'self'; base-uri 'self'; object-src 'none'; "
        b"frame-ancestors 'none'; form-action 'self'; "
        b"img-src 'self' data: blob:; media-src 'self' blob:; "
        b"style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
    ),
)


def _is_loopback_client(client_host: str | None) -> bool:
    if not client_host:
        return False
    try:
        return ipaddress.ip_address(client_host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _parse_host_header(host_header: str | None) -> tuple[str, int | None] | None:
    if not host_header or any(char in host_header for char in "\\/\r\n\t "):
        return None
    try:
        parsed = urlsplit("//" + host_header)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return None
    if hostname not in _ALLOWED_HOSTS:
        return None
    if port is not None and not (1 <= port <= 65535):
        return None
    return hostname, port


def _origin_matches_host(origin: str | None, host: tuple[str, int | None]) -> bool:
    # An absent Origin is normal for direct navigation and many safe GETs.
    if origin is None:
        return True
    if not origin or origin == "null":
        return False
    try:
        parsed = urlsplit(origin)
        origin_host = (parsed.hostname or "").lower()
        origin_port = parsed.port
    except ValueError:
        return False
    if parsed.scheme.lower() != "http" or parsed.username or parsed.password:
        return False
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False
    return (origin_host, origin_port) == host and origin_host in _ALLOWED_HOSTS


def is_local_request_allowed(
    *,
    client_host: str | None,
    host_header: str | None,
    origin: str | None,
    method: str,
    path: str,
    sec_fetch_site: str | None = None,
    sec_fetch_mode: str | None = None,
    sec_fetch_dest: str | None = None,
) -> bool:
    """Return whether an incoming HTTP request satisfies the local-only policy."""
    if not _is_loopback_client(client_host):
        return False

    parsed_host = _parse_host_header(host_header)
    if parsed_host is None:
        return False
    if not _origin_matches_host(origin, parsed_host):
        return False

    fetch_site = (sec_fetch_site or "").strip().lower()
    if fetch_site == "cross-site":
        # Permit only a top-level document navigation to the dashboard root.
        # API requests, static files, and every mutation remain denied.
        return (
            method.upper() in {"GET", "HEAD"}
            and path == "/"
            and (sec_fetch_mode or "").strip().lower() == "navigate"
            and (sec_fetch_dest or "").strip().lower() == "document"
        )

    return True


class LocalOnlySecurityMiddleware:
    """Pure ASGI middleware enforcing the local dashboard access policy."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        client = scope.get("client")
        client_host = client[0] if client else None

        allowed = is_local_request_allowed(
            client_host=client_host,
            host_header=_header_text(headers.get(b"host")),
            origin=_header_text(headers.get(b"origin")),
            method=scope.get("method", "GET"),
            path=scope.get("path", "/"),
            sec_fetch_site=_header_text(headers.get(b"sec-fetch-site")),
            sec_fetch_mode=_header_text(headers.get(b"sec-fetch-mode")),
            sec_fetch_dest=_header_text(headers.get(b"sec-fetch-dest")),
        )

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {key.lower() for key, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (key, value) for key, value in _SECURITY_HEADERS if key not in existing
                ]
                if scope.get("path", "").startswith("/api/"):
                    message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        if not allowed:
            body = b"Forbidden: this application is available only from its local dashboard."
            await send_with_security_headers(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send_with_security_headers(
                {"type": "http.response.body", "body": body, "more_body": False}
            )
            return

        await self.app(scope, receive, send_with_security_headers)


def _header_text(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return value.decode("latin-1")
    except UnicodeDecodeError:
        return None
