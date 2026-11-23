"""OS-backed protection for locally stored OAuth/access-token JSON files.

Windows uses DPAPI (current user scope); other platforms use owner-only file
permissions. Plaintext files from older AutoClips versions are migrated to
DPAPI automatically on first successful read on Windows.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DPAPI_PREFIX = b"AUTOCLIPS-DPAPI-V1\n"
_DPAPI_ENTROPY = b"AutoClipsAI local credential storage v1"
IS_WINDOWS = os.name == "nt"


def _dpapi_transform(payload: bytes, *, protect: bool) -> bytes:
    if not IS_WINDOWS:
        raise RuntimeError("Windows DPAPI is unavailable on this platform.")

    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    input_buffer = ctypes.create_string_buffer(payload)
    entropy_buffer = ctypes.create_string_buffer(_DPAPI_ENTROPY)
    input_blob = DataBlob(
        len(payload), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    entropy_blob = DataBlob(
        len(_DPAPI_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    output_blob = DataBlob()

    if protect:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
        ]
        function.restype = wintypes.BOOL
        succeeded = function(
            ctypes.byref(input_blob), "AutoClips AI credentials", ctypes.byref(entropy_blob),
            None, None, 0x01, ctypes.byref(output_blob),
        )
    else:
        description = wintypes.LPWSTR()
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
        ]
        function.restype = wintypes.BOOL
        succeeded = function(
            ctypes.byref(input_blob), ctypes.byref(description), ctypes.byref(entropy_blob),
            None, None, 0x01, ctypes.byref(output_blob),
        )
        if description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))

    if not succeeded:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def _atomic_write(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if not IS_WINDOWS:
            os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        if not IS_WINDOWS:
            os.chmod(path, 0o600)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def save_secure_json(path: Path, value: Any) -> None:
    """Atomically save JSON encrypted with Windows DPAPI or owner-only elsewhere."""
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stored = DPAPI_PREFIX + _dpapi_transform(serialized, protect=True) if IS_WINDOWS else serialized
    _atomic_write(Path(path), stored)


def load_secure_json(path: Path) -> Any:
    """Load a secure JSON file; migrate legacy plaintext to DPAPI on Windows."""
    path = Path(path)
    raw = path.read_bytes()
    if raw.startswith(DPAPI_PREFIX):
        if not IS_WINDOWS:
            raise ValueError("This credential file was encrypted by Windows DPAPI and must be opened by the same Windows user.")
        raw = _dpapi_transform(raw[len(DPAPI_PREFIX):], protect=False)
    else:
        # Existing versions saved JSON directly. Migrate it immediately on Windows.
        if IS_WINDOWS:
            value = json.loads(raw.decode("utf-8"))
            save_secure_json(path, value)
            return value
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return json.loads(raw.decode("utf-8"))


def secure_delete(path: Path) -> None:
    """Remove the local credential file (storage media may retain old blocks)."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        raise


def harden_private_directory(path: Path) -> bool:
    """Restrict a private directory to the current user, SYSTEM and local admins."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if not IS_WINDOWS:
        try:
            os.chmod(path, 0o700)
            return True
        except OSError:
            return False

    username = os.environ.get("USERNAME")
    if not username:
        return False
    domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or "."
    identity = f"{domain}\\{username}"
    try:
        result = subprocess.run(
            [
                "icacls", str(path), "/inheritance:r",
                "/remove:g", "*S-1-1-0", "*S-1-5-32-545", "*S-1-5-11",
                "/grant:r", f"{identity}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F", "/C",
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def harden_private_file(path: Path) -> bool:
    """Restrict a local .env or OAuth client JSON file to user, SYSTEM and admins."""
    path = Path(path)
    if not path.is_file():
        return True
    if not IS_WINDOWS:
        try:
            os.chmod(path, 0o600)
            return True
        except OSError:
            return False

    username = os.environ.get("USERNAME")
    if not username:
        return False
    domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or "."
    identity = f"{domain}\\{username}"
    try:
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/remove:g", "*S-1-1-0", "*S-1-5-32-545", "*S-1-5-11", "/grant:r", f"{identity}:F", "*S-1-5-18:F", "*S-1-5-32-544:F"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
