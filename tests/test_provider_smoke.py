"""Offline checks that provider smoke tests never run on import or without --live."""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import provider_smoke


class SmokeToolTests(unittest.TestCase):
    def test_manual_opt_in_is_required(self):
        options = provider_smoke.parse_args([])
        with self.assertRaisesRegex(ValueError, "--live"):
            provider_smoke.check_options(options)

    def test_disallows_paid_provider(self):
        with mock.patch.object(sys, "argv", ["provider_smoke.py", "--live", "--provider", "serpapi"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    provider_smoke.parse_args()

    def test_deduplicates_provider_selection(self):
        with mock.patch.object(sys, "argv", [
            "provider_smoke.py", "--live", "--provider", "wikimedia", "--provider", "wikimedia"
        ]):
            self.assertEqual(provider_smoke.check_options(provider_smoke.parse_args()), ["wikimedia"])

    def test_bounded_maximums(self):
        with mock.patch.object(sys, "argv", [
            "provider_smoke.py", "--live", "--max-attempts", "100"
        ]):
            with self.assertRaisesRegex(ValueError, "1-10"):
                provider_smoke.check_options(provider_smoke.parse_args())

    def test_failed_ddgs_diagnostic_does_not_expose_error_text(self):
        with mock.patch.object(provider_smoke.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "Missing ddgs: https://external.test/private?token=secret"
            result = provider_smoke.run_provider(
                "ddgs", "mountain lake", 4, 2, 20,
                Path(__file__).resolve().parents[1] / "scripts" / "skill.py",
            )
        self.assertIn("optional DDGS dependency is missing", result["reason"])
        self.assertNotIn("token=", str(result))

    def test_transient_provider_failure_has_sanitized_explanation(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def fake_temp(*args, **kwargs):
                return contextlib.nullcontext(folder)
            def fake_subprocess(argv, **kwargs):
                cache = root / ".image-search" / "smoke"
                cache.mkdir(parents=True, exist_ok=True)
                (cache / "results-cache.json").write_text(json.dumps({
                    "warnings": ["openverse temporarily unavailable: skipped remaining requests"],
                    "summary": {"unique_results": 0, "downloaded_unique": 0},
                    "metrics": {"download_attempts": 0},
                }))
                return mock.Mock(returncode=1, stderr="secret query in remote error")
            with mock.patch.object(provider_smoke.tempfile, "TemporaryDirectory", side_effect=fake_temp), \
                 mock.patch.object(provider_smoke.subprocess, "run", side_effect=fake_subprocess), \
                 mock.patch.object(provider_smoke, "prepared_python", return_value=Path(sys.executable)):
                result = provider_smoke.run_provider(
                    "openverse", "a test", 3, 2, 20,
                    Path(__file__).resolve().parents[1] / "scripts" / "skill.py",
                )
        self.assertIn("temporarily unavailable", result["reason"])
        self.assertNotIn("secret query", str(result))

    def test_valid_report_after_mocked_provider_calls(self):
        with mock.patch.object(sys, "argv", [
            "provider_smoke.py", "--live", "--provider", "wikimedia"
        ]), mock.patch.object(provider_smoke, "run_provider", return_value={
            "provider": "wikimedia", "status": "passed", "unique_results": 4,
            "downloaded": 1, "download_attempts": 1, "finalized": True,
            "elapsed_seconds": 0.2,
        }) as run:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(provider_smoke.main(), 0)
            self.assertIn('"passed": 1', out.getvalue())
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
