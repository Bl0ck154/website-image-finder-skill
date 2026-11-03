"""Offline tests for provider selection and safe website asset finalization."""
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
import finalize_image
import image_search


class Response:
    status_code = 200
    def __init__(self, data):
        self.data = data
    def json(self):
        return self.data


class Session:
    def __init__(self, data=None):
        self.response = Response(data or {"results": []})
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response
    def close(self):
        pass


def result():
    return {
        "title": "Office", "url": "https://example.com/office.jpg",
        "thumbnail": "https://example.com/thumb.jpg",
        "foreign_landing_url": "https://example.com/office",
        "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "width": 1200, "height": 800,
    }


class ProviderTests(unittest.TestCase):
    def test_auto_region_not_forced_to_lithuania(self):
        session = Session({"images_results": []})
        self.assertEqual(image_search.region_to_google("auto"), (None, None))
        image_search.search_serpapi(
            session, "office", "dummy", 10, "auto", 1, "any",
            "any", "any", "active", "any", "any", "any",
        )
        params = session.calls[0][1]["params"]
        self.assertNotIn("gl", params)
        self.assertNotIn("hl", params)

    def test_openverse_has_license_and_commercial_filter(self):
        session = Session({"results": [result()]})
        found = image_search.search_openverse(
            session, "office", 10, 1, "any", "any", "commercial-modify",
            "active", "any", "any", "any",
        )
        self.assertEqual(found[0].provider, "openverse")
        self.assertEqual(found[0].license_tag, "by")
        self.assertEqual(session.calls[0][1]["params"]["license_type"], "commercial,modification")

    def test_openverse_rejects_unsupported_filter(self):
        session = Session()
        with self.assertRaises(common.SkillError):
            image_search.search_openverse(
                session, "x", 10, 1, "any", "photo", "any", "active", "any", "any", "any"
            )
        self.assertEqual(session.calls, [])

    def test_ddgs_does_not_pretend_to_filter_creative_commons(self):
        with self.assertRaises(common.SkillError):
            image_search.ddgs_license("creative-commons")

    def test_auto_falls_back_from_ddgs_failure(self):
        candidate = image_search.make_openverse_candidate("office", 1, result())
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(image_search, "create_session", return_value=Session()), \
             mock.patch.object(image_search, "search_ddgs", side_effect=RuntimeError("blocked")), \
             mock.patch.object(image_search, "search_openverse", return_value=[candidate]), \
             mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "", "SERPAPI_KEY": ""}), \
             mock.patch.object(sys, "argv", [
                 "image_search.py", "office", "--root", root,
                 "--batch-size", "0", "--out", ".image-search/test",
             ]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = image_search.main()
            cache = json.loads((Path(root) / ".image-search/test/results-cache.json").read_text())
        self.assertEqual(rc, 0)
        self.assertIn("openverse", cache["providers_used"])

    def test_search_with_no_downloaded_images_is_not_success(self):
        candidate = image_search.make_openverse_candidate("office", 1, result())
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(image_search, "create_session", return_value=Session()), \
             mock.patch.object(image_search, "search_openverse", return_value=[candidate]), \
             mock.patch.object(image_search, "download_next_batch", return_value=([], 1)), \
             mock.patch.object(sys, "argv", [
                 "image_search.py", "office", "--root", root,
                 "--provider", "openverse", "--batch-size", "1",
                 "--max-attempts", "1", "--out", ".image-search/test",
             ]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = image_search.main()
        self.assertEqual(rc, 3)

    def test_retry_small_candidate(self):
        candidate = image_search.make_openverse_candidate("office", 1, result())
        candidate.status = "skipped-small"
        settings = {
            "min_width": 200, "min_height": 100, "max_mb": 12,
            "max_pixels": 30_000_000, "near_duplicate_distance": 5,
            "allow_first_frame": False,
        }
        states = []
        def fake_download(session, item, out, width, height, *args):
            states.append((item.status, width, height))
            item.status = "downloaded"
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            image_search, "download_candidate", side_effect=fake_download
        ):
            found, attempts = image_search.download_next_batch(
                Session(), [candidate], Path(root), settings, 1, 1, retry_failed=True
            )
        self.assertEqual(states, [("found", 200, 100)])
        self.assertEqual((len(found), attempts), (1, 1))


    def test_reuse_cached_search_across_runs(self):
        candidate = image_search.make_openverse_candidate("office", 1, result())
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(image_search, "create_session", return_value=Session()), \
             mock.patch.object(image_search, "search_openverse", return_value=[candidate]) as provider, \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            first = [
                "image_search.py", "office", "--provider", "openverse",
                "--root", root, "--batch-size", "0", "--out", ".image-search/first",
            ]
            second = [
                "image_search.py", "office", "--provider", "openverse",
                "--root", root, "--batch-size", "0", "--out", ".image-search/second",
                "--reuse-cache-hours", "24",
            ]
            with mock.patch.object(sys, "argv", first):
                self.assertEqual(image_search.main(), 0)
            with mock.patch.object(sys, "argv", second):
                self.assertEqual(image_search.main(), 0)
            self.assertEqual(provider.call_count, 1)
            cache = json.loads((Path(root) / ".image-search/second/results-cache.json").read_text())
            self.assertEqual(len(cache["results"]), 1)
            self.assertEqual(cache["results"][0]["status"], "found")

    def test_paid_serpapi_request_cap_rejects_expensive_search(self):
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "dummy-value"}), \
             mock.patch.object(image_search, "create_session") as client, \
             mock.patch.object(sys, "argv", [
                 "image_search.py", "office", "--extra-query", "garden",
                 "--root", root, "--provider", "serpapi", "--batch-size", "0", "--pages", "3",
             ]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(image_search.main(), 2)
            client.assert_not_called()

    def test_no_fallback_uses_only_selected_provider(self):
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "", "SERPAPI_KEY": ""}), \
             mock.patch.object(image_search, "create_session", return_value=Session()), \
             mock.patch.object(image_search, "search_ddgs", side_effect=RuntimeError("blocked")), \
             mock.patch.object(image_search, "search_openverse") as fallback, \
             mock.patch.object(sys, "argv", [
                 "image_search.py", "office", "--root", root, "--batch-size", "0",
                 "--no-provider-fallback", "--out", ".image-search/test",
             ]), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(image_search.main(), 1)
            fallback.assert_not_called()


    def test_paid_provider_requires_explicit_selection(self):
        self.assertEqual(image_search.provider_order("auto", "any", False, ddgs_available=True),
                         ["ddgs", "openverse", "wikimedia"])
        self.assertEqual(image_search.provider_order("auto", "any", False, ddgs_available=False),
                         ["openverse", "wikimedia"])
        self.assertEqual(image_search.provider_order("auto", "any", True, ddgs_available=True),
                         ["ddgs"])
        self.assertEqual(image_search.provider_order("serpapi", "any", False), ["serpapi"])
        self.assertEqual(image_search.provider_order("auto", "commercial-modify", False),
                         ["openverse"])

    def test_existing_serpapi_key_does_not_trigger_paid_search(self):
        candidate = image_search.make_openverse_candidate("office", 1, result())
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.dict("os.environ", {"SERPAPI_API_KEY": "fake-paid-key"}), \
             mock.patch.object(image_search, "provider_order", return_value=["openverse"]), \
             mock.patch.object(image_search, "create_session", return_value=Session()), \
             mock.patch.object(image_search, "search_serpapi") as paid, \
             mock.patch.object(image_search, "search_openverse", return_value=[candidate]), \
             mock.patch.object(sys, "argv", [
                 "image_search.py", "office", "--root", root,
                 "--batch-size", "0", "--out", ".image-search/test",
             ]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(image_search.main(), 0)
            paid.assert_not_called()

    def test_wikimedia_commons_metadata(self):
        payload = {"query": {"pages": [{
            "index": 1, "title": "File:Lake photo.jpg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a1/lake.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Lake_photo.jpg",
                "mime": "image/jpeg", "width": 1600, "height": 1000,
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                },
            }],
        }]}}
        session = Session(payload)
        images = image_search.search_wikimedia(
            session, "lake", 10, 1, "wide", "any",
            "any", "active", "any", "any", "any",
        )
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].provider, "wikimedia-commons")
        self.assertEqual(images[0].license_tag, "CC BY-SA 4.0")
        self.assertEqual(images[0].source_domain, "commons.wikimedia.org")
        self.assertEqual(session.calls[0][1]["params"]["gsrnamespace"], 6)

    def test_wikimedia_rejects_license_claims_it_cannot_verify(self):
        with self.assertRaises(common.SkillError):
            image_search.search_wikimedia(
                Session(), "lake", 10, 1, "any", "any",
                "commercial-modify", "active", "any", "any", "any",
            )



