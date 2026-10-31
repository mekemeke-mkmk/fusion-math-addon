"""Autodesk Design and Make Marketplace entitlement checks for Math Curve."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# This is the Marketplace ID assigned to the Math Curve 2 preview submission.
MARKETPLACE_APP_ID = "1343581627431012464"
ENTITLEMENT_ENDPOINT = "https://apps.autodesk.com/webservices/checkentitlement"


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


def check_license(app: Any) -> LicenseStatus:
    """Verify this signed-in Fusion user with Autodesk's Marketplace service.

    Marketplace owns the 30-day trial and paid entitlement state. This add-in
    never starts, extends, or caches a local license state.
    """
    user_id = _get_fusion_user_id(app)
    if not user_id:
        return LicenseStatus(
            False,
            "signed_out",
            "Sign in to Fusion with your Autodesk account to verify the Math Curve license.",
        )

    return _request_entitlement(user_id)
