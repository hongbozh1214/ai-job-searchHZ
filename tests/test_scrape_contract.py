"""Tests for the /scrape Step 2 search-output contract across portal CLIs.

Mirrors the pattern of test_html_report_command.py: derive the contract from
the spec itself and compare it against the real portal CLIs, so a drift on
either side fails with a clean diff.

Why this test exists: .claude/skills/job-scraper/SKILL.md Step 2 promises
"Search output already includes title, company, location, date, and URL" for
every portal CLI, and Step 4.75's degraded scan flags "company null or empty
on every result" as a half-working parser. A CLI that quietly stops emitting
those fields flags the portal as degraded on every /scrape run while CI stays
green, breaks the seen_jobs.json dedupe (url_or_company_title_key), and leaves
/rank without a posting URL. That failure class landed for real: jobnet-search
emitted only the raw API schema and jobdanmark-search emitted companyName with
no company/location/date keys until both were normalized.

{helpers.ts, commands/search.ts} are the two files where every registered
CLI's search output currently lives (HTML-parsing portals normalize in
helpers.ts, API portals in commands/search.ts). detail.ts is deliberately
excluded: the contract is about the search output /scrape consumes.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_SKILL = REPO_ROOT / ".claude" / "skills" / "job-scraper" / "SKILL.md"
PORTAL_CLIS = sorted((REPO_ROOT / ".agents" / "skills").glob("*-search"))

# Derived, never copied: a hardcoded field list drifts in lockstep with
# nothing - if Step 2's prose drops or adds a field, the known-good portals
# and this pin would keep agreeing forever while the contract changed.
_CONTRACT_SENTENCE = re.compile(r"Search output already includes ([a-zA-Z0-9\s,]+)\.", re.MULTILINE)


def derive_contract_fields() -> frozenset[str]:
    text = SCRAPER_SKILL.read_text(encoding="utf-8")
    match = _CONTRACT_SENTENCE.search(text)
    if match is None:
        raise AssertionError("Step 2 contract sentence not found in job-scraper/SKILL.md")
    fields_text = re.sub(r"\s+and\s+", ",", match.group(1))
    fields = {f.strip().lower() for f in fields_text.split(",") if f.strip()}
    return frozenset(fields)


def search_output_source(search_ts: Path) -> str:
    helpers_ts = search_ts.parent.parent / "helpers.ts"
    files = [search_ts, helpers_ts] if helpers_ts.exists() else [search_ts]
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


class ScrapeSearchOutputContractTests(unittest.TestCase):
    """Every portal CLI's search output must carry the Step 2 contract fields."""

    def test_step2_contract_sentence_is_found_in_the_scraper_skill(self):
        """Guards the anchor the field list is derived from."""
        fields = derive_contract_fields()
        self.assertGreaterEqual(fields, {"title", "company", "location", "date", "url"})

    def test_every_portal_cli_emits_the_step2_contract_fields(self):
        contract = derive_contract_fields()
        failures: list[str] = []
        for portal in PORTAL_CLIS:
            search_ts = portal / "cli" / "src" / "commands" / "search.ts"
            if not search_ts.exists():
                failures.append(f"{portal.name}: no cli/src/commands/search.ts")
                continue
            source = search_output_source(search_ts)
            emitted = set(re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*):", source, re.MULTILINE))
            missing = sorted(contract - emitted)
            if missing:
                failures.append(f"{portal.name}: missing {missing} in search output")
        self.assertEqual([], failures, "; ".join(failures) or "no portal CLIs checked")



# Step 4's storage schema, derived the same way as the Step 2 contract above:
# the field list lives in the spec, never duplicated here, so a schema change
# fails this test instead of silently agreeing with a stale copy.
_STEP4_SCHEMA_BLOCK = re.compile(r"2\. Add new jobs.*?```json(.*?)```", re.DOTALL)


def derive_stored_fields() -> frozenset[str]:
    text = SCRAPER_SKILL.read_text(encoding="utf-8")
    match = _STEP4_SCHEMA_BLOCK.search(text)
    if match is None:
        raise AssertionError("Step 4 seen_jobs.json schema block not found in job-scraper/SKILL.md")
    return frozenset(re.findall(r'"([a-z_]+)":', match.group(1)))


