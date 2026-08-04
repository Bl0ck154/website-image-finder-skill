from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import image_search  # noqa: E402
from image_search import (  # noqa: E402
    DdgsSearchBatch,
    ddgs_backend_mismatch_error,
    detect_ddgs_actual_sources,
    make_candidate,
)


class FakeEngine:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeClient:
    def __init__(self, engine_name: str | None = None) -> None:
        self._engines_cache = {} if engine_name is None else {object: FakeEngine(engine_name)}


class FakeSession:
    def close(self) -> None:
        pass


class DdgsBackendTests(unittest.TestCase):
    def candidate(self):
        return make_candidate(
            "ddgs",
            "robin",
            1,
            {
                "title": "Robin",
                "image": "https://example.com/robin.jpg",
                "thumbnail": "https://example.com/robin-small.jpg",
                "url": "https://example.com/robin",
                "source": "example.com",
                "width": 1200,
                "height": 800,
            },
        )

    def test_runtime_engine_wins_over_result_site_source(self) -> None:
        raw = [{"source": "Pixabay"}, {"source": "Bing"}]
        actual = detect_ddgs_actual_sources(FakeClient("duckduckgo"), raw)
        self.assertEqual(actual, ["DuckDuckGo"])

    def test_result_source_is_checked_when_runtime_engine_is_unavailable(self) -> None:
        actual = detect_ddgs_actual_sources(FakeClient(), [{"source": "DuckDuckGo"}])
        self.assertEqual(actual, ["DuckDuckGo"])

    def test_explicit_bing_mismatch_has_honest_error(self) -> None:
        message = ddgs_backend_mismatch_error("bing", "9.14.4", ["DuckDuckGo"])
        self.assertEqual(
            message,
            "Requested DDGS backend 'bing', but DDGS 9.14.4 returned\n"
            "DuckDuckGo results. This DDGS version does not provide a working\n"
            "Bing Images backend.",
        )

    def test_matching_explicit_backend_is_accepted(self) -> None:
        self.assertIsNone(ddgs_backend_mismatch_error("bing", "10.0.0", ["Bing"]))

    def test_auto_never_claims_a_requested_backend(self) -> None:
        self.assertIsNone(ddgs_backend_mismatch_error("auto", "9.14.4", ["DuckDuckGo"]))

    def test_candidate_provider_does_not_use_requested_backend_or_result_site(self) -> None:
        candidate = self.candidate()
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.provider, "ddgs-images")
        self.assertEqual(candidate.source_label, "example.com")

    def test_cli_writes_manifest_and_fails_on_explicit_backend_mismatch(self) -> None:
        batch = DdgsSearchBatch([self.candidate()], "9.14.4", "bing", ["DuckDuckGo"])
        with tempfile.TemporaryDirectory() as root, mock.patch.object(image_search, "create_session", return_value=FakeSession()), mock.patch.object(image_search, "search_ddgs", return_value=batch):
            argv = [
                "image_search.py",
                "robin",
                "--root",
                root,
                "--provider",
                "ddgs",
                "--ddgs-backend",
                "bing",
                "--batch-size",
                "0",
                "--out",
                ".image-search/test",
            ]
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = image_search.main()

            self.assertEqual(exit_code, 2)
            self.assertIn("Requested backend: bing", stdout.getvalue())
            self.assertIn("Actual source: DuckDuckGo", stdout.getvalue())
            self.assertIn(
                "Requested DDGS backend 'bing', but DDGS 9.14.4 returned\n"
                "DuckDuckGo results. This DDGS version does not provide a working\n"
                "Bing Images backend.",
                stderr.getvalue(),
            )
            manifest = json.loads((Path(root) / ".image-search" / "test" / "results-cache.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["ddgs_version"], "9.14.4")
            self.assertEqual(manifest["requested_backend"], "bing")
            self.assertEqual(manifest["actual_sources"], ["DuckDuckGo"])

    def test_cli_auto_uses_neutral_ddgs_wording(self) -> None:
        batch = DdgsSearchBatch([self.candidate()], "9.14.4", "auto", ["DuckDuckGo"])
        with tempfile.TemporaryDirectory() as root, mock.patch.object(image_search, "create_session", return_value=FakeSession()), mock.patch.object(image_search, "search_ddgs", return_value=batch):
            argv = [
                "image_search.py",
                "robin",
                "--root",
                root,
                "--provider",
                "ddgs",
                "--ddgs-backend",
                "auto",
                "--batch-size",
                "0",
                "--out",
                ".image-search/test",
            ]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                exit_code = image_search.main()

            self.assertEqual(exit_code, 0)
            self.assertIn(
                "DDGS image search using the backends available in the installed DDGS version.",
                stdout.getvalue(),
            )


if __name__ == "__main__":
    unittest.main()
