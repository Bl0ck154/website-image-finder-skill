"""Regressions for image presets, fallback, image originals and pinned DNS transport."""
from __future__ import annotations

import contextlib
import io
import json
import socket
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
import safe_transport


class PresetTests(unittest.TestCase):
    def parse(self, *arguments):
        with mock.patch.object(sys, "argv", ["image_search.py", "test", *arguments]):
            args = image_search.parse_args()
        image_search.validate_args(args)
        return args

    def test_asset_preset_defaults(self):
        self.assertEqual(
            (self.parse("--asset-type", "logo").min_width,
             self.parse("--asset-type", "logo").min_height), (100, 60))
        self.assertEqual(
            (self.parse("--asset-type", "icon").min_width,
             self.parse("--asset-type", "icon").min_height), (64, 64))
        hero = self.parse("--asset-type", "hero")
        self.assertEqual((hero.min_width, hero.min_height, hero.orientation),
                         (1200, 600, "wide"))
        photo = self.parse()
        self.assertEqual((photo.min_width, photo.min_height, photo.orientation),
                         (800, 500, "any"))

    def test_explicit_flags_override_preset(self):
        args = self.parse("--asset-type", "hero", "--min-width", "512", "--orientation", "square")
        self.assertEqual((args.min_width, args.min_height, args.orientation),
                         (512, 600, "square"))

    def test_logos_not_skipped_due_to_photo_defaults(self):
        args = self.parse("--asset-type", "logo")
        candidate = image_search.make_candidate("ddgs", "logo", 1, {
            "image": "https://images.example.org/logo.png",
            "url": "https://example.org/logo", "title": "logo",
            "width": 256, "height": 256,
        })
        with tempfile.TemporaryDirectory() as folder:
            session = mock.MagicMock()
            with mock.patch.object(image_search, "origin_referer", return_value=None), \
                 mock.patch.object(image_search, "request_with_safe_redirects",
                                   side_effect=common.SkillError("simulated failed download")):
                image_search.download_candidate(
                    session, candidate, Path(folder), args.min_width, args.min_height,
                    12_000_000, 30_000_000, set(), [], 5, False,
                )
        self.assertEqual(candidate.status, "failed")
        self.assertNotEqual(candidate.status, "skipped-metadata-small")


class ProviderRecoveryTests(unittest.TestCase):
    def test_auto_uses_openverse_only_after_download_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            first = image_search.make_candidate("ddgs", "trees", 1, {
                "image": "https://images.example.org/invalid.jpg",
                "url": "https://example.org/source", "title": "trees",
                "width": 1200, "height": 800,
            })
            fallback = image_search.make_openverse_candidate("trees", 1, {
                "url": "https://images.example.org/backup.jpg",
                "foreign_landing_url": "https://example.org/backup",
                "title": "trees", "width": 1200, "height": 800,
            })
            batch = image_search.DdgsSearchBatch([first], "9.9", "auto", [])
            def fake_download(session, candidates, out_dir, settings, count, attempts, **kwargs):
                if fallback in candidates:
                    fallback.status = "downloaded"
                    fallback.local_file = "backup.webp"
                    fallback.batch = 1
                    return [fallback], 1
                first.status = "failed"
                return [], 2

            args = ["image_search.py", "trees", "--root", folder,
                    "--out", ".image-search/recovery", "--batch-size", "1",
                    "--max-attempts", "6", "--reuse-cache-hours", "0"]
            with mock.patch.object(sys, "argv", args), \
                 mock.patch.object(image_search, "provider_order",
                                   return_value=["ddgs", "openverse", "wikimedia"]), \
                 mock.patch.object(image_search, "search_ddgs", return_value=batch), \
                 mock.patch.object(image_search, "search_openverse", return_value=[fallback]) as second, \
                 mock.patch.object(image_search, "search_wikimedia") as third, \
                 mock.patch.object(image_search, "create_session", return_value=mock.MagicMock()), \
                 mock.patch.object(image_search, "download_next_batch", side_effect=fake_download), \
                 mock.patch.object(image_search, "write_batch_outputs", return_value=(None, None)), \
                 mock.patch.object(image_search, "save_review_report",
                                   return_value=Path(folder) / "review.json"), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(image_search.main(), 0)
            second.assert_called_once()
            third.assert_not_called()
            cache = json.loads((Path(folder) / ".image-search/recovery/results-cache.json").read_text())
            self.assertEqual(cache["metrics"]["provider_calls"],
                             {"ddgs": 1, "openverse": 1})
            self.assertEqual(cache["metrics"]["download_attempts"], 3)
            self.assertIn("openverse", cache["providers_used"])

    def test_run_outputs_must_stay_private(self):
        with tempfile.TemporaryDirectory() as root:
            arguments = ["image_search.py", "trees", "--root", root,
                         "--out", "public/images/cache"]
            with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(image_search.main(), 2)
            self.assertFalse((Path(root) / "public/images/cache").exists())

    def test_explicit_and_license_filtered_search_remain_restricted(self):
        self.assertEqual(image_search.provider_order("openverse", "any", False), ["openverse"])
        self.assertEqual(image_search.provider_order("auto", "commercial", False), ["openverse"])
        self.assertEqual(image_search.provider_order("serpapi", "any", False), ["serpapi"])


