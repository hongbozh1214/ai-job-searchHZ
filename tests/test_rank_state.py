"""Tests for tools/rank_state.py - /rank's state helper (#395).

/rank used to pull the whole of seen_jobs.json through the model's context to
select candidates, then emit it back to record scores. That cost the whole
backlog per run no matter how few jobs were being scored, and it grew for the
life of the workspace. These pin the behaviour the three subcommands took
over: selection matches Step 1's existing rules, the sweep matches rule 6
exactly (including its two defensive-parse edge cases), and the write-back
matches Step 4's existing rules exactly - the location_verdict legacy
migration, the deadline null-is-not-a-correction rule, and verbatim
strengths/gaps persistence.
"""
import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "rank_state.py"

TODAY = "2026-09-03"


def entry(**over):
    base = {
        "title": "SOC Analyst",
        "company": "Acme",
        "url": "https://example.com/job",
        "first_seen": "2026-08-30",
        "deadline": None,
        "status": "new",
        "portal": "linkedin-search",
        "market": "europe",
    }
    base.update(over)
    return base


class RankStateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "seen_jobs.json"
        self.addCleanup(self._tmp.cleanup)

    def write_state(self, seen):
        self.state.write_text(json.dumps({"seen": seen}), encoding="utf-8")

    def run_tool(self, *args, expect=0):
        command = [sys.executable, str(TOOL), *args]
        if "--market" not in args:
            command.extend(["--market", "europe"])
        command.extend(["--state", str(self.state), "--today", TODAY])
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, expect, proc.stderr)
        return json.loads(proc.stdout)

    def read_state(self):
        return json.loads(self.state.read_text(encoding="utf-8"))["seen"]


