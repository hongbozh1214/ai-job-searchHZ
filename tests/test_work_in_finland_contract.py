"""Selected Work in Finland rules and synthetic downstream contract; no network."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_SKILL = REPO_ROOT / ".claude/skills/job-scraper/SKILL.md"


class WorkInFinlandFallbackTests(unittest.TestCase):
    """Rule review and synthetic contract replay; not a collector or agent run."""

    def section(self):
        return SCRAPER_SKILL.read_text(encoding="utf-8").split(
            "#### 1d. Selected Work in Finland structured fallback", 1
        )[1].split("### Step 2:", 1)[0]

    def test_entry_access_and_failure_contract(self):
        text = " ".join(self.section().split())
        for required in [
            "GET https://www.workinfinland.com/api/jobs/?limit=6&page=1",
            "real strict checker to the exact URL", "without following redirects",
            "at most one page", "nonnegative integer", "credential-bearing URLs",
            "nonempty page has `partial`", "empty page with nonzero total is `unknown`",
            "`parse_failed`", "stop without retry", "not a full-market check",
            "clears the cards and counts to zero", "date or stable ID",
            "`expireDate` is not publication date", "mechanism=company_pages_cli_source",
            "Step 2's existing batched lookup", "explicit temporary state/tracker paths",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_rule_mapping_through_real_state_cli_with_isolated_history(self):
        # Deliberately synthetic: actual network capture retained schema/hashes,
        # not the original titles or employer values. Never call this real replay.
        mapping = dict(re.findall(
            r"^\| (title|company|location|url|date) \| ([A-Za-z.]+) \|$",
            self.section(), re.MULTILINE,
        ))
        self.assertEqual(set(mapping), {"title", "company", "location", "url", "date"})
        raw = {"title": "Synthetic scientist", "employer": {"name": "Fixture Ltd", "city": "Espoo"},
               "externalUrl": "https://jobs.example.test/role?jobId=123456", "expireDate": "2099-01-01"}
        job = {}
        for field, path in mapping.items():
            value = raw
            if path == "null":
                value = None
            else:
                for key in path.split("."):
                    value = value[key]
            job[field] = value
        self.assertIsNone(job["date"])
        self.assertEqual(job["url"], raw["externalUrl"])
        self.assertNotIn("id", job)
        job.update(market="finland", status="new", source="cli",
                   portal="work-in-finland", posted_date=job["date"], deadline=None)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, tracker, batch = root / "seen.json", root / "tracker.csv", root / "input.json"
            state.write_text('{"seen": {}}', encoding="utf-8")
            tracker.write_text("company,role,source\n", encoding="utf-8")
            batch.write_text(json.dumps([job]), encoding="utf-8")

            def call(command):
                p = subprocess.run([
                    sys.executable, "-B", str(REPO_ROOT / "tools/scrape_state.py"), command,
                    "--state", str(state), "--tracker", str(tracker), "--input", str(batch),
                ], capture_output=True, text=True, check=True)
                return json.loads(p.stdout)

            self.assertEqual(call("lookup")[0]["decision"], "new")
            self.assertEqual(len(call("add")["added"]), 1)
            saved = json.loads(state.read_text())["seen"]
            row = next(iter(saved.values()))
            self.assertIsNone(row["posted_date"])
            self.assertIsNone(row["deadline"])
            self.assertEqual(row["url"], raw["externalUrl"])
            self.assertEqual(row["market"], "finland")
            self.assertEqual(row["source"], "cli")
            # Different visible title at the same URL must not create a duplicate.
            renamed = {**job, "title": "Synthetic renamed role"}
            batch.write_text(json.dumps([renamed]), encoding="utf-8")
            before = state.read_bytes()
            self.assertEqual(call("lookup")[0]["decision"], "seen_url")
            self.assertEqual(state.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
