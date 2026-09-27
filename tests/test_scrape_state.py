"""The compact /scrape helpers must preserve history and reject ambiguous writes."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import portal_catalog  # noqa: E402
import scrape_state  # noqa: E402


class ScrapeStateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / "job_scraper/seen_jobs.json"
        self.tracker = self.root / "job_search_tracker.csv"

    def entry(self, url, title="Engineer", market="europe"):
        return {"company": "Acme", "title": title, "url": url, "market": market,
                "status": "new", "source": "websearch", "portal": "company-careers",
                "first_seen": "2026-09-27"}

    def test_lookup_and_add_only_emit_compact_results_and_preserve_rankings(self):
        original = self.entry("https://example.test/1")
        original.update(status="ranked", rank_score=93, gaps=["SQL"])
        self.state.parent.mkdir()
        self.state.write_text(json.dumps({"seen": {"legacy-name": original}, "extra": {"x": 1}}))
        found = scrape_state.run_lookup([self.entry("https://example.test/1", "Engineer (Remote)")],
                                         {"legacy-name": original}, {})
        self.assertEqual(found[0]["decision"], "seen_url")
        self.assertEqual(found[0]["key"], "legacy-name")
        self.assertNotIn("gaps", found[0])
        self.assertNotIn("rank_score", found[0])

        new = self.entry("https://example.test/2")
        selected = scrape_state.run_lookup([new], {"legacy-name": original}, {})[0]
        self.assertEqual(selected["decision"], "new")
        new["key"] = selected["key"]
        self.assertEqual(scrape_state.run_add([new], self.state, self.tracker), [selected["key"]])
        saved = json.loads(self.state.read_text())
        self.assertEqual(saved["seen"]["legacy-name"], original)
        self.assertEqual(saved["extra"], {"x": 1})
        self.assertEqual(scrape_state.run_lookup([new], saved["seen"], {})[0]["decision"], "seen_url")

    def test_batch_conflict_aborts_before_writing(self):
        a = self.entry("https://example.test/1")
        b = self.entry("https://example.test/1", "Renamed Engineer")
        with self.assertRaisesRegex(ValueError, "seen_url"):
            scrape_state.run_add([a, b], self.state, self.tracker)
        self.assertFalse(self.state.exists())

    def test_distinct_known_urls_same_title_get_different_keys(self):
        first = self.entry("https://example.test/1")
        key1 = scrape_state.run_lookup([first], {}, {})[0]["key"]
        scrape_state.run_add([first], self.state, self.tracker)
        second = self.entry("https://example.test/2")
        saved = json.loads(self.state.read_text())["seen"]
        key2 = scrape_state.run_lookup([second], saved, {})[0]["key"]
        self.assertNotEqual(key1, key2)
        self.assertEqual(scrape_state.run_add([second], self.state, self.tracker), [key2])

    def test_tracker_url_or_missing_url_prevents_duplicate(self):
        with self.tracker.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["company", "role", "source"])
            writer.writeheader()
            writer.writerow({"company": "Acme", "role": "Engineer", "source": "https://example.test/1/"})
        pair = scrape_state.tracker_pairs(self.tracker)
        self.assertEqual(scrape_state.run_lookup([self.entry("https://example.test/1")], {}, pair)[0]["decision"], "tracked")
        self.assertEqual(scrape_state.run_lookup([self.entry("https://example.test/2")], {}, pair)[0]["decision"], "new")
        self.assertEqual(scrape_state.run_lookup([self.entry("")], {}, pair)[0]["decision"], "tracked")

    def test_portal_history_uses_legacy_hostname_without_emitting_entries(self):
        seen = {"old": {"url": "https://jobs.example.test/role", "company": "Private"}}
        self.assertTrue(scrape_state.portal_history(seen, "example-search", "example.test"))
        self.assertFalse(scrape_state.portal_history(seen, "other", "another.test"))


class PortalCatalogTests(unittest.TestCase):
    def test_only_frontmatter_controls_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / ".agents/skills/demo"
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(
                "---\nname: demo\nenabled: false # intentionally disabled\n---\n"
                + "Long body with enabled: true\n" * 1000)
            self.assertEqual(portal_catalog.catalog(root), [
                {"name": "demo", "path": ".agents/skills/demo/SKILL.md", "enabled": False}])


if __name__ == "__main__":
    unittest.main()
