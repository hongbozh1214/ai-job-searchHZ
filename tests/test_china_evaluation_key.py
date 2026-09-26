"""China evaluations cannot overwrite reports for another local JD."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import china_evaluation_key


class ChinaEvaluationKeyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.inbox = self.root / "markets/china/jobs/inbox"
        self.reports = self.root / "markets/china/jobs/evaluated"
        self.inbox.mkdir(parents=True)
        self.reports.mkdir()
        self.a = self.inbox / "one.md"
        self.b = self.inbox / "two.md"
        self.a.write_text("posting one", encoding="utf-8")
        self.b.write_text("posting two", encoding="utf-8")

    def key(self, path, url=""):
        return china_evaluation_key.choose(self.root, path, "Acme", "Engineer", url)

    def archive(self, key, source, url="not provided"):
        (self.reports / f"{key}.md").write_text(
            f"# Evaluation\n\n**Source:** markets/china/jobs/inbox/{source}\n**Source URL:** {url}\n",
            encoding="utf-8")

    def test_distinct_known_urls_receive_distinct_stable_paths(self):
        first = self.key(self.a, "https://example.test/jobs/1")
        self.archive(first, "one.md", "https://example.test/jobs/1")
        second = self.key(self.b, "https://example.test/jobs/2")
        self.assertNotEqual(first, second)
        self.assertEqual(second, self.key(self.b, "https://example.test/jobs/2"))
        self.archive(second, "two.md", "https://example.test/jobs/2")
        self.assertEqual(second, self.key(self.b, "https://example.test/jobs/2"))
        self.assertEqual(first, self.key(self.a, "https://example.test/jobs/1"))

    def test_two_url_less_local_jds_are_separate(self):
        first = self.key(self.a)
        self.archive(first, "one.md")
        second = self.key(self.b)
        self.assertNotEqual(first, second)
        self.archive(second, "two.md")
        self.assertEqual(second, self.key(self.b))

    def test_legacy_report_without_source_fails_closed(self):
        base = self.key(self.a)
        (self.reports / f"{base}.md").write_text("# Old report without source")
        with self.assertRaisesRegex(ValueError, "no source identity"):
            self.key(self.b)

    def test_inbox_symlink_to_other_checkout_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.inbox / "foreign.md").symlink_to(Path(outside) / "foreign.md")
            (Path(outside) / "foreign.md").write_text("other candidate")
            with self.assertRaisesRegex(ValueError, "file in the China inbox"):
                self.key(self.inbox / "foreign.md")

    def test_cli_returns_key_without_writing_report(self):
        proc = subprocess.run([sys.executable, str(Path(china_evaluation_key.__file__)),
                               "--source", str(self.a), "--company", "Acme", "--title", "Engineer",
                               "--root", str(self.root)], capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout.strip(), "acme_engineer")
        self.assertFalse(list(self.reports.iterdir()))
