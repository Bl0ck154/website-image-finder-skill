"""HTTP errors and provider circuit-breaker regressions; no external requests."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import image_search
import search_providers
from common import SkillError


class FakeResponse:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
    def json(self):
        raise ValueError("HTML body")


class ProviderStatusTests(unittest.TestCase):
    def test_429_is_reported_before_json_parse(self):
        for provider in ["Openverse", "Wikimedia"]:
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(search_providers.ProviderTemporarilyUnavailable, "429"):
                    search_providers.check_search_response(
                        FakeResponse(429, {"Retry-After": "180"}), provider
                    )

    def test_503_is_transient_and_400_is_invalid_request(self):
        with self.assertRaises(search_providers.ProviderTemporarilyUnavailable):
            search_providers.check_search_response(FakeResponse(503), "Openverse")
        with self.assertRaises(SkillError) as e:
            search_providers.check_search_response(FakeResponse(400), "Openverse")
        self.assertNotIsInstance(e.exception, search_providers.ProviderTemporarilyUnavailable)

    def test_untrusted_retry_after_is_not_echoed(self):
        with self.assertRaises(search_providers.ProviderTemporarilyUnavailable) as e:
            search_providers.check_search_response(
                FakeResponse(429, {"Retry-After": "https://evil.invalid/?token=secret"}), "Openverse"
            )
        self.assertNotIn("evil.invalid", str(e.exception))

    def test_openverse_http_error_is_checked_before_decoding(self):
        response = FakeResponse(429)
        session = mock.Mock()
        session.get.return_value = response
        with self.assertRaises(search_providers.ProviderTemporarilyUnavailable):
            image_search.search_openverse(
                session, "landscape", 2, 1, "any", "any", "any",
                "active", "any", "any", "any"
            )
        self.assertEqual(session.get.call_args.kwargs["timeout"], (5, 12))


class CircuitBreakerTests(unittest.TestCase):
    def run_search(self, *, license_filter="any", page_count=3, error=None):
        if error is None:
            error = search_providers.ProviderTemporarilyUnavailable("Openverse HTTP 429")
        Wikimedia = image_search.make_candidate("ddgs", "clouds", 1, {
            "image": "https://images.example.org/sky.jpg",
            "url": "https://example.org/sky", "title": "sky",
            "width": 1100, "height": 800
        })
        with tempfile.TemporaryDirectory() as folder:
            args = [
                "image_search.py", "clouds", "--root", folder,
                "--out", ".image-search/test", "--batch-size", "0",
                "--pages", str(page_count), "--reuse-cache-hours", "0",
                "--license", license_filter,
            ]
            with mock.patch.object(sys, "argv", args), \
                 mock.patch.object(image_search, "provider_order",
                                   return_value=(["openverse"] if license_filter != "any"
                                                 else ["openverse", "wikimedia"])), \
                 mock.patch.object(image_search, "create_session", return_value=mock.MagicMock()), \
                 mock.patch.object(image_search, "search_openverse", side_effect=error) as blocked, \
                 mock.patch.object(image_search, "search_wikimedia", return_value=[Wikimedia]) as backup, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = image_search.main()
            payload = json.loads(
                (Path(folder)/".image-search/test/results-cache.json").read_text()
            )
            return exit_code, payload, blocked.call_count, backup.call_count

    def test_transient_failure_skips_retries_and_uses_compatible_fallback(self):
        rc, payload, failures, backups = self.run_search()
        self.assertEqual(rc, 0)
        self.assertEqual(failures, 1)
        self.assertEqual(backups, 3)
        self.assertEqual(payload["metrics"]["provider_calls"],
                         {"openverse": 1, "wikimedia": 3})
        self.assertTrue(any("skipped remaining requests" in w for w in payload["warnings"]))

    def test_license_restriction_never_falls_back_to_unverified_provider(self):
        rc, payload, failures, backups = self.run_search(license_filter="commercial")
        self.assertEqual(rc, 1)
        self.assertEqual(failures, 1)
        self.assertEqual(backups, 0)
        self.assertEqual(payload["metrics"]["provider_calls"], {"openverse": 1})

    def test_bad_parameter_error_is_not_a_transient_provider_failure(self):
        rc, payload, failures, backups = self.run_search(
            license_filter="commercial", error=SkillError("Unsupported Openverse filter")
        )
        self.assertEqual(rc, 1)
        self.assertEqual(failures, 3)
        self.assertEqual(backups, 0)


if __name__ == "__main__":
    unittest.main()
