"""Regression tests for the fork's multi-market/OpenClaw safety contracts.

These files are executable specifications: a routing or privacy sentence can
change runtime behavior even when no Python or TypeScript implementation moves.
The tests pin the boundaries that would otherwise regress silently.
"""

import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class MultiMarketRouterTests(unittest.TestCase):
    def test_router_resolves_market_for_setup_and_analyze(self):
        router = read("skills/job-search/SKILL.md")
        market_rule = router.split("## Route the operation", 1)[0]
        for operation in ("setup", "scrape", "analyze", "rank", "apply", "interview"):
            self.assertIn(f"`{operation}`", market_rule)
        self.assertIn("documents/<market>/profile/preferences.md", router)

    def test_china_operations_reach_their_market_workflows(self):
        router = read("skills/job-search/SKILL.md")
        for workflow in (
            "setup-profile.md",
            "scrape-jobs.md",
            "analyze-job.md",
            "rank-jobs.md",
            "apply-job.md",
            "interview-prep.md",
        ):
            self.assertIn(workflow, router)


class MarketStrategySelectionTests(unittest.TestCase):
    """Static market-selection contract; actual agent consumption is separate."""

    def test_market_paths_and_overlays_select_personal_strategies(self):
        skill = read(".claude/skills/job-scraper/SKILL.md")
        selection = skill.split("### Step 0: Load State", 1)[1].split("### Step 1:", 1)[0]
        routes = re.findall(
            r"^\s*\| `(europe|finland)` \| `([^`]+)` \| `([^`]+)` \|",
            selection, re.MULTILINE,
        )
        self.assertEqual(len(routes), 2)
        for market, strategy, guide in routes:
            with self.subTest(market=market):
                self.assertEqual(strategy, f"documents/{market}/profile/search-queries.md")
                self.assertEqual(guide, f"markets/{market}/search-queries.md")
                overlay = read(f"markets/{market}/workflows/scrape-jobs.md")
                self.assertIn(f"`{strategy}`", overlay)
                self.assertIn("shared scraper's Step 0", overlay)
        self.assertIn("Do not substitute the global strategy or the other market's strategy", selection)
        self.assertIn("Stop that market", selection)
        self.assertIn("ask if missing or ambiguous", selection)
        self.assertIn("this table does not change China", selection)

    def test_source_selection_and_summary_do_not_promote_history_to_acceptance(self):
        skill = read(".claude/skills/job-scraper/SKILL.md")
        self.assertIn("Use sources explicitly selected by the local strategy", skill)
        self.assertIn("use the selected market's source guide as candidates", skill)
        self.assertIn("A guide is not a command to run", skill)
        self.assertIn("not-attempted sources remain unverified", skill)
        self.assertIn("Historical evidence is not this run's acceptance", skill)
        self.assertIn("broad does not enable every source", skill)
        guide = read(".claude/skills/job-scraper/search-queries.md")
        self.assertIn("canonical", guide)
        self.assertIn("job-scraper Step 0", guide)
        self.assertNotIn("runs its CLI first", guide)
        self.assertNotIn("those CLIs to run", guide)


class PersonalDataBoundaryTests(unittest.TestCase):
    def test_europe_and_finland_setup_write_only_gitignored_copies(self):
        gitignore = read(".gitignore")
        self.assertIn("documents/*/profile/**", gitignore)
        for market in ("europe", "finland"):
            workflow = read(f"markets/{market}/workflows/setup-profile.md")
            self.assertIn(f"documents/{market}/profile/preferences.md", workflow)
            self.assertIn(f"markets/{market}/profile/preferences.md", workflow)
            self.assertIn("Never edit the tracked template", workflow)

    def test_china_has_no_candidate_specific_education_default(self):
        workflow = read("markets/china/workflows/scrape-jobs.md")
        for inherited_default in (
            "全日制本科",
            "统招本科",
            "学士学位",
            "985/211",
            "candidate has graduation certificate",
        ):
            self.assertNotIn(inherited_default, workflow)
        self.assertIn("never infer a candidate's degree", workflow)


