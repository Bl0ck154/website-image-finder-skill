"""The committed live-image demo must remain usable and properly credited."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from html.parser import HTMLParser

from PIL import Image


PROJECT = Path(__file__).resolve().parents[1]
DEMO = PROJECT / "examples" / "earth"


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "img":
            self.images.append(props)
        elif tag == "a":
            self.links.append(props.get("href", ""))


class RealDemoTests(unittest.TestCase):
    def test_real_image_has_expected_format_and_size(self):
        photo = DEMO / "assets" / "blue-marble.webp"
        self.assertTrue(photo.is_file())
        with Image.open(photo) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (1280, 640))
        self.assertLess(photo.stat().st_size, 149430)

    def test_example_page_is_local_and_credits_original(self):
        page = PageAssets()
        page.feed((DEMO / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(page.images), 1)
        image = page.images[0]
        self.assertEqual(image["src"], "assets/blue-marble.webp")
        self.assertTrue((DEMO / image["src"]).is_file())
        self.assertGreater(len(image["alt"]), 30)
        self.assertEqual((image["width"], image["height"]), ("1280", "640"))
        self.assertIn("https://commons.wikimedia.org/wiki/File:Blue_Marble_2002.jpg", page.links)
        self.assertIn("https://www.nasa.gov/nasa-brand-center/images-and-media/", page.links)

    def test_provenance_is_written_and_not_just_claimed(self):
        readme = (DEMO / "README.md").read_text(encoding="utf-8")
        self.assertIn("NASA Goddard Space Flight Center", readme)
        self.assertIn("public domain", readme)
        self.assertIn("149,430 bytes", readme)
        self.assertIn("105,736 bytes", readme)
        self.assertIn("ed48d6b8214261080a24d2760200dfe3cac60fb5b25e09de54fa1362e3265419", readme)


if __name__ == "__main__":
    unittest.main()
