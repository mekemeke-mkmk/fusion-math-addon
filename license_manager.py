"""Autodesk Design and Make Marketplace entitlement checks for Math Curve."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# This is the Marketplace ID assigned to the Math Curve 2 preview submission.
MARKETPLACE_APP_ID = "1343581627431012464"
ENTITLEMENT_ENDPOINT = "https://apps.autodesk.com/webservices/checkentitlement"

# Developer mode skips the Marketplace check while testing the edit source on the
# developer's own PC. It needs this environment variable or the flag file below, AND an
# add-in folder outside the Marketplace install location (ApplicationPlugins), so
# installed copies always check. The flag file lives in the user's folder, never in the add-in.
DEV_MODE_ENV = "MATH_CURVE_DEV_MODE"
DEV_MODE_FLAG_NAME = "developer_mode"
ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass(frozen=True)
class LicenseStatus:
    allowed: bool
    mode: str
    message: str


def _get_fusion_user_id(app: Any) -> str:
    """Return Fusion's Autodesk account ID, which the Marketplace API expects."""
    try:
        return str(app.userId or "").strip()
    except Exception:
        return ""


def _parse_entitlement(payload: Any, user_id: str) -> LicenseStatus:
    if not isinstance(payload, dict):
        return LicenseStatus(False, "verification_error", "The Marketplace returned an invalid license response.")

    if payload.get("UserId") not in (None, "", user_id):
        return LicenseStatus(False, "verification_error", "The Marketplace license response was for a different user.")
    if str(payload.get("AppId", MARKETPLACE_APP_ID)) != MARKETPLACE_APP_ID:
        return LicenseStatus(False, "verification_error", "The Marketplace license response was for a different app.")

    if payload.get("IsValid") is True:
        return LicenseStatus(True, "entitled", "Marketplace entitlement verified.")

    marketplace_message = str(payload.get("Message") or "No active Marketplace entitlement was found.")
    return LicenseStatus(
        False,
        "not_entitled",
        "Your 30-day trial has ended or this Autodesk account does not have an active license. "
        f"Marketplace response: {marketplace_message}",
    )


def _request_entitlement(user_id: str) -> LicenseStatus:
    query = urlencode({"userid": user_id, "appid": MARKETPLACE_APP_ID})
    request = Request(
        f"{ENTITLEMENT_ENDPOINT}?{query}",
        headers={"Accept": "application/json", "User-Agent": "MathCurve/26.2.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
        return LicenseStatus(False, "connection_error", "Unable to contact Autodesk Marketplace to verify your license.")

    return _parse_entitlement(payload, user_id)


def developer_flag_path() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "MathCurve2", DEV_MODE_FLAG_NAME)


def developer_mode_requested() -> bool:
    if os.environ.get(DEV_MODE_ENV, "").strip() == "1":
        return True
    try:
        return os.path.isfile(developer_flag_path())
    except OSError:
        return False


def is_marketplace_install(addin_dir: str = "") -> bool:
    normalized = os.path.abspath(addin_dir or ADDIN_DIR).replace("\\", "/").lower()
    return "/applicationplugins/" in normalized + "/"


def developer_mode_enabled(addin_dir: str = "") -> bool:
    return developer_mode_requested() and not is_marketplace_install(addin_dir)


def developer_diagnostics() -> str:
    """Hint shown only for copies outside the Marketplace install, to explain why the check ran."""
    if is_marketplace_install():
        return ""
    return (
        f"Running from a development folder: {ADDIN_DIR}. "
        f"Developer mode is OFF ({DEV_MODE_ENV}={os.environ.get(DEV_MODE_ENV, '(not set)')}; "
        f"flag file {developer_flag_path()} not found)."
    )


def check_license(app: Any) -> LicenseStatus:
    """Verify this signed-in Fusion user with Autodesk's Marketplace service.

    Marketplace owns the 30-day trial and paid entitlement state. This add-in
    never starts, extends, or caches a local license state.
    """
    if developer_mode_enabled():
        return LicenseStatus(True, "developer", "Developer mode: Marketplace license check skipped.")

    user_id = _get_fusion_user_id(app)
    if not user_id:
        return LicenseStatus(
            False,
            "signed_out",
            "Sign in to Fusion with your Autodesk account to verify the Math Curve license.",
        )

    return _request_entitlement(user_id)