class Candidates(RankStateCase):
    def test_selects_only_new_entries_and_projects_a_compact_row(self):
        self.write_state(
            {
                "a": entry(),
                "b": entry(status="ranked", rank_score=70),
                "c": entry(status="skipped"),
                "d": entry(status="expired"),
            }
        )
        out = self.run_tool("candidates", "--tracker", str(self.tmp / "none.csv"))
        self.assertEqual([row["key"] for row in out["selected"]], ["a"])
        self.assertEqual(
            set(out["selected"][0]),
            {"key", "title", "company", "url", "portal", "deadline", "posted_date"},
            "the projection is the point: strengths/gaps and every other stored field "
            "stay on disk rather than entering the conversation",
        )

    def test_limit_defers_the_rest_and_reports_the_count(self):
        self.write_state({f"k{i}": entry(title=f"Role {i}") for i in range(25)})
        out = self.run_tool("candidates", "--limit", "10", "--tracker", str(self.tmp / "none.csv"))
        self.assertEqual(len(out["selected"]), 10)
        self.assertEqual(out["eligible"], 25)
        self.assertEqual(
            out["deferred"],
            15,
            "a backlog larger than the batch limit must be reported, not silently truncated - "
            "the user has to know a re-run continues it",
        )

    def test_limit_zero_means_no_cap(self):
        self.write_state({f"k{i}": entry(title=f"Role {i}") for i in range(15)})
        out = self.run_tool("candidates", "--limit", "0", "--tracker", str(self.tmp / "none.csv"))
        self.assertEqual(len(out["selected"]), 15)
        self.assertEqual(out["deferred"], 0)

    def test_tracker_pairs_are_excluded(self):
        self.write_state({"a": entry(company="Acme", title="SOC Analyst"), "b": entry(company="Other")})
        tracker = self.tmp / "tracker.csv"
        tracker.write_text("date,company,role\n2026-08-01,ACME,soc analyst\n", encoding="utf-8")
        out = self.run_tool("candidates", "--tracker", str(tracker))
        self.assertEqual([row["key"] for row in out["selected"]], ["b"])
        self.assertEqual(out["excluded_by_tracker"], 1)

    def test_distinct_posting_url_remains_rankable_when_another_role_variant_is_tracked(self):
        self.write_state({"same": entry(url="https://example.com/123456"),
                          "distinct": entry(url="https://example.com/654321")})
        tracker = self.tmp / "tracker.csv"
        tracker.write_text("company,role,source\nAcme,SOC Analyst,https://example.com/123456\n", encoding="utf-8")
        out = self.run_tool("candidates", "--tracker", str(tracker))
        self.assertEqual([r["key"] for r in out["selected"]], ["distinct"])
        self.assertEqual(out["excluded_by_tracker"], 1)

    def test_tracker_exclusion_handles_utf8_bom_and_reordered_columns(self):
        self.write_state({"a": entry(company="Acme", title="SOC Analyst"), "b": entry(company="Other")})
        tracker = self.tmp / "tracker.csv"
        # A spreadsheet export can prepend a BOM to either matching column.
        for encoding in ("utf-8", "utf-8-sig"):
            for csv_text in (
                "date,company,role\r\n2026-08-01,ACME,soc analyst\r\n",
                "company,role,date\r\nACME,soc analyst,2026-08-01\r\n",
                "role,company,date\r\nsoc analyst,ACME,2026-08-01\r\n",
            ):
                with self.subTest(encoding=encoding, header=csv_text.splitlines()[0]):
                    tracker.write_bytes(csv_text.encode(encoding))
                    out = self.run_tool("candidates", "--tracker", str(tracker))
                    self.assertEqual([row["key"] for row in out["selected"]], ["b"])
                    self.assertEqual(out["excluded_by_tracker"], 1)

    def test_tracker_exclusion_preserves_unicode_identity(self):
        # Use the standard /outcome header and the real candidates CLI.
        header = (
            "date,company,sector,role,role_type,channel,status,contact_person,"
            "fit_rating,notes,cv_file,cover_letter_file,source,deadline"
        ).split(",")
        cases = (
            # Tracked company/role, candidate company/title, expected exclusion.
            ("Acme", "设计师", "Acme", "工程师", False),
            ("Acme", "工程师", "Acme", "工程师", True),
            ("腾讯", "Engineer", "腾讯", "Engineer", True),
            ("腾讯", "Engineer", "阿里巴巴", "Engineer", False),
            ("Компания", "Инженер", "КОМПАНИЯ", "ИНЖЕНЕР", True),
            ("Café", "Engineer", "Cafe\u0301", "Engineer", True),
            ("Straße", "Engineer", "STRASSE", "Engineer", True),
            ("कला Labs", "Engineer", "कल Labs", "Engineer", False),
            ("Acme, Inc.", "SOC Analyst", "ACME_INC", "soc-analyst", True),
        )
        tracker = self.tmp / "tracker.csv"
        for company, role, candidate_company, title, excluded in cases:
            with self.subTest(tracked=(company, role), candidate=(candidate_company, title)):
                self.write_state({
                    "candidate": entry(company=candidate_company, title=title),
                    "other": entry(company="Other", title="Untracked role"),
                })
                with tracker.open("w", encoding="utf-8", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=header)
                    writer.writeheader()
                    writer.writerow({"date": TODAY, "company": company, "role": role, "status": "applied"})
                out = self.run_tool("candidates", "--tracker", str(tracker))
                self.assertEqual(
                    [row["key"] for row in out["selected"]],
                    ["other"] if excluded else ["candidate", "other"],
                )
                self.assertEqual(out["excluded_by_tracker"], int(excluded))

    def test_focus_filters_on_title_company_and_stored_fit_notes(self):
        self.write_state(
            {
                "a": entry(title="Data Scientist"),
                "b": entry(title="SOC Analyst"),
                "c": entry(title="Engineer", strengths=["strong data science match"]),
            }
        )
        out = self.run_tool("candidates", "--focus", "data scien", "--tracker", str(self.tmp / "n.csv"))
        self.assertEqual(sorted(row["key"] for row in out["selected"]), ["a", "c"])

    def test_all_flag_includes_every_status_but_skipped(self):
        self.write_state(
            {
                "a": entry(status="ranked"),
                "b": entry(status="expired"),
                "c": entry(status="skipped"),
                "d": entry(status="new"),
            }
        )
        out = self.run_tool("candidates", "--all", "--tracker", str(self.tmp / "n.csv"))
        self.assertEqual(sorted(row["key"] for row in out["selected"]), ["a", "b", "d"])

    def test_market_filter_excludes_other_and_legacy_unknown_entries(self):
        self.write_state(
            {
                "eu": entry(title="EU Role", market="europe"),
                "fi": entry(title="FI Role", market="finland"),
                "legacy": entry(title="Legacy Role", market=None),
            }
        )
        out = self.run_tool(
            "candidates", "--market", "europe", "--tracker", str(self.tmp / "n.csv")
        )
        self.assertEqual([row["key"] for row in out["selected"]], ["eu"])
        self.assertEqual(out["market"], "europe")
        self.assertEqual(out["excluded_by_market"], 1)
        self.assertEqual(out["unknown_market"], 1)

    def test_missing_state_file_exits_nonzero(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), "candidates", "--state", str(self.tmp / "nope.json"),
             "--tracker", str(self.tmp / "n.csv"), "--market", "europe"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not found", proc.stderr + proc.stdout)

    def test_market_is_required_at_the_cli_boundary(self):
        self.write_state({"a": entry()})
        proc = subprocess.run(
            [sys.executable, str(TOOL), "candidates", "--state", str(self.state)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--market", proc.stderr)


class Sweep(RankStateCase):
    def test_retires_past_deadlines_and_flags_the_closing_ones(self):
        self.write_state(
            {
                "past": entry(status="ranked", deadline="2026-09-01"),
                "soon": entry(status="ranked", deadline="2026-09-07"),
                "later": entry(status="ranked", deadline="2026-12-01"),
            }
        )
        out = self.run_tool("sweep", "--write")
        self.assertEqual([r["key"] for r in out["newly_expired"]], ["past"])
        self.assertEqual([r["key"] for r in out["closing_soon"]], ["soon"])
        self.assertEqual(self.read_state()["past"]["status"], "expired")
        self.assertEqual(self.read_state()["soon"]["status"], "ranked")

    def test_entries_without_a_deadline_are_left_alone(self):
        """The majority case. Inferring one from first_seen would retire jobs
        on a date nobody set."""
        self.write_state({"a": entry(status="ranked", deadline=None), "b": entry(status="ranked")})
        out = self.run_tool("sweep", "--write")
        self.assertEqual(out["newly_expired"], [])
        self.assertTrue(all(e["status"] == "ranked" for e in self.read_state().values()))

    def test_non_iso_deadlines_are_reported_not_compared(self):
        """Portals have shipped "ASAP", DD.MM.YYYY and free text into this field."""
        self.write_state(
            {
                "asap": entry(status="ranked", deadline="ASAP", portal="jobindex-search"),
                "euro": entry(status="ranked", deadline="31.08.2026", portal="jobbank-search"),
            }
        )
        out = self.run_tool("sweep", "--write")
        self.assertEqual(out["newly_expired"], [])
        self.assertEqual(
            sorted(r["portal"] for r in out["unparseable_deadlines"]),
            ["jobbank-search", "jobindex-search"],
            "a bad stored value is traced back to the portal that wrote it",
        )
        self.assertTrue(all(e["status"] == "ranked" for e in self.read_state().values()))

    def test_only_ranked_entries_are_swept_and_excluded_keys_are_skipped(self):
        self.write_state(
            {
                "new_past": entry(status="new", deadline="2026-09-01"),
                "rescored": entry(status="ranked", deadline="2026-09-01"),
                "other": entry(status="ranked", deadline="2026-09-01"),
            }
        )
        out = self.run_tool("sweep", "--write", "--exclude", "rescored")
        self.assertEqual([r["key"] for r in out["newly_expired"]], ["other"])
        self.assertEqual(out["swept"], 1)
        self.assertEqual(self.read_state()["new_past"]["status"], "new")

    def test_without_write_nothing_is_persisted(self):
        self.write_state({"past": entry(status="ranked", deadline="2026-09-01")})
        out = self.run_tool("sweep")
        self.assertEqual([r["key"] for r in out["newly_expired"]], ["past"])
        self.assertFalse(out["written"])
        self.assertEqual(self.read_state()["past"]["status"], "ranked")

    def test_market_filter_only_sweeps_the_selected_market(self):
        self.write_state(
            {
                "eu": entry(status="ranked", deadline="2026-09-01", market="europe"),
                "fi": entry(status="ranked", deadline="2026-09-01", market="finland"),
                "legacy": entry(status="ranked", deadline="2026-09-01", market=None),
            }
        )
        out = self.run_tool("sweep", "--write", "--market", "europe")
        self.assertEqual([row["key"] for row in out["newly_expired"]], ["eu"])
        self.assertEqual(out["excluded_by_market"], 1)
        self.assertEqual(out["unknown_market"], 1)
        stored = self.read_state()
        self.assertEqual(stored["eu"]["status"], "expired")
        self.assertEqual(stored["fi"]["status"], "ranked")
        self.assertEqual(stored["legacy"]["status"], "ranked")

    def test_vetoed_jobs_are_not_closing_soon_but_can_still_expire(self):
        self.write_state({
            "new-veto": entry(status="ranked", deadline="2026-09-04", rank_eligible=False,
                              market_gates={"authorization": {"verdict": "FAIL", "reason": "permit"}}),
            "legacy-veto": entry(status="ranked", deadline="2026-09-04",
                                 market_gates={"authorization": {"verdict": "FAIL", "reason": "permit"}}),
            "eligible": entry(status="ranked", deadline="2026-09-04", rank_eligible=True),
            "past-veto": entry(status="ranked", deadline="2026-09-01", rank_eligible=False),
        })
        out = self.run_tool("sweep", "--write")
        self.assertEqual([r["key"] for r in out["closing_soon"]], ["eligible"])
        self.assertEqual([r["key"] for r in out["newly_expired"]], ["past-veto"])
        self.assertEqual(self.read_state()["past-veto"]["status"], "expired")


class Apply(RankStateCase):
    def results(self, payload):
        path = self.tmp / "results.json"
        state = self.read_state() if self.state.exists() else {}
        for result in payload:
            if result.get("status") == "scored" and "market_gates" not in result:
                result["market_gates"] = {name: {"verdict": "PASS"} for name in
                                          ("authorization", "contract", "compensation", "mobility")}
            if result.get("status") == "scored":
                previous = state.get(result.get("key"), {})
                if "location_verdict" not in result and previous.get("location_verdict", previous.get("location")) not in ("PASS", "FAIL", "FLAG"):
                    result["location_verdict"] = "PASS"
                if "language_gate" not in result and previous.get("language_gate") not in ("PASS", "FAIL", "FLAG"):
                    result["language_gate"] = "PASS"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_weights_bands_and_persisted_fields(self):
        self.write_state({"a": entry()})
        out = self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 80, "experience": 60, "behavioral": 70, "career": 75},
                        "location_verdict": "PASS",
                        "language_gate": "PASS",
                        "deadline": "2026-09-05",
                        "strengths": ["s1", "s2"],
                        "gaps": ["g1"],
                    }
                ]
            ),
        )
        stored = self.read_state()["a"]
        # 80*.30 + 60*.25 + 70*.15 + 75*.30 = 72
        self.assertEqual(stored["rank_score"], 72)
        self.assertEqual(stored["rank_verdict"], "Good Fit")
        self.assertEqual(stored["status"], "ranked")
        self.assertEqual(stored["rank_date"], TODAY)
        self.assertEqual(stored["strengths"], ["s1", "s2"])
        self.assertEqual(stored["gaps"], ["g1"])
        self.assertEqual(stored["deadline"], "2026-09-05")
        self.assertTrue(out["ranked"][0]["urgent"], "a deadline inside 7 days carries the urgency marker")

    def test_expired_status_is_written_through(self):
        self.write_state({"a": entry()})
        out = self.run_tool("apply", "--results", self.results([{"key": "a", "status": "expired"}]))
        self.assertEqual(self.read_state()["a"]["status"], "expired")
        self.assertEqual([r["key"] for r in out["expired"]], ["a"])

    def test_null_deadline_does_not_erase_a_stored_one(self):
        """Absence is not a correction: a fetch that degraded to a listing page
        returns no deadline, and blanking the stored date would also put the
        entry out of the sweep's reach forever."""
        self.write_state({"a": entry(deadline="2026-10-01")})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50},
                        "deadline": None,
                    }
                ]
            ),
        )
        self.assertEqual(self.read_state()["a"]["deadline"], "2026-10-01")

    def test_legacy_verdict_stored_under_location_is_migrated(self):
        self.write_state({"a": entry(location="FLAG")})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50},
                    }
                ]
            ),
        )
        stored = self.read_state()["a"]
        self.assertEqual(stored["location_verdict"], "FLAG")
        self.assertNotIn("location", stored, "a legacy verdict is moved, never left to read as a place")

    def test_a_real_place_in_location_survives(self):
        self.write_state({"a": entry(location="Athens, Greece")})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50},
                        "location_verdict": "PASS",
                    }
                ]
            ),
        )
        self.assertEqual(self.read_state()["a"]["location"], "Athens, Greece")

    def test_vetoed_rows_are_separated_from_the_ranking(self):
        self.write_state({"a": entry(), "b": entry(), "c": entry()})
        scores = {"technical": 90, "experience": 90, "behavioral": 90, "career": 90}
        out = self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {"key": "a", "status": "scored", "scores": scores, "location_verdict": "FAIL"},
                    {"key": "b", "status": "scored", "scores": scores, "language_gate": "FAIL",
                     "language_note": "requires fluent Polish"},
                    {"key": "c", "status": "scored", "scores": {"technical": 40, "experience": 40,
                                                                "behavioral": 40, "career": 40}},
                ]
            ),
        )
        self.assertEqual(sorted(r["key"] for r in out["vetoed"]), ["a", "b"])
        self.assertEqual([r["key"] for r in out["ranked"]], ["c"])
        self.assertEqual(self.read_state()["b"]["language_note"], "requires fluent Polish")

    def test_language_note_is_dropped_when_gate_passes(self):
        self.write_state({"a": entry(language_note="stale note from a prior run")})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50},
                        "language_gate": "PASS",
                    }
                ]
            ),
        )
        self.assertNotIn("language_note", self.read_state()["a"])

    def test_strengths_and_gaps_are_capped_and_stored_verbatim(self):
        self.write_state({"a": entry()})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50},
                        "strengths": ["one", "two", "three", "four"],
                        "gaps": ["<script>not sanitized on purpose, stored as plain data</script>"],
                    }
                ]
            ),
        )
        stored = self.read_state()["a"]
        self.assertEqual(len(stored["strengths"]), 3, "at most 3 bullets, matching the spec")
        self.assertEqual(
            stored["gaps"],
            ["<script>not sanitized on purpose, stored as plain data</script>"],
            "gaps are stored verbatim - untrusted data, never reformatted",
        )

    def test_all_replaces_rather_than_accumulates_arrays(self):
        self.write_state({"a": entry(status="ranked", strengths=["old strength"], gaps=["old gap"])})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [
                    {
                        "key": "a",
                        "status": "scored",
                        "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50},
                        "strengths": ["new strength"],
                        "gaps": ["new gap"],
                    }
                ]
            ),
        )
        stored = self.read_state()["a"]
        self.assertEqual(stored["strengths"], ["new strength"])
        self.assertEqual(stored["gaps"], ["new gap"])

    def test_unknown_key_is_an_error_not_a_silent_drop(self):
        self.write_state({"a": entry()})
        out = self.run_tool(
            "apply", "--results", self.results([{"key": "ghost", "status": "scored", "scores": {}}]), expect=1
        )
        self.assertEqual(out["errors"][0]["key"], "ghost")

    def test_market_filter_rejects_cross_market_and_unknown_writes(self):
        self.write_state(
            {
                "eu": entry(market="europe"),
                "fi": entry(market="finland"),
                "legacy": entry(market=None),
            }
        )
        out = self.run_tool(
            "apply",
            "--market",
            "europe",
            "--results",
            self.results(
                [
                    {"key": "eu", "status": "expired"},
                    {"key": "fi", "status": "expired"},
                    {"key": "legacy", "status": "expired"},
                ]
            ),
            expect=1,
        )
        self.assertEqual([row["key"] for row in out["expired"]], ["eu"])
        self.assertEqual({error["key"] for error in out["errors"]}, {"fi", "legacy"})
        stored = self.read_state()
        self.assertEqual(stored["eu"]["status"], "expired")
        self.assertEqual(stored["fi"]["status"], "new")
        self.assertEqual(stored["legacy"]["status"], "new")

    def test_missing_score_dimension_is_an_error(self):
        self.write_state({"a": entry()})
        out = self.run_tool(
            "apply",
            "--results",
            self.results([{"key": "a", "status": "scored", "scores": {"technical": 80}}]),
            expect=1,
        )
        self.assertIn("experience", out["errors"][0]["error"])
        self.assertEqual(self.read_state()["a"]["status"], "new", "a rejected result never half-writes an entry")

    def test_dry_run_prints_but_never_writes(self):
        self.write_state({"a": entry()})
        self.run_tool(
            "apply",
            "--results",
            self.results(
                [{"key": "a", "status": "scored",
                  "scores": {"technical": 50, "experience": 50, "behavioral": 50, "career": 50}}]
            ),
            "--dry-run",
        )
        self.assertEqual(self.read_state()["a"]["status"], "new")

    def test_invalid_scores_report_errors_without_changing_the_entry(self):
        dimensions = ("technical", "experience", "behavioral", "career")
        invalid = (-1, 101, True, False, float("nan"), float("inf"), -float("inf"), 10**400)
        for dimension in dimensions:
            for value in invalid:
                with self.subTest(dimension=dimension, value=value):
                    original = entry(status="ranked", rank_score=70, strengths=["keep"])
                    self.write_state({"a": original, "b": entry()})
                    scores = dict.fromkeys(dimensions, 50)
                    scores[dimension] = value
                    out = self.run_tool(
                        "apply", "--results", self.results([
                            {"key": "a", "status": "scored", "scores": scores},
                            {"key": "b", "status": "scored", "scores": dict.fromkeys(dimensions, 80)},
                        ]), expect=1,
                    )
                    self.assertEqual(len(out["errors"]), 1)
                    self.assertEqual(out["errors"][0]["key"], "a")
                    self.assertIn(dimension, out["errors"][0]["error"])
                    self.assertEqual(self.read_state()["a"], original)
                    self.assertEqual([row["key"] for row in out["ranked"]], ["b"])
                    self.assertEqual(self.read_state()["b"]["rank_score"], 80)

    def test_score_boundaries_and_fractional_scores_remain_valid(self):
        for value, expected in ((0, 0), (100, 100), (72.5, 73)):
            with self.subTest(value=value):
                self.write_state({"a": entry()})
                out = self.run_tool("apply", "--results", self.results([
                    {"key": "a", "status": "scored", "scores": dict.fromkeys(
                        ("technical", "experience", "behavioral", "career"), value)},
                ]))
                self.assertEqual(out["errors"], [])
                self.assertEqual(self.read_state()["a"]["rank_score"], expected)

    def test_re_scoring_an_already_ranked_job_is_idempotent(self):
        """Re-running /rank never re-scores an already-ranked job unless --all
        says so (Step 4), but if it does score one again, apply must produce
        the same result deterministically rather than accumulating state."""
        self.write_state({"a": entry(status="ranked", rank_score=40, strengths=["old"])})
        scores = {"technical": 90, "experience": 90, "behavioral": 90, "career": 90}
        self.run_tool(
            "apply", "--results",
            self.results([{"key": "a", "status": "scored", "scores": scores, "strengths": ["new"]}]),
        )
        stored = self.read_state()["a"]
        self.assertEqual(stored["rank_score"], 90)
        self.assertEqual(stored["strengths"], ["new"])

    def test_expired_deadlines_never_make_the_ranking_even_with_high_scores(self):
        self.write_state({"stored": entry(deadline="2026-09-01"),
                          "fresh": entry(deadline="2026-09-10"),
                          "corrected": entry(deadline="2026-09-01")})
        full = dict.fromkeys(("technical", "experience", "behavioral", "career"), 90)
        out = self.run_tool("apply", "--results", self.results([
            {"key": "stored", "status": "scored", "scores": full, "deadline": None},
            {"key": "fresh", "status": "scored", "scores": full, "deadline": "2026-09-02"},
            {"key": "corrected", "status": "scored", "scores": full, "deadline": "2026-09-10"},
        ]))
        self.assertEqual({r["key"] for r in out["expired"]}, {"stored", "fresh"})
        self.assertEqual([r["key"] for r in out["ranked"]], ["corrected"])
        self.assertEqual(self.read_state()["fresh"]["deadline"], "2026-09-02")
        self.assertEqual(self.read_state()["corrected"]["status"], "ranked")

    def test_market_gates_veto_and_flags_persist_without_losing_score(self):
        self.write_state({"a": entry(), "b": entry()})
        full = dict.fromkeys(("technical", "experience", "behavioral", "career"), 90)
        gates = {name: {"verdict": "PASS"} for name in
                 ("authorization", "contract", "compensation", "mobility")}
        out = self.run_tool("apply", "--results", self.results([
            {"key": "a", "status": "scored", "scores": full,
             "market_gates": {**gates, "authorization": {"verdict": "FAIL", "reason": "work permit required"}}},
            {"key": "b", "status": "scored", "scores": full,
             "market_gates": {**gates, "contract": {"verdict": "FLAG", "reason": "term unclear"}}},
        ]))
        self.assertEqual([r["key"] for r in out["vetoed"]], ["a"])
        self.assertEqual([r["key"] for r in out["ranked"]], ["b"])
        self.assertEqual(self.read_state()["a"]["market_gates"]["authorization"]["reason"], "work permit required")

    def test_missing_or_invalid_market_decisions_cannot_silently_pass(self):
        self.write_state({"a": entry()})
        scores = dict.fromkeys(("technical", "experience", "behavioral", "career"), 90)
        out = self.run_tool("apply", "--results", self.results([
            {"key": "a", "status": "scored", "scores": scores, "market_gates": {}},
        ]), expect=1)
        self.assertIn("market_gates missing", out["errors"][0]["error"])
        self.assertEqual(self.read_state()["a"]["status"], "new")

    def test_invalid_fresh_deadline_cannot_override_known_expiry(self):
        self.write_state({"a": entry(deadline="2026-09-01")})
        out = self.run_tool("apply", "--results", self.results([
            {"key": "a", "status": "scored", "deadline": "ASAP",
             "scores": dict.fromkeys(("technical", "experience", "behavioral", "career"), 90)},
        ]), expect=1)
        self.assertIn("deadline", out["errors"][0]["error"])
        self.assertEqual(self.read_state()["a"]["status"], "new")

    def test_unsupported_verdict_and_missing_flag_reason_are_rejected(self):
        self.write_state({"a": entry()})
        for decision in ({"verdict": ["FAIL"]}, {"verdict": "FLAG"}):
            with self.subTest(decision=decision):
                gates = {name: {"verdict": "PASS"} for name in
                         ("authorization", "contract", "compensation", "mobility")}
                gates["authorization"] = decision
                out = self.run_tool("apply", "--results", self.results([
                    {"key": "a", "status": "scored", "market_gates": gates,
                     "scores": dict.fromkeys(("technical", "experience", "behavioral", "career"), 90)},
                ]), expect=1)
                self.assertEqual(out["errors"][0]["key"], "a")
                self.assertEqual(self.read_state()["a"]["status"], "new")

    def test_location_and_language_must_be_explicit_or_preserve_existing_verdict(self):
        self.write_state({"a": entry(language_gate="FAIL", language_note="mandatory language")})
        scores = dict.fromkeys(("technical", "experience", "behavioral", "career"), 90)
        out = self.run_tool("apply", "--results", self.results([
            {"key": "a", "status": "scored", "scores": scores, "location_verdict": "PASS"},
        ]))
        self.assertEqual([row["key"] for row in out["vetoed"]], ["a"])
        self.assertFalse(self.read_state()["a"]["rank_eligible"])
        gates = {name: {"verdict": "PASS"} for name in
                 ("authorization", "contract", "compensation", "mobility")}
        for verdict in ("fail", "", 123):
            with self.subTest(verdict=verdict):
                payload = [{"key": "a", "status": "scored", "scores": scores,
                            "market_gates": gates, "location_verdict": verdict,
                            "language_gate": "PASS"}]
                file = self.tmp / "invalid.json"
                file.write_text(json.dumps(payload))
                result = self.run_tool("apply", "--results", str(file), expect=1)
                self.assertIn("location_verdict", result["errors"][0]["error"])
                self.assertFalse(self.read_state()["a"]["rank_eligible"])
        file.write_text(json.dumps([{"key": "a", "status": "scored", "scores": scores,
                                    "market_gates": gates, "location_verdict": "PASS", "language_gate": "fail"}]))
        result = self.run_tool("apply", "--results", str(file), expect=1)
        self.assertIn("language_gate", result["errors"][0]["error"])
        file.write_text(json.dumps([{"key": "a", "status": "scored", "scores": scores,
                                    "market_gates": gates, "location_verdict": "PASS", "language_gate": "PASS"}]))
        self.assertEqual([row["key"] for row in self.run_tool("apply", "--results", str(file))["ranked"]], ["a"])
        self.assertTrue(self.read_state()["a"]["rank_eligible"], "a genuinely new PASS can revive a vetoed role")

    def test_explicit_verdicts_required_for_new_entries(self):
        self.write_state({"a": entry()})
        gates = {name: {"verdict": "PASS"} for name in
                 ("authorization", "contract", "compensation", "mobility")}
        file = self.tmp / "missing.json"
        file.write_text(json.dumps([{"key": "a", "status": "scored",
                                    "scores": dict.fromkeys(("technical", "experience", "behavioral", "career"), 90),
                                    "market_gates": gates}]))
        out = self.run_tool("apply", "--results", str(file), expect=1)
        self.assertIn("location_verdict", out["errors"][0]["error"])
        self.assertEqual(self.read_state()["a"]["status"], "new")


