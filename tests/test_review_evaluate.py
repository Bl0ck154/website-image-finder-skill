"""Offline ranking and benchmark tests: do not call external search providers."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import common
import download_more
import evaluate_runs
import image_search
import review_candidates


def candidate(path: str, rank: int, title: str, width: int, height: int):
    obj = image_search.make_openverse_candidate(
        "blue sky lake", rank,
        {
            "url": f"https://images.example.com/{rank}.jpg",
            "foreign_landing_url": f"https://photos.example.com/{rank}",
            "title": title,
            "license": "by",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "width": width,
            "height": height,
        },
    )
    obj.local_file = path
    obj.status = "downloaded"
    obj.rank = rank
    return obj


class TechnicalReviewTests(unittest.TestCase):
    def test_measured_dimensions_aspect_and_reasons(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            Image.new("RGB", (1600, 900), "blue").save(directory / "wide.jpg")
            Image.new("RGB", (700, 700), "blue").save(directory / "square.jpg")
            wide = candidate("wide.jpg", 2, "blue sky lake view", 1600, 900)
            square = candidate("square.jpg", 1, "plain", 700, 700)
            report = review_candidates.build_review_report([square, wide], directory, "wide")

            self.assertEqual(report["scored_count"], 2)
            self.assertEqual(report["candidates"][0]["rank"], 2)
            self.assertGreater(report["candidates"][0]["technical_score"],
                               report["candidates"][1]["technical_score"])
            self.assertEqual(report["candidates"][0]["measured"]["width"], 1600)
            self.assertIn("matches requested aspect ratio", report["candidates"][0]["reasons"])
            self.assertFalse(report["candidates"][0]["visual_relevance_verified"])
            self.assertFalse(report["candidates"][0]["reuse_rights_verified"])

    def test_review_output_is_private_and_does_not_include_source_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            Image.new("RGB", (1000, 700), "green").save(directory / "test.png")
            item = candidate("test.png", 1, "lake", 1000, 700)
            item.source_page_url = "https://photos.example.com/?sensitive_token=private"
            path = review_candidates.save_review_report([item], directory, "any", 1)
            self.assertEqual(path.name, "review-batch-01.json")
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn("sensitive_token", contents)
            self.assertEqual(json.loads(contents)["scored_count"], 1)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            obj = candidate("../outside.jpg", 1, "bad", 1000, 700)
            with self.assertRaises(common.SkillError):
                review_candidates.technical_assessment(obj, directory, "wide")
            report = review_candidates.build_review_report([obj], directory, "wide")
            self.assertEqual(report["scored_count"], 0)
            self.assertEqual(len(report["errors"]), 1)

    def test_missing_files_get_explanations_without_failing_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            item = candidate("deleted.png", 1, "lake", 1000, 700)
            report = review_candidates.build_review_report([item], directory, "any")
            self.assertEqual(report["scored_count"], 0)
            self.assertEqual(len(report["errors"]), 1)


    def test_more_command_creates_batch_shortlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run_dir = directory / ".image-search" / "run"
            run_dir.mkdir(parents=True)
            saved = candidate("unused.png", 4, "lake", 900, 700)
            saved.status = "found"
            saved.local_file = None
            (run_dir / "results-cache.json").write_text(json.dumps({
                "tool": "website-image-finder",
                "schema_version": 3,
                "results": [vars(saved)],
                "download_settings": {
                    "min_width": 400, "min_height": 300, "max_mb": 12,
                    "max_pixels": 30_000_000, "near_duplicate_distance": 5,
                    "allow_first_frame": False,
                },
                "search_settings": {"orientation": "wide"},
            }), encoding="utf-8")

            def fake_download(session, candidates, out_dir, settings, count, attempts, retry_failed):
                Image.new("RGB", (900, 700), "blue").save(out_dir / "downloaded.png")
                candidates[0].status = "downloaded"
                candidates[0].local_file = "downloaded.png"
                candidates[0].batch = 1
                return [candidates[0]], 1

            with mock.patch.object(sys, "argv", [
                "download_more.py", "--root", str(directory),
                "--run", ".image-search/run", "--count", "1",
            ]), mock.patch.object(download_more, "create_session") as session, mock.patch.object(
                download_more, "download_next_batch", side_effect=fake_download
            ), contextlib.redirect_stdout(io.StringIO()):
                session.return_value.close.return_value = None
                self.assertEqual(download_more.main(), 0)
            report = json.loads((run_dir / "review-batch-01.json").read_text())
            self.assertEqual(report["scored_count"], 1)



class RunEvaluationTests(unittest.TestCase):
    def test_summary_preserves_old_caches_without_inventing_timing(self):
        cache = {"tool": "website-image-finder", "results": [{"status": "downloaded"}, {"status": "duplicate"}]}
        summary = evaluate_runs.summarize_cache(cache, "old")
        self.assertEqual(summary["downloaded"], 1)
        self.assertEqual(summary["duplicates"], 1)
        self.assertIsNone(summary["provider_calls"])
        self.assertIsNone(summary["elapsed_seconds"])
        self.assertFalse(summary["complete_metrics"])

    def test_evaluate_aggregate_and_no_sensitive_image_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run = directory / ".image-search" / "run"
            run.mkdir(parents=True)
            (run / "results-cache.json").write_text(json.dumps({
                "tool": "website-image-finder",
                "requested_provider": "auto",
                "providers_used": ["openverse"],
                "results": [
                    {"status": "downloaded", "image_url": "https://example.com/?secret=value"},
                    {"status": "failed"},
                ],
                "queries": ["lake"],
                "metrics": {"provider_calls": {"openverse": 1}, "elapsed_seconds": 1.25, "cache_reused": False},
                "warnings": ["provider blocked"],
            }), encoding="utf-8")
            runs = evaluate_runs.load_runs(directory, [".image-search/run"], 10)
            report = evaluate_runs.aggregate_summaries(runs)
            self.assertEqual(report["provider_calls_total"], {"openverse": 1})
            self.assertEqual(report["runs_with_download"], 1)
            self.assertEqual(report["median_elapsed_seconds"], 1.25)
            self.assertNotIn("secret=value", json.dumps(runs))
            self.assertEqual(runs[0]["run"], "run-01")

    def test_run_outside_private_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / ".image-search").mkdir()
            (directory / "external").mkdir()
            with self.assertRaises(common.SkillError):
                evaluate_runs.load_runs(directory, ["external"], 10)


class HttpRetryTests(unittest.TestCase):
    def test_transient_server_errors_are_retried_but_rate_limits_are_not(self):
        session = image_search.create_session()
        retry = session.adapters["https://"].max_retries
        self.assertIn(503, retry.status_forcelist)
        self.assertNotIn(429, retry.status_forcelist)
        self.assertEqual(retry.total, 2)
        self.assertEqual(retry.read, 0)
        session.close()


if __name__ == "__main__":
    unittest.main()