class SeenJobsPostingDateTests(unittest.TestCase):
    """The posting date Step 2 guarantees must survive into Step 4's storage.

    Step 2's contract promises a `date` on every portal CLI's search output and
    the test above keeps every CLI honest about emitting it. Step 1b then uses
    that date to scope the run to the last 14 days - and Step 4's schema drops
    it. `first_seen` records when this scraper first saw an entry, not when the
    employer posted it, so once the run ends nothing can tell a posting
    published yesterday from one published two years ago: the Step 1b window is
    unauditable and /rank has no freshness signal to weigh.

    That failure landed for real: a freehire-search posting dated 2024-05-13 was
    scraped and ranked Strong Fit at position 1 of 133, its own scoring note
    observing the listing "may be long stale" with nothing able to act on it.
    """

    def test_step4_schema_persists_a_posting_date(self):
        stored = derive_stored_fields()
        self.assertIn(
            "posted_date",
            stored,
            "Step 4's seen_jobs.json schema stores no posting-date field, so a "
            "posting's age is unrecoverable after the run that scraped it",
        )

    def test_the_step2_date_field_survives_into_storage(self):
        contract = derive_contract_fields()
        self.assertIn("date", contract, "Step 2 no longer guarantees a posting date")
        stored = derive_stored_fields()
        self.assertIn(
            "posted_date",
            stored,
            "Step 2 guarantees a posting `date` and CI enforces every CLI emits it, "
            "but Step 4 discards it at write time",
        )

    def test_posted_date_semantics_are_documented(self):
        """A stored field the spec never explains gets backfilled by guessing."""
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        self.assertIn("`posted_date`", text, "posted_date is in the schema but never documented")
        self.assertRegex(
            text,
            r"never infer a posting date",
            "posted_date must carry the same never-backfill rule as `deadline`",
        )


