"""Application slugs must be fixed before documents are written."""

import csv
import hashlib
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

    def test_china_existing_pack_can_resume_only_for_the_same_saved_jd(self):
        inbox = self.root / "markets/china/jobs/inbox"
        inbox.mkdir(parents=True)
        first = inbox / "first.md"
        other = inbox / "other.md"
        first.write_text("first", encoding="utf-8")
        other.write_text("other", encoding="utf-8")
        pack = self.root / "markets/china/jobs/evaluated/acme_engineer-application.md"
        pack.parent.mkdir(parents=True)
        digest = hashlib.sha256(first.read_bytes()).hexdigest()
        pack.write_text(f"# Draft\n**Source:** markets/china/jobs/inbox/first.md\n**Source SHA256:** {digest}\n", encoding="utf-8")
        decision = application_key.choose(self.root, "Acme", "Engineer", "https://example.test/job/1",
                                           "china", date(2026, 9, 27), first)
        self.assertEqual(decision, {"slug": "acme_engineer", "action": "resume_draft", "source_sha256": digest})
        first.write_text("changed JD", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JD content changed"):
            application_key.choose(self.root, "Acme", "Engineer", "https://example.test/job/1",
                                   "china", date(2026, 9, 27), first)
        with self.assertRaisesRegex(ValueError, "another saved JD"):
            application_key.choose(self.root, "Acme", "Engineer", "https://example.test/job/2",
                                   "china", date(2026, 9, 27), other)
        with self.assertRaisesRegex(ValueError, "cannot be verified"):
            self.choose(market="china")

    def test_china_interrupted_reapplication_keeps_its_dated_pack(self):
        inbox = self.root / "markets/china/jobs/inbox"
        inbox.mkdir(parents=True)
        jd = inbox / "job.md"
        jd.write_text("full JD", encoding="utf-8")
        self.rows({"status": "rejected", "source": "https://example.test/job/1",
                   "notes": "china_posting_key:acme_engineer"})
        pack = self.root / "markets/china/jobs/evaluated/acme_engineer-attempt-20260927-application.md"
        pack.parent.mkdir(parents=True)
        digest = hashlib.sha256(jd.read_bytes()).hexdigest()
        pack.write_text(f"# Draft\n**Source:** markets/china/jobs/inbox/job.md\n**Source SHA256:** {digest}\n", encoding="utf-8")
        decision = application_key.choose(self.root, "Acme", "Engineer", "https://example.test/job/1",
                                           "china", date(2026, 9, 27), jd)
        self.assertEqual(decision, {"slug": "acme_engineer-attempt-20260927", "action": "resume_draft", "source_sha256": digest})
        self.assertIn("# Draft", pack.read_text(encoding="utf-8"))

    def test_legacy_china_pack_requires_manual_review_before_resume(self):
        inbox = self.root / "markets/china/jobs/inbox"
        inbox.mkdir(parents=True)
        jd = inbox / "old.md"
        jd.write_text("complete JD", encoding="utf-8")
        pack = self.root / "markets/china/jobs/evaluated/acme_engineer-application.md"
        pack.parent.mkdir(parents=True)
        pack.write_text("**Source:** markets/china/jobs/inbox/old.md\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "review it before resuming"):
            application_key.choose(self.root, "Acme", "Engineer", "https://example.test/job/1",
                                   "china", date(2026, 9, 27), jd)

    def test_china_open_application_cannot_refresh_another_jd_pack(self):
        inbox = self.root / "markets/china/jobs/inbox"
        inbox.mkdir(parents=True)
        other = inbox / "other.md"
        other.write_text("other", encoding="utf-8")
        pack = self.root / "markets/china/jobs/evaluated/acme_engineer-application.md"
        pack.parent.mkdir(parents=True)
        pack.write_text("**Source:** markets/china/jobs/inbox/old.md\n", encoding="utf-8")
        self.rows({"status": "drafted", "source": "https://example.test/job/1",
                   "notes": "china_posting_key:acme_engineer"})
        with self.assertRaisesRegex(ValueError, "another saved JD"):
            application_key.choose(self.root, "Acme", "Engineer", "https://example.test/job/1",
                                   "china", date(2026, 9, 27), other)

    def test_cli_reports_decision_without_writing(self):
        proc = subprocess.run([sys.executable, str(Path(application_key.__file__)),
                               "--company", "Acme", "--role", "Engineer", "--root", str(self.root)],
                              capture_output=True, text=True, check=True)
        self.assertIn('"action": "new_posting"', proc.stdout)
        self.assertFalse((self.root / "job_search_tracker.csv").exists())
