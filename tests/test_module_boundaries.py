"""Extracted modules must retain the original public helper interfaces."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candidate_model
import contact_sheet
import image_search
import search_cache
import search_providers


class ModuleBoundaryTests(unittest.TestCase):
    def test_candidate_identity(self):
        self.assertIs(image_search.Candidate, candidate_model.Candidate)
        self.assertIs(image_search.make_candidate, candidate_model.make_candidate)
        self.assertIs(image_search.make_openverse_candidate,
                      candidate_model.make_openverse_candidate)

    def test_provider_exports(self):
        self.assertIs(image_search.search_openverse, search_providers.search_openverse)
        self.assertIs(image_search.search_wikimedia, search_providers.search_wikimedia)
        self.assertIs(image_search.search_ddgs, search_providers.search_ddgs)

    def test_contact_and_cache_exports(self):
        self.assertIs(image_search.create_contact_sheet, contact_sheet.create_contact_sheet)
        self.assertIs(image_search.find_reusable_cache, search_cache.find_reusable_cache)
        self.assertIs(image_search.write_cache, search_cache.write_cache)
        self.assertEqual(search_cache.cache_summary([])["unique_results"], 0)


if __name__ == "__main__":
    unittest.main()