class StateAndRuntimeContractTests(unittest.TestCase):
    def test_china_scrape_uses_canonical_lifecycle_status(self):
        workflow = read("markets/china/workflows/scrape-jobs.md")
        self.assertIn('"status": "new/skipped"', workflow)
        self.assertIn('"fetch_status": "ready/manual_required/blocked/skipped"', workflow)
        self.assertIn('"source": "cli"', workflow)
        self.assertIn("For WebSearch results, set `source` to\n`websearch`", workflow)
        self.assertIn("tools/job_key.py", workflow)

    def test_every_market_persists_and_ranks_with_an_explicit_market(self):
        scraper = read(".claude/skills/job-scraper/SKILL.md")
        rank = read(".claude/commands/rank.md")
        router = read("skills/job-search/SKILL.md")
        self.assertIn('"market": "china/europe/finland"', scraper)
        for command in ("candidates", "sweep", "apply"):
            command_line = next(
                line for line in rank.splitlines()
                if f"tools/rank_state.py {command}" in line
            )
            self.assertIn("--market", command_line)
        self.assertIn("every `tools/rank_state.py` invocation via `--market`", router)
        for market in ("china", "europe", "finland"):
            workflow = read(f"markets/{market}/workflows/scrape-jobs.md")
            self.assertIn(f'"market": "{market}"', workflow)

    def test_rank_veto_is_respected_by_downstream_readers(self):
        for path in (".claude/commands/notion-sync.md", ".claude/skills/upskill/SKILL.md"):
            with self.subTest(path=path):
                rule = read(path)
                for field in ("rank_eligible", "location_verdict", "language_gate", "market_gates"):
                    self.assertIn(field, rule)
                self.assertIn("FAIL", rule)

    def test_china_apply_text_pack_and_full_documents_have_distinct_contracts(self):
        shared = read(".claude/commands/apply.md")
        china = read("markets/china/workflows/apply-job.md")
        outcome = read(".claude/commands/outcome.md")
        self.assertIn("markets/china/workflows/apply-job.md", shared)
        self.assertIn("Step 6b", shared)
        for rule in ("text-only", "Full documents", "china_text_pack:", "cv_file", "cover_letter_file",
                     "job_search_tracker.csv", "job_posting.md", "source URL", "URL alone"):
            self.assertIn(rule, china)
        self.assertIn("china_text_pack:", outcome)
        self.assertIn("do not search fallback globs", outcome)

    def test_feature_branches_trigger_ci_without_requiring_a_pr(self):
        workflow = read(".github/workflows/ci.yml")
        self.assertIn('branches: [master, "feature/**"]', workflow)

    def test_runtime_does_not_invent_a_specific_ai_tool(self):
        files = (
            read("CLAUDE.md"),
            read(".claude/commands/apply.md"),
            read(".claude/commands/html-report.md"),
        )
        combined = "\n".join(files)
        self.assertNotIn("must reference **Claude Code** by name", combined)
        self.assertNotIn("Generated by Claude Code", combined)
        self.assertIn("Never infer a tool from the assistant runtime", combined)


class PortalSafetyTests(unittest.TestCase):
    def test_china_scrape_routes_linkedin_through_the_public_cli(self):
        workflow = read("markets/china/workflows/scrape-jobs.md")
        self.assertIn(".agents/skills/linkedin-search/cli/src/cli.ts search", workflow)
        self.assertIn(".agents/skills/linkedin-search/cli/src/cli.ts detail", workflow)
        self.assertIn('"<city, China>"', workflow)
        self.assertIn("--jobage 14 --limit 10", workflow)
        self.assertIn("report LinkedIn as unavailable and continue", workflow)
        self.assertNotIn("Do not include LinkedIn by default", workflow)

    def test_company_registry_fails_closed_instead_of_running_examples(self):
        helper = read(".agents/skills/company-pages-search/cli/src/helpers.ts")
        self.assertIn('"NO_REGISTRY"', helper)
        self.assertIn("example registry is never searched automatically", helper)
        self.assertNotIn("USING_EXAMPLE_REGISTRY", helper)
        self.assertNotIn("EXAMPLE_REGISTRY_PATH", helper)

    def test_bun_portals_declare_the_openclaw_binary_requirement(self):
        requirement = 'metadata: {"openclaw":{"requires":{"bins":["bun"]}}}'
        for skill in ("linkedin-search", "company-pages-search"):
            self.assertIn(requirement, read(f".agents/skills/{skill}/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