class PinnedTransportTests(unittest.TestCase):
    def test_numeric_ip_is_connected_with_original_hostname_preserved(self):
        with mock.patch.object(safe_transport.socket, "getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ]):
            adapter = safe_transport.pinned_adapter_class()()
            pool = adapter.get_connection("https://images.example.org/forest.jpg")
            self.assertEqual(pool.host, "images.example.org")
            with mock.patch("urllib3.util.connection.create_connection") as connect:
                pool._new_conn()._new_conn()
            self.assertEqual(connect.call_args.args[0], ("8.8.8.8", 443))
            pool.close()
            adapter.close()

    def test_private_and_mixed_dns_responses_are_blocked(self):
        for answers in [
            [("127.0.0.1", 443)],
            [("8.8.8.8", 443), ("192.168.0.10", 443)],
        ]:
            with self.subTest(answers=answers), mock.patch.object(
                safe_transport.socket, "getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", address)
                    for address in answers
                ],
            ):
                with self.assertRaises(common.SkillError):
                    safe_transport.resolve_public_address("https://images.example.org/photo.jpg")

    def test_proxy_transport_is_denied(self):
        adapter = safe_transport.pinned_adapter_class()()
        with self.assertRaises(common.SkillError):
            adapter.get_connection("https://images.example.org/",
                                   proxies={"https": "http://proxy.example.org:8080"})


class PreserveOriginalTests(unittest.TestCase):
    def test_prefers_original_in_final_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache_dir = root / ".image-search" / "run"
            (cache_dir / "originals").mkdir(parents=True)
            Image.new("RGB", (500, 300), "blue").save(
                cache_dir / "originals" / "image.original", format="PNG"
            )
            Image.new("RGB", (120, 80), "red").save(
                cache_dir / "preview.webp", format="WEBP"
            )
            candidate = {
                "id": "img-1", "rank": 1, "status": "downloaded",
                "local_file": "preview.webp",
                "original_file": "originals/image.original",
            }
            cache = cache_dir / "results-cache.json"
            cache.write_text(json.dumps({"results": [candidate]}))
            args = mock.Mock(input=None, cache=str(cache), candidate="1")
            source, _, _ = finalize_image.resolve_source(args, root)
            self.assertEqual(source.resolve(), (cache_dir / "originals" / "image.original").resolve())
            with Image.open(source) as image:
                self.assertEqual(image.size, (500, 300))
            candidate["original_file"] = "../../outside"
            cache.write_text(json.dumps({"results": [candidate]}))
            with self.assertRaises(common.SkillError):
                finalize_image.resolve_source(args, root)

    def test_download_keeps_uncompressed_source_bytes(self):
        image = Image.new("RGB", (640, 480), (80, 120, 150))
        raw = io.BytesIO()
        image.save(raw, "PNG")
        source_bytes = raw.getvalue()
        candidate = image_search.make_candidate("ddgs", "forest", 1, {
            "image": "https://images.example.org/photo.png",
            "url": "https://example.org/image",
            "title": "forest", "width": 640, "height": 480,
        })

        class Response:
            status_code = 200
            url = "https://images.example.org/photo.png"
            headers = {"content-type": "image/png", "content-length": str(len(source_bytes))}
            def iter_content(self, chunk_size):
                yield source_bytes
            def close(self):
                pass

        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(image_search, "request_with_safe_redirects",
                                   return_value=Response()), \
                 mock.patch.object(image_search, "validate_public_url",
                                   side_effect=lambda value: value), \
                 mock.patch.object(image_search, "origin_referer", return_value=None):
                image_search.download_candidate(
                    mock.Mock(), candidate, Path(folder), 400, 300,
                    3_000_000, 30_000_000, set(), [], 5, False
                )
            self.assertEqual(candidate.status, "downloaded")
            self.assertIsNotNone(candidate.original_file)
            self.assertEqual(
                (Path(folder) / candidate.original_file).read_bytes(), source_bytes
            )


if __name__ == "__main__":
    unittest.main()
