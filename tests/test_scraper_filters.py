import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "scraper_enhanced",
    ROOT / "kbid-scraper" / "scraper_enhanced.py",
)
SCRAPER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRAPER_MODULE)
KBidScraperFixed = SCRAPER_MODULE.KBidScraperFixed


class ScraperLotFilterTests(unittest.TestCase):
    def setUp(self):
        profiles = json.loads((ROOT / "kbid-scraper" / "category_profiles.json").read_text(encoding="utf-8"))
        profile = profiles["profit-all-in-one"]
        self.scraper = KBidScraperFixed.__new__(KBidScraperFixed)
        self.scraper.include_category_ids = set(profile["include_category_ids"])
        self.scraper.exclude_category_ids = set(profile["exclude_category_ids"])
        self.scraper.exclude_lot_terms = self.scraper.normalize_lot_terms(profile["exclude_lot_terms"])

    def test_major_appliances_category_is_excluded(self):
        self.assertFalse(self.scraper.category_allowed(["5", "34"]))

    def test_miscategorized_furniture_and_appliances_are_excluded(self):
        blocked = (
            ("Midwest Mobile Cafeteria Table", "Commercial & Industrial > Restaurant Equipment"),
            ("Cabinet on wheels with key", "Commercial & Industrial > Office Equipment"),
            ("Frigidaire air conditioning unit", "Technology > Electronics"),
        )
        for title, category in blocked:
            with self.subTest(title=title):
                self.assertFalse(self.scraper.lot_allowed(title, category))

    def test_non_furniture_tool_remains_allowed(self):
        self.assertTrue(
            self.scraper.lot_allowed(
                "Milwaukee M18 Fuel Impact Wrench",
                "Household & Estate > Power Tools/Shop Equipment",
            )
        )


if __name__ == "__main__":
    unittest.main()
