"""China text applications get the authoritative recording rules without full /apply."""

import subprocess
import sys
import unittest
from pathlib import Path

from tools import apply_record


ROOT = Path(__file__).resolve().parent.parent


class ChinaTextApplyRouteTests(unittest.TestCase):
    def test_extractor_returns_only_the_canonical_tracker_archive_section(self):
        source = (ROOT / ".claude/commands/apply.md").read_text(encoding="utf-8")
        section = apply_record.record_section(source)
        self.assertTrue(section.startswith(apply_record.HEADING))
        self.assertIn("date,company,sector,role", section)
        self.assertIn("china_posting_key:<selected-slug>", section)
        self.assertIn("Archive the posting now", section)
        self.assertNotIn("### Application-Form Fields", section)
        self.assertNotIn("## Step 5: DRAFTER", section)
        self.assertLess(len(section.split()), len(source.split()) // 3)
        result = subprocess.run([sys.executable, "tools/apply_record.py"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), section)

    def test_fails_closed_if_shared_section_is_missing_or_unbounded(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            apply_record.record_section("## Other heading\nNo tracker")
        with self.assertRaisesRegex(ValueError, "no following heading"):
            apply_record.record_section(apply_record.HEADING + "\njob_search_tracker.csv job_posting.md")

    def test_router_text_and_full_modes_keep_required_gates(self):
        router = (ROOT / "skills/job-search/SKILL.md").read_text(encoding="utf-8")
        overlay = (ROOT / "markets/china/workflows/apply-job.md").read_text(encoding="utf-8")
        self.assertIn("resolve China output mode **before reading", router)
        self.assertIn("python3 tools/apply_record.py", router)
        self.assertIn("If the candidate\n  explicitly requests full CV and cover-letter files", router)
        self.assertIn("read the\nentire shared `/apply` workflow before drafting", overlay)
        for rule in ("resume_draft", "source_sha256", "china_text_pack:<relative-pack-path>",
                     "status: drafted", "documents/applications/<slug>/job_posting.md"):
            self.assertIn(rule, overlay)


if __name__ == "__main__":
    unittest.main()
