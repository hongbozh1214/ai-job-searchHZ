"""Application slugs must be fixed before documents are written."""

import csv
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools import application_key


HEADER = ("date", "company", "sector", "role", "role_type", "channel", "status",
          "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
          "source", "deadline")


class ApplicationSlugTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "documents/applications").mkdir(parents=True)

    def rows(self, *entries):
        with (self.root / "job_search_tracker.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows({"company": "Acme", "role": "Engineer", **row} for row in entries)

    def choose(self, url="https://example.test/job/1", market="europe"):
        return application_key.choose(self.root, "Acme", "Engineer", url,
                                      market, date(2026, 9, 27))

    def test_a_closed_application_gets_a_distinct_dated_attempt(self):
        self.rows({"status": "rejected", "source": "https://example.test/job/1",
                   "notes": "posting_key:acme_engineer"})
        old_archive = self.root / "documents/applications/acme_engineer"
        old_archive.mkdir()
        (old_archive / "job_posting.md").write_text("original", encoding="utf-8")
        new = self.choose()
        self.assertEqual(new, {"slug": "acme_engineer-attempt-20260927", "action": "new_attempt"})
        self.assertEqual((old_archive / "job_posting.md").read_text(encoding="utf-8"), "original")
        (self.root / "documents/applications" / new["slug"]).mkdir()
        self.assertEqual(self.choose()["slug"], "acme_engineer-attempt-20260927-2")

    def test_refresh_open_row_reuses_its_marker_but_not_a_closed_archive(self):
        self.rows({"status": "applied", "source": "https://example.test/job/1",
                   "notes": "posting_key:acme_engineer-123"})
        self.assertEqual(self.choose(), {"slug": "acme_engineer-123", "action": "refresh_open"})
        self.rows({"status": "rejected", "source": "https://example.test/job/1"},
                  {"status": "drafted", "source": "https://example.test/job/1"})
        with self.assertRaisesRegex(ValueError, "share an archive"):
            self.choose()

    def test_distinct_urls_keep_distinct_archives(self):
        self.rows({"status": "applied", "source": "https://example.test/job/1"})
        second = self.choose("https://example.test/job/2")
        self.assertEqual(second["action"], "new_posting")
        self.assertNotEqual(second["slug"], "acme_engineer")

    def test_unknown_archives_and_invalid_markers_fail_closed(self):
        (self.root / "documents/applications/acme_engineer").mkdir()
        with self.assertRaisesRegex(ValueError, "unverified provenance"):
            self.choose()
        self.rows({"status": "drafted", "source": "https://example.test/job/1",
                   "notes": "posting_key:../../other"})
        with self.assertRaisesRegex(ValueError, "safe single folder"):
            self.choose()

    def test_existing_custom_template_output_blocks_unrecorded_draft(self):
        output = self.root / "cv/main_acme_engineer.typ"
        output.parent.mkdir(parents=True)
        output.write_text("existing custom CV", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unverified provenance"):
            self.choose()

    def test_china_uses_the_existing_posting_key_shape(self):
        self.assertEqual(self.choose(market="china")["slug"], "acme_engineer")

    def test_cli_reports_decision_without_writing(self):
        proc = subprocess.run([sys.executable, str(Path(application_key.__file__)),
                               "--company", "Acme", "--role", "Engineer", "--root", str(self.root)],
                              capture_output=True, text=True, check=True)
        self.assertIn('"action": "new_posting"', proc.stdout)
        self.assertFalse((self.root / "job_search_tracker.csv").exists())
