"""Focused tests for the Marketplace Entitlement API integration."""

import importlib.util
import json
import pathlib
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError


MODULE_PATH = pathlib.Path(__file__).parents[1] / "license_manager.py"
SPEC = importlib.util.spec_from_file_location("license_manager", MODULE_PATH)
license_manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = license_manager
SPEC.loader.exec_module(license_manager)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeApp:
    userId = "FUSION-USER-123"


class LicenseManagerTests(unittest.TestCase):
    def test_entitlement_request_uses_official_endpoint_and_ids(self):
        payload = {
            "UserId": FakeApp.userId,
            "AppId": license_manager.MARKETPLACE_APP_ID,
            "IsValid": True,
            "Message": "Ok",
        }
        with patch.object(license_manager, "urlopen", return_value=FakeResponse(payload)) as request:
            status = license_manager.check_license(FakeApp())

        self.assertTrue(status.allowed)
        url = request.call_args.args[0].full_url
        self.assertIn("https://apps.autodesk.com/webservices/checkentitlement?", url)
        self.assertIn("userid=FUSION-USER-123", url)
        self.assertIn(f"appid={license_manager.MARKETPLACE_APP_ID}", url)

    def test_invalid_entitlement_blocks_use(self):
        status = license_manager._parse_entitlement(
            {
                "UserId": FakeApp.userId,
                "AppId": license_manager.MARKETPLACE_APP_ID,
                "IsValid": False,
                "Message": "Ok",
            },
            FakeApp.userId,
        )
        self.assertFalse(status.allowed)
        self.assertEqual(status.mode, "not_entitled")

    def test_connection_failure_blocks_use_without_a_local_grace_cache(self):
        with patch.object(license_manager, "urlopen", side_effect=URLError("offline")):
            status = license_manager.check_license(FakeApp())

        self.assertFalse(status.allowed)
        self.assertEqual(status.mode, "connection_error")


if __name__ == "__main__":
    unittest.main()
