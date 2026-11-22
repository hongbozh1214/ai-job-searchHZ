"""Offline regression tests for missed LinkedIn/Indeed coverage."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.scrape_source_check import MARKET_COUNTRIES, check, no_duplicate_keys


ROOT = Path(__file__).resolve().parent.parent
EUROPE = MARKET_COUNTRIES["europe"]
FINLAND = MARKET_COUNTRIES["finland"]


def entries(countries, status="ran"):
    return {key: {"status": status, "evidence": "offline fixture"}
            for key in ("linkedin", *(f"indeed:{code}" for code in countries))}


class ScrapeSourceCheckTests(unittest.TestCase):
    def test_omission_fails_both_checks_for_both_markets(self):
        for countries, count in ((EUROPE, 7), (FINLAND, 2)):
            for phase in ("plan", "report"):
                with self.subTest(countries=countries, phase=phase):
                    result = check(phase, countries, {})
                    self.assertFalse(result["ok"])
                    self.assertEqual(len(result["errors"]), count)
                    self.assertIn("linkedin: missing", result["errors"])

    def test_planned_is_not_a_closeout_result(self):
        rows = entries(EUROPE, "planned")
        self.assertTrue(check("plan", EUROPE, rows)["ok"])
        self.assertFalse(check("report", EUROPE, rows)["ok"])

    def test_finland_scope_does_not_accept_europe(self):
        result = check("report", FINLAND, entries(FINLAND))
        self.assertEqual(result["expected"], ["linkedin", "indeed:FI"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["uncovered"], [])
        self.assertFalse(check("report", FINLAND, entries(EUROPE))["ok"])
        self.assertFalse(check("report", EUROPE, entries(FINLAND))["ok"])

    def test_explicit_skip_is_valid_but_not_covered(self):
        rows = entries(FINLAND)
        rows["linkedin"] = {"status": "skipped", "reason": "explicit_exclusion",
                            "evidence": "Fixture: explicitly excluded"}
        result = check("report", FINLAND, rows)
        self.assertTrue(result["ok"])
        self.assertEqual(result["uncovered"], ["linkedin"])

    def test_generic_access_verdict_cannot_skip_either_dedicated_list(self):
        for phase, status in (("plan", "planned"), ("report", "ran")):
            for countries in (EUROPE, FINLAND):
                for key in ("linkedin", f"indeed:{countries[0]}"):
                    with self.subTest(phase=phase, countries=countries, key=key):
                        rows = entries(countries, status)
                        rows[key] = {"status": "skipped", "reason": "access_unconfirmed",
                                     "evidence": "Generic access table"}
                        self.assertFalse(check(phase, countries, rows)["ok"])

    def test_missing_indeed_scope_is_a_source_specific_skip(self):
        rows = entries(FINLAND)
        reason = {"status": "skipped", "reason": "missing_indeed_scope",
                  "evidence": "Fixture: no approved country or method"}
        rows["indeed:FI"] = reason
        result = check("report", FINLAND, rows)
        self.assertTrue(result["ok"])
        self.assertEqual(result["uncovered"], ["indeed:FI"])
        rows["linkedin"] = reason
        self.assertFalse(check("report", FINLAND, rows)["ok"])

    def test_indeed_stop_accounts_for_remaining_countries(self):
        rows = entries(EUROPE)
        rows["indeed:GB"] = {"status": "failed", "evidence": "Fixture: HTTP 429"}
        self.assertIn("indeed:DK: call recorded after a failed Indeed call",
                      check("report", EUROPE, rows)["errors"])
        rows.update({f"indeed:{code}": {"status": "deferred", "reason": "prior_country_stop",
                                        "evidence": "Fixture: stop at GB"}
                     for code in EUROPE[1:]})
        result = check("report", EUROPE, rows)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["uncovered"]), 6)
        del rows["indeed:GB"]
        self.assertIn("indeed:DK: no earlier failed Indeed call for prior_country_stop",
                      check("report", EUROPE, rows)["errors"])

    def test_finland_deferred_requires_evidence(self):
        rows = entries(FINLAND)
        rows["indeed:FI"] = {"status": "deferred", "reason": "interrupted"}
        self.assertFalse(check("report", FINLAND, rows)["ok"])
        rows["indeed:FI"]["evidence"] = "Fixture: interrupted before request"
        self.assertEqual(check("report", FINLAND, rows)["uncovered"], ["indeed:FI"])

    def test_cannot_report_a_run_without_evidence(self):
        rows = entries(EUROPE)
        rows["indeed:DK"] = {"status": "ran", "evidence": " "}
        self.assertFalse(check("report", EUROPE, rows)["ok"])

    def test_narrower_scope_is_not_inferred_from_results(self):
        self.assertFalse(check("report", EUROPE, entries(("DE",)))["ok"])
        self.assertTrue(check("report", ("DE",), entries(("DE",)))["ok"])

    def test_rejects_duplicate_rows(self):
        with self.assertRaises(ValueError):
            json.loads('{"linkedin": {}, "linkedin": {}}', object_pairs_hook=no_duplicate_keys)

    def test_cli_missing_input_fails_and_finland_disallows_overrides(self):
        command = [sys.executable, "tools/scrape_source_check.py", "report",
                   "--market", "finland", "--input", "nonexistent-fixture.json"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("nonexistent-fixture.json", result.stdout)
        self.assertEqual(json.loads(result.stdout)["market"], "finland")
        override = subprocess.run(command + ["--countries", "DE"], cwd=ROOT,
                                  capture_output=True, text=True, check=False)
        self.assertEqual(override.returncode, 2)

    def test_shared_workflow_calls_both_checks(self):
        spec = (ROOT / ".claude/skills/job-scraper/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scrape_source_check.py plan --market <europe|finland>", spec)
        self.assertIn("scrape_source_check.py report --market <europe|finland>", spec)
        self.assertIn("Before any live search in a normal Europe/Finland run", spec)
        self.assertIn("For a normal Europe or Finland scrape, run Step 1e's closeout", spec)
        self.assertIn("to Step 1e before evaluating the general access table", spec)
        for market in ("europe", "finland"):
            workflow = (ROOT / f"markets/{market}/workflows/scrape-jobs.md").read_text(encoding="utf-8")
            self.assertIn("Use Step 1e's dedicated LinkedIn and Indeed list rules", workflow)