class SeenJobsMarketTests(unittest.TestCase):
    """Every stored job must retain the market that selected its rules."""

    def test_step4_schema_persists_the_selected_market(self):
        self.assertIn("market", derive_stored_fields())

    def test_legacy_market_is_never_inferred(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        self.assertIn("`unknown_market`", text)
        self.assertRegex(text, r"never infer or bulk-backfill their market")


class SeenJobsDedupContinuityTests(unittest.TestCase):
    """The new key rule must not replay jobs stored under legacy keys."""

    def test_existing_urls_are_seen_regardless_of_key(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        self.assertIn("URL matches any existing `seen_jobs.json` entry", text)
        self.assertIn("do not create a\n  duplicate key", text)
        self.assertIn("register-market", text)

    def test_step4_presentation_mentions_url_deduplication(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        self.assertIn("Different known URLs are distinct postings", text)
        self.assertIn("not already in the seen list or tracker by exact URL", text)


class PortalQuerySyntaxTests(unittest.TestCase):
    """Static workflow contract adapted from upstream PR #653, not an agent run."""

    def test_plain_terms_and_branch_specific_quoting_preserve_selection_and_budget(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        step1b = text.split("#### 1b.", 1)[1].split("#### 1c.", 1)[0]
        for required in (
            "One plain term per CLI call", "`site:` expression, boolean `OR`",
            "`Query syntax:`", "inside the argument the CLI receives",
            "query_unconfirmed", "do not rewrite personal files",
            "never multiply the budget per query", "not a live syntax probe",
        ):
            # Normalize case/whitespace so layout changes do not weaken the contract.
            self.assertIn(required.lower(), " ".join(step1b.lower().split()))
        company = (REPO_ROOT / ".agents/skills/company-pages-search/SKILL.md").read_text()
        self.assertRegex(company, r"(?m)^Query syntax:.*literal title substring")
        self.assertIn("server phrase quoting and boolean operators are unverified", company)
        guide = (SCRAPER_SKILL.parent / "search-queries.md").read_text()
        priorities = re.split(r"(?m)^### Priority \d+:", guide)[1:]
        self.assertEqual(len(priorities), 4)
        for priority in priorities:
            plain = priority.split("#### Plain terms (portal CLIs)", 1)[1].split("#### WebSearch-only", 1)[0]
            self.assertNotIn("site:", plain)
            self.assertNotRegex(plain, r"\bOR\b")

    def test_cross_query_pool_keeps_identities_market_dates_and_scan_facts(self):
        text = " ".join(SCRAPER_SKILL.read_text(encoding="utf-8").split())
        for required in (
            "deduplicate the pool by exact original posting URL before Step 2",
            "within the selected market only", "Keep query strings and distinct known URLs/IDs",
            "Do not silently merge conflicting identities", "Keep every query's source/employer coverage and errors",
            "several partial calls do not establish complete coverage", "A null date stays unknown",
            "does not replace Step 2's state/tracker lookup",
        ):
            self.assertIn(required, text)


class PortalAccessPathTests(unittest.TestCase):
    """Candidate routes are explicitly distinct from accepted live connectors."""

    def test_alert_leads_reuse_existing_route_without_state_or_access_fabrication(self):
        text = " ".join(SCRAPER_SKILL.read_text().split())
        for phrase in (
            "The user manages subscriptions and supplies selected leads",
            "not a full JD or proof the posting is open",
            "existing `$job-search analyze --market <market> <URL or JD>` route",
            "without changing ranking state", "Do not fabricate `source=cli`/`websearch`",
            "Do not fetch the restricted portal to resolve a missing employer URL or ID",
        ):
            self.assertIn(phrase, text)
        for market in ('europe', 'finland'):
            guide = (REPO_ROOT / f'markets/{market}/search-queries.md').read_text()
            self.assertIn('Step 1e', guide)

    def test_indeed_mcp_client_and_region_access_remain_unconfirmed(self):
        text = " ".join(SCRAPER_SKILL.read_text().split())
        for phrase in (
            "only for Claude Connector with account sign-in",
            "keep this route unconfirmed", "non-Claude client/method and regional scope",
            "Do not guess an MCP endpoint", "Get Resume", "outside discovery scope",
            "Historical denied Job Market Finland/Duunitori paths stay blocked",
            "not retry an API version or alternate route as a workaround",
        ):
            self.assertIn(phrase, text)

    def test_indeed_routine_selection_requires_standing_country_and_client_authorization(self):
        text = " ".join(SCRAPER_SKILL.read_text().split())
        branch = text.split("**Indeed country list search (user-confirmed Indeed authorization).**", 1)[1]
        branch = branch.split("User-controlled saved searches", 1)[0]
        for phrase in (
            "one `jobSearch` POST", "`https://apis.indeed.com/graphql`",
            "approved runtime credential, without a robots precheck", "Do not retry or paginate",
            "automatically in ordinary interactive `/scrape` runs",
            "standing Indeed authorization covers automatic queries for the selected country",
            "JobSpy App identifier and runtime credential",
            "without an additional robots precheck or a repeat permission prompt",
            "`--country CN` for China",
            "Scheduled or unattended runs stay outside this rollout",
            "A one-time authorization or successful historical test does not establish standing authorization",
            "`skipped (access): unconfirmed`",
            "intersect the current workspace's selected market strategy and standing Indeed scope",
            "Query each eligible country exactly once, serially",
            "Keep Finland under its own market", "Reserve one POST per eligible country",
            "`documents/profile/source-access.md`", "--env-file=.env.indeed.runtime",
            "Do not reuse another candidate's scope or runtime environment",
            "Stop the remaining Indeed calls on access denial, rate limit or unconfirmed response",
            "exclude Indeed detail and health requests",
        ):
            self.assertIn(phrase, branch)
        self.assertNotIn("outputs/indeed-jobspy-cli-deploy-", branch)

    def test_euraxess_provisional_leads_require_detail_and_shared_budget(self):
        text = " ".join(SCRAPER_SKILL.read_text().split())
        for phrase in (
            "not an employer registry entry labelled EURAXESS",
            "https://euraxess.ec.europa.eu/jobs/search", "not server filtering or complete coverage",
            "`needs_detail=true` is a provisional lead", "not a valid record to write in Step 4",
            "same-ID canonical/title and employer/body checks",
            "do not prepend search if that exceeds a one-list budget",
            "Missing IDs or detail failures remain unconfirmed, never closed",
            "Local structural replay is not online CLI or full-JD acceptance",
        ):
            self.assertIn(phrase, text)


class SourceAccessContractTests(unittest.TestCase):
    """Static rule/table replay, not execution of an agent or portal CLI."""

    def test_enabled_is_not_permission_and_access_table_skips_unknown(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        self.assertIn("`enabled: true` do not grant access permission", text)
        self.assertIn("Missing permission evidence is `unconfirmed`", text)
        self.assertIn("LinkedIn list\nsearch follows Step 1e; direct LinkedIn detail and health probes remain excluded", text)
        # Replay pre-assessed synthetic source decisions against the actual rule
        # table. This proves table semantics only, not a runtime scheduler gate.
        actions = dict(re.findall(
            r"^\| `(permitted|denied|unconfirmed)` \| `(eligible|skip)` \|",
            text, re.MULTILINE,
        ))
        for source, access, expected in [
            ("LinkedIn detail outside the list exception", "denied", "skip"),
            ("enabled source without permission evidence", "unconfirmed", "skip"),
            ("checker missing or failed", "unconfirmed", "skip"),
            ("robots explicitly disallows", "denied", "skip"),
            ("documented permitted method", "permitted", "eligible"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(actions[access], expected)
        self.assertIn("coverage still unverified until results establish it", text)
        self.assertIn("Keep disabled portals disabled", text)

    def test_linkedin_list_is_automatic_and_bounded_only_in_selected_markets(self):
        text = " ".join(SCRAPER_SKILL.read_text(encoding="utf-8").split())
        branch = text.split("**LinkedIn list search (personal-use exception).**", 1)[1].split("User-controlled saved searches", 1)[0]
        for phrase in (
            "Include it automatically in ordinary Finland/Europe scrapes",
            "Respect the current workspace's strategy, its explicit exclusions and the shared request budget",
            "search --single-request --page 1 --format json",
            "Limit to one list call per market per run",
            "Stop LinkedIn for the rest of the run",
            "Carry successful rows as partial list leads",
            "This exception excludes LinkedIn detail and health requests",
        ):
            self.assertIn(phrase, branch)

    def test_all_request_stages_share_gate_without_access_bypass(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        step1 = text.split("### Step 1: Search", 1)[1].split("### Step 2:", 1)[0]
        self.assertIn("source-access gate", step1.split("#### 1a.", 1)[0])
        fallback = step1.split("#### 1c. WebSearch fallback", 1)[1]
        self.assertIn("Apply the source-access gate before fallback", fallback)
        self.assertIn("A CLI failure alone is\nnot permission", fallback)
        self.assertIn("bypass denied/unconfirmed permission", fallback)
        detail = text.split("### Step 2: Fetch & Parse", 1)[1].split("### Step 2.5:", 1)[0]
        self.assertIn("source-access gate again before any detail request", detail)
        self.assertNotIn("retry with browser headers", detail)
        self.assertIn("do\nnot retry with different headers, curl", detail)
        health = text.split("### Step 4.75: Portal Health Check", 1)[1].split("### Step 5:", 1)[0]
        self.assertIn("source-access gate in ordinary and probe-only health modes", health)
        self.assertIn("Denied/unconfirmed sources get no sentinel", health)
        self.assertIn("including\nexplicitly named disabled portals", health)

    def test_access_skips_and_failures_survive_zero_yield_summary(self):
        text = SCRAPER_SKILL.read_text(encoding="utf-8")
        summary = text.split("### Step 5: Present Results", 1)[1]
        self.assertIn("even if it never ran, failed, or produced no surviving jobs", summary)
        self.assertIn("skipped (access): <portal> - denied|unconfirmed; <reason>", summary)
        self.assertIn("Missing\ncoverage is unverified, never healthy/no jobs", summary)
        self.assertIn("Do not count an access skip or\nfailed request as an empty scan", summary)
        self.assertIn("do not create a job/state row for it", summary)


if __name__ == "__main__":
    unittest.main()