class LocalChina(RankStateCase):
    def setUp(self):
        super().setUp()
        self.inbox = self.tmp / "inbox"
        self.inbox.mkdir()

    def jd(self, content=None):
        path = self.inbox / "company-role.md"
        path.write_text(content or ("# 工程师 @ 公司\n**Source URL:** https://example.com/456789\n"
                                    "**Fetch Status:** manual_required\n## Paste Full JD Below\n"
                                    + "负责项目开发与团队协作，要求了解具体项目、开展文档编制与跟进沟通。" * 5), encoding="utf-8")
        return path

    def test_two_local_postings_flow_through_import_rank_veto_sweep_and_tracker(self):
        self.write_state({"manual": entry(market="china", fetch_status="manual_required")})
        for number in (1001, 1002):
            (self.inbox / f"posting-{number}.md").write_text(
                f"# 工程师 @ 公司\n**Source URL:** https://example.com/{number}\n"
                "## Paste Full JD Below\n" + "招聘工程师，负责实际项目研发、沟通及交付。" * 15,
                encoding="utf-8",
            )
        imported = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox))
        self.assertEqual(len(imported["imported"]), 2)
        selected = self.run_tool("candidates", "--market", "china", "--inbox", str(self.inbox),
                                 "--tracker", str(self.tmp / "none.csv"))
        self.assertEqual(len(selected["selected"]), 2)
        self.assertEqual(selected["awaiting_local_jd"], 1)
        keys = {row["url"].rsplit("/", 1)[-1]: row["key"] for row in selected["selected"]}
        gates = {name: {"verdict": "PASS"} for name in
                 ("compensation", "work_schedule", "employment_type", "social_insurance", "role_type", "qualifications")}
        results = []
        for number in (1001, 1002):
            results.append({"key": keys[str(number)], "status": "scored", "deadline": "2026-09-07",
                            "scores": dict.fromkeys(("technical", "experience", "behavioral", "career"), 90),
                            "market_gates": gates if number == 1001 else {
                                **gates, "work_schedule": {"verdict": "FAIL", "reason": "Schedule conflicts with stated availability"}},
                            "location_verdict": "PASS", "language_gate": "PASS"})
        file = self.tmp / "batch.json"
        file.write_text(json.dumps(results), encoding="utf-8")
        ranked = self.run_tool("apply", "--market", "china", "--results", str(file))
        self.assertEqual([r["key"] for r in ranked["ranked"]], [keys["1001"]])
        self.assertEqual([r["key"] for r in ranked["vetoed"]], [keys["1002"]])
        sweep = self.run_tool("sweep", "--market", "china")
        self.assertEqual([r["key"] for r in sweep["closing_soon"]], [keys["1001"]])
        self.assertEqual(len(self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox))["unchanged"]), 2)
        tracker = self.tmp / "tracker.csv"
        tracker.write_text("company,role,source\n公司,工程师,https://example.com/1001\n", encoding="utf-8")
        remaining = self.run_tool("candidates", "--all", "--market", "china", "--inbox", str(self.inbox),
                                  "--tracker", str(tracker))
        self.assertEqual([row["key"] for row in remaining["selected"]], [keys["1002"]])

    def test_import_offline_and_rank_same_key_without_refetch(self):
        file = self.jd()
        first = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox), "--file", str(file))
        key = first["imported"][0]["key"]
        self.assertEqual(self.read_state()[key]["fetch_status"], "ready")
        self.assertEqual(self.run_tool("candidates", "--market", "china", "--inbox", str(self.inbox),
                                       "--tracker", str(self.tmp / "none"))
                         ["selected"][0]["job_file"], str(file))
        result = {"key": key, "status": "scored", "scores": dict.fromkeys(
            ("technical", "experience", "behavioral", "career"), 80),
            "location_verdict": "PASS", "language_gate": "PASS",
            "market_gates": {name: {"verdict": "PASS"} for name in
                             ("compensation", "work_schedule", "employment_type",
                              "social_insurance", "role_type", "qualifications")}}
        results = self.tmp / "results.json"
        results.write_text(json.dumps([result]), encoding="utf-8")
        out = self.run_tool("apply", "--market", "china", "--results", str(results))
        self.assertEqual([r["key"] for r in out["ranked"]], [key])
        again = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox))
        self.assertEqual(again["unchanged"][0]["key"], key)
        self.assertEqual(self.read_state()[key]["status"], "ranked")
        self.jd(file.read_text(encoding="utf-8") + "\n补充明确要求。")
        updated = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox))
        self.assertEqual(updated["imported"][0]["key"], key)
        self.assertEqual(self.read_state()[key]["status"], "new")

    def test_manual_required_snippet_and_escape_are_rejected(self):
        file = self.jd("# Role @ Company\n## Search Snippet\nlooks relevant\n## Paste Full JD Below\n")
        out = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox), expect=1)
        self.assertEqual(len(out["errors"]), 1)
        self.assertFalse(self.state.exists())
        outside = self.tmp / "outside.md"
        outside.write_text(self.jd().read_text(encoding="utf-8"), encoding="utf-8")
        file.unlink()
        file.symlink_to(outside)
        out = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox), expect=1)
        self.assertIn("inside the China inbox", out["errors"][0]["error"])

    def test_matches_scraped_record_without_creating_duplicate(self):
        self.write_state({"legacy": entry(market="china", title="工程师", company="公司",
                                          url="https://example.com/456789", fetch_status="manual_required")})
        out = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox),
                            "--file", str(self.jd()))
        self.assertEqual(out["imported"][0]["key"], "legacy")
        self.assertEqual(len(self.read_state()), 1)

    def test_distinct_urls_keep_distinct_inbox_records_and_reimport_idempotently(self):
        a = self.jd(self.jd().read_text(encoding="utf-8").replace("# 工程师 @ 公司", "# Engineer @ Acme"))
        b = self.inbox / "another-location.md"
        b.write_text(a.read_text(encoding="utf-8").replace("456789", "654321"), encoding="utf-8")
        out = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox))
        self.assertEqual(len(out["imported"]), 2)
        self.assertEqual(len(self.read_state()), 2)
        self.assertEqual({e["url"] for e in self.read_state().values()},
                         {"https://example.com/456789", "https://example.com/654321"})
        self.assertEqual(len(self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox))["unchanged"]), 2)
        audit = subprocess.run([sys.executable, str(REPO / "tools/job_key.py"), "--audit", str(self.state)],
                               capture_output=True, text=True)
        self.assertEqual(audit.returncode, 0, audit.stdout)
        self.assertEqual(json.loads(audit.stdout)["keys_not_matching_current_rule"], 0)

    def test_without_url_another_file_must_not_overwrite_existing_role(self):
        first = self.jd().read_text(encoding="utf-8").replace("**Source URL:** https://example.com/456789", "")
        a = self.jd(first)
        b = self.inbox / "z-different-posting.md"
        b.write_text(first + "\n新职位新增的要求", encoding="utf-8")
        out = self.run_tool("import-local", "--market", "china", "--inbox", str(self.inbox), expect=1)
        self.assertEqual(len(out["imported"]), 1)
        self.assertEqual(len(out["errors"]), 1)
        self.assertEqual(len(self.read_state()), 1)
        self.assertEqual(next(iter(self.read_state().values()))["job_file"], str(a))

    def test_manual_required_records_do_not_starve_ready_china_jobs(self):
        self.write_state({**{f"blocked-{i}": entry(market="china", fetch_status="manual_required") for i in range(10)},
                          "ready": entry(market="china", job_file=str(self.jd()), fetch_status="ready")})
        out = self.run_tool("candidates", "--market", "china", "--inbox", str(self.inbox),
                            "--tracker", str(self.tmp / "none.csv"))
        self.assertEqual([r["key"] for r in out["selected"]], ["ready"])
        self.assertEqual(out["awaiting_local_jd"], 10)
        self.assertEqual(out["deferred"], 0)

    def test_deleted_local_jd_is_not_selected_or_read_outside_inbox(self):
        old = self.jd()
        outside = self.tmp / "outside.md"
        outside.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
        self.write_state({"missing": entry(market="china", job_file=str(self.inbox / "gone.md")),
                          "outside": entry(market="china", job_file=str(outside)),
                          "ready": entry(market="china", job_file=str(old))})
        out = self.run_tool("candidates", "--market", "china", "--inbox", str(self.inbox),
                            "--tracker", str(self.tmp / "none.csv"))
        self.assertEqual([r["key"] for r in out["selected"]], ["ready"])
        self.assertEqual(out["awaiting_local_jd"], 2)


if __name__ == "__main__":
    unittest.main()