class SafetyTests(unittest.TestCase):
    def test_private_provenance_when_finalizing_public_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / ".image-search/test"
            run.mkdir(parents=True)
            Image.new("RGB", (1000, 600), "#ffcc88").save(run / "original.webp", "WEBP")
            manifest = {"results": [{
                "id": "img-safe", "rank": 1, "status": "downloaded",
                "local_file": "original.webp",
                "image_url": "https://example.com/image.jpg?token=private",
                "source_page_url": "https://example.com/image",
            }]}
            (run / "results-cache.json").write_text(json.dumps(manifest))
            with mock.patch.object(sys, "argv", [
                "finalize_image.py", "--root", str(root),
                "--cache", ".image-search/test/results-cache.json",
                "--candidate", "1", "--output", "public/images/hero.webp",
            ]), contextlib.redirect_stdout(io.StringIO()):
                rc = finalize_image.main()
            self.assertEqual(rc, 0)
            self.assertTrue((root / "public/images/hero.webp").exists())
            self.assertFalse((root / "public/images/hero.webp.source.json").exists())
            private = root / ".image-search/provenance/public/images/hero.webp.source.json"
            self.assertTrue(private.exists())
            self.assertEqual(json.loads(private.read_text())["candidate_id"], "img-safe")

    def test_private_workdir_has_nested_gitignore(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            private = common.prepare_private_workdir(root)
            ignored = (private / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("*", ignored)
            self.assertIn("!.gitignore", ignored)
            self.assertEqual(common.prepare_private_workdir(root), private)

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            root.mkdir()
            with self.assertRaises(common.SkillError):
                common.resolve_under_root("../outside.jpg", root)

    def test_private_ips_rejected(self):
        for url in ["http://127.0.0.1/", "http://169.254.169.254/metadata",
                    "http://192.168.0.1/", "file:///etc/passwd"]:
            with self.subTest(url=url), self.assertRaises(common.SkillError):
                common.validate_remote_url_syntax(url)


if __name__ == "__main__":
    unittest.main()
