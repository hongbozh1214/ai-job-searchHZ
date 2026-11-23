---
name: scrape
description: >
  Finds new job postings matching your profile via installed portal-search CLIs
  (LinkedIn, local job boards, and any skills added with /add-portal). Deduplicates
  across runs. Triggers on: job scrape, find jobs, search jobs, new jobs, job search,
  scrape jobs, /scrape
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(bun --version), Bash(bun run .agents/skills/*/cli/src/cli.ts *), Bash(python tools/job_key.py:*), Bash(python3 tools/job_key.py:*), Bash(python3 tools/rank_state.py:*), Bash(python3 tools/scrape_state.py:*), Bash(python3 tools/scrape_source_check.py:*), Bash(python3 tools/portal_catalog.py:*), WebFetch, WebSearch, Agent, AskUserQuestion
---

# Job Scraper

---

## How It Works

This skill searches job portals using the **installed portal-search CLIs** in
`.agents/skills/` (plus WebSearch as a fallback), using queries from your profile.
It deduplicates against previously seen jobs and the application tracker, and
presents new matches with a quick fit assessment.

## Invocation

The user triggers this skill by saying things like:
- "Find new jobs"
- "Scrape for jobs"
- "Any new positions?"
- "/scrape"

Optional arguments:
- A focus area, e.g. "/scrape data science" or "/scrape geophysics"
- "broad" to run all search categories, e.g. "/scrape broad"
- "health" to run the portal health check only (Step 4.75), without searching, deduplicating, or presenting jobs - e.g. "/scrape health", or "/scrape health jobnet" to probe one portal even if disabled

---

## Execution Steps

### Step 0: Load State

1. Keep `job_scraper/seen_jobs.json` and `job_search_tracker.csv` out of the
   conversation. `tools/scrape_state.py` reads both when needed and creates
   `{"seen": {}}` on the first successful write. Do not print or manually
   rewrite either whole file. Use the compact `lookup` and `add` calls in Steps
   2/4, including for China.
2. For Europe/Finland, carry exactly one market resolved by the existing
   `skills/job-search/SKILL.md` router; ask if missing or ambiguous before choosing
   strategy files. Select the **local strategy** and **source guide** together:

   | Market | Local strategy | Source guide |
   | --- | --- | --- |
   | `europe` | `documents/europe/profile/search-queries.md` | `markets/europe/search-queries.md` |
   | `finland` | `documents/finland/profile/search-queries.md` | `markets/finland/search-queries.md` |

   Do not substitute the global strategy or the other market's strategy when a
   Europe/Finland local strategy is missing. Stop that market and request its
   setup; do not generate queries from tracked examples or historical results.
   Separate an explicitly requested two-market run into two selections/summaries;
   do not pool their scope or infer a market from source domains or job locations.
   Other/legacy routes retain their existing `documents/profile/search-queries.md`
   selection and missing-file setup behavior; this table does not change China.
   Use `.claude/skills/job-scraper/search-queries.md` for query rules/examples only.

   Use sources explicitly selected by the local strategy. If it names no sources,
   use the selected market's source guide as candidates in its existing order,
   limited to this run's countries and sector. A guide is not a command to run
   every listed source. In either case apply Step 1b's source-access gate and
   enabled flags; neither installed CLIs nor the global/other-market source list
   expands the selection. Add the enabled LinkedIn list branch in Step 1e to
   ordinary Europe/Finland scrapes unless the run or local strategy explicitly
   excludes it. Also apply Step 1e's Indeed selection for interactive runs with
   standing authorization covering the selected country and method, including
   the China list branch. Do not
   rewrite personal strategy files or enable sources
   to fill a gap. Record selection reasons and sources skipped or not attempted.
   Before any live search in a normal Europe/Finland run, complete the Step 1e
   source-ledger preflight, including when `/scrape` is followed by `/rank`.
   Prior audit/online evidence may inform selection but is historical, never a
   successful request or coverage result for this run. Keep current untested
   sources unverified; preserve denied/unconfirmed/partial/errors in Step 5.

#### 0a. Europe/Finland limited-source rollout

For Europe/Finland, use Step 0's selected market strategy, enabled source flags,
source access and the current run budget. **Priority employers are preferences,
not an employer allowlist.** Discover relevant roles across employers through
eligible market-wide keyword sources as well as priority-company searches.
The table below records previously accepted reader branches, not the complete
set of employers worth searching or scoring. A maintained registry is a priority
input, not the market's employer universe.

| Entry | Initial scope | Output eligibility |
| --- | --- | --- |
| Novonesis | Existing exact Workday board, explicit --company only | Same-ID/canonical/JD-verified details only |
| VTT | Existing exact official list/TalentAdore branch, explicit --company only | Same-ID/URL/JD-verified details only |
| EURES | Europe supplemental keyword source, Step 1g | List leads provisional; only verified original-source details may advance |
| Indeed | Authorized country list, Step 1e | List leads provisional; only verified original-source details may advance |
| Work in Finland | Finland supplemental list; VTT-only detail reuse, Step 1d | Lists provisional; supported VTT details only after deployment and sandbox acceptance of this change |
| EURAXESS | Selected research-sector list/detail, Step 1f | Lists provisional; identity/employer/sections-verified details only after deployment and sandbox acceptance of this change |

This is source eligibility, not a change to personal strategies, registry,
portal toggles, scoring or platform permission. It does not enable any source
that Step 0 did not select. Resolve the market before selecting entries; never
infer it from the source domain. Split two-market runs and keep their state,
coverage and summaries separate. Do not skip an employer just because it is not
named in the table, registry or historical acceptance samples. Keep actual ATS
support boundaries: an unimplemented/unsupported reader is not permission to
guess a tenant, bypass a checker or call a restricted endpoint. Record it as
`detail_method_unsupported`, separately from denied source access, and use only
a separately documented permitted original-JD route if one is available.
Ashby permission-unconfirmed and unsupported SuccessFactors paths remain pending
capabilities; this does not exclude those employers from lawful discovery through
other independently permitted sources. LinkedIn list discovery and the authorized
Indeed country lists follow Step 1e. Freehire stays out;
blocked Job Market Finland/Duunitori/Nature paths are not retried or bypassed.
China uses Step 1e for Indeed list discovery and retains its existing local-JD requirements.

For an ordinary user-requested market search, follow Step 1's query categories
and consider relevant employers outside the priority list. Allocate the shared
budget across discovery and verification; do not spend it all rechecking a few
historical sample employers. Multiple terms and selected details may be processed
only within that run's explicit budget and each reader's documented limits.
One-keyword/one-detail maintenance probes and a VTT-only adapter contract are not
permanent market-wide employer or candidate-count restrictions. Do not query the
whole registry implicitly; select and budget company calls explicitly.
Reserve the documented worst-case request budget BEFORE invoking a CLI; output
--limit is not a page/request limit. Request-budget limits remain in force; this
scope correction is not a command to make requests during maintenance.
Honor any tighter run-specific budget; without an authorized scrape scope, skip
network and report budget_unconfirmed. An offline dry-run uses explicit synthetic
strategy, registry, fixtures and temporary state only. Never consume an old
one-off probe budget or turn it into recurring permission.

- Novonesis: CLI search can read 5 pages of 20; detail can rescan 5 pages plus
  1 GET. Each Workday operation can visit up to 4 same-origin hops, each gated.
  Conservatively reserve up to 20 protected requests for search, 24 for detail,
  and their strict-checker calls; if the run's budget cannot cover a call, defer
  that call. Do not invent a max-pages CLI flag or call --limit 1 a one-page cap.
- VTT: normally search 1 GET and detail 1 list GET plus 1 matched detail GET;
  the existing list reader may visit up to 4 allowed-board hops. Reserve up to
  4 protected requests for search and 5 for detail, plus their checker calls.
- EURES: search 1 POST for page 1/10; detail at most 1 API GET plus 1 explicitly
  supplied supported original-page GET, each gated. No Finland country filter
  is verified, and no implicit list precedes detail.
- Indeed: reserve one POST per selected country, up to 6 for Europe and
  up to 1 for Finland or China. Each POST uses one keyword and reads the first
  page. Preserve explicit exclusions and any tighter run-specific budget.
- Work in Finland/EURAXESS: each list invocation reads one page and is separately
  gated. Budget each selected detail independently; do not assume a historical
  one-detail probe cap applies to every ordinary run. WIF re-reads the same
  query page, reuses the official VTT list (up to 4 gated board hops), and reads
  one matching TalentAdore detail (reserve 6 protected requests plus checkers).
  The accepted VTT Jobly extension uses one WIF re-read plus one selected Jobly
  GET (reserve 2 plus checkers),
  without the VTT board. Its independent source gate cannot be skipped.
  EURAXESS detail re-reads one list page and one selected detail (reserve 2 plus
  checkers). Do not prepend a search when its extra list would exceed budget.
  Until that acceptance, retain the deployed list-only restrictions.

A rejected, unknown, challenged or rate-limited source stops without retry;
retain errors/Retry-After and any partial coverage. Keep other independently
eligible sources separate. Skip deferred calls explicitly rather than reporting
no jobs. Budget is shared across keywords, source calls, markets and redirects;
never reset it per query. Run checker and adapter access checks where required
by the selected route.

Keep list-only/unverified-JD leads visible in Step 5 and the provisional review
queue defined in Step 0b; they are not excluded from evaluation. They stay outside
verified-only Step 4/state writes. Missing company or stable identity cannot be
guessed. For usable verified details, pool by exact original
posting URL within the selected market, then use the existing lookup/add
contract; new means unseen, not recently published. Preserve source/employer
coverage/errors even if all rows become duplicates. A successful detail does
not upgrade partial to full coverage, and null publication dates remain null.
A source's historical acceptance is not a successful read for the current run.

The discovery scope also does not exclude existing verified full JDs from the
normal `/rank` or analyze route just because their employer is outside a recent
maintenance sample. Missing full JD or unconfirmed identity prevents a complete,
verified score, not provisional evaluation under Step 0b. Never invent missing
salary/language/JD facts, change the candidate's thresholds, or treat a maintenance
acceptance tool as a scoring rule. If no selected leads reach verified JD, report
full scoring incomplete and still present retained leads, provisional scores or
intervals and the exact reader/access/identity/budget gaps; do not label the
market-wide task complete. Other candidates with independently permitted working paths may continue
inside the shared budget; an actual access denial is never retried or bypassed.

This correction changes no scheduler or source toggle and grants no new platform
permission. It is not evidence that a real weekly or complete scrape has run.

#### 0b. Europe/Finland: retain evidence-limited candidates

For Europe/Finland, request access, posting identity and evaluation are separate
decisions. This section is the canonical policy for both `/scrape` and `/rank`;
China's existing complete-local-JD workflow is unchanged.

A failed detail request, blocked/unknown access, unsupported reader, 403/404/429,
parse error or missing JD does not discard an already observed list lead and does
not by itself establish expiry, a hard-gate FAIL or an unsuitable job. Keep its
actual title/employer/link, source coverage and error in the visible candidate
pool. Stop restricted requests without retry/bypass; continue evaluating evidence
already obtained and independently eligible candidates inside the run budget.
Never invent a list when the list itself could not be read. Report source-level
access failures even when no candidate identity was available.

Use these identity decisions; parser rejection is evidence of an unresolved
association, not automatically proof of a different posting:

| Identity evidence | Candidate action | Detail action |
| --- | --- | --- |
| `verified` | `retain` | `use_verified_detail` |
| `unconfirmed` | `retain` | `flag_association_pending` |
| `confirmed_mismatch` | `retain_original_lead` | `reject_wrong_detail_pair` |

Only confirmed different postings justify rejecting their association: for
example, explicit authoritative same-namespace IDs and canonical pages identify
different roles. Show the conflicting fields, links and reason to the user.
Do not declare mismatch just for missing identifiers, employer abbreviations,
case/formatting or a publisher's title suffix. An uncertain detail may receive a
separate provisional assessment labeled association pending; do not merge its
unconfirmed requirements/employer facts into the original lead as verified facts.
A wrong detail is not a reason to silently erase the original list lead.

**Score from available posting text first.** For deduplicated Europe/Finland
candidates, use substantive text tied to the same posting, including an Indeed
first-page description, an eligible LinkedIn detail, or another source's usable
body. Produce a provisional score or interval before attempting any employer-original
lookup. Original verification is not a prerequisite for provisional scoring.
In a provisional-only run, leave original verification of the high-ranked
shortlist to the user. Use the existing permitted verification path when the
user requests verified scoring or original-posting checks.

**Provisional evaluation remains available.** Evaluate only what observed list,
snippet, saved JD or fetched detail actually supports, using the existing profile,
dimensions and weights. Mark unsupported dimensions unknown; do not invent scores,
fill unknowns with zero, renormalize known weights or call a title-only assessment
a complete JD score. For weighted dimensions whose evidence is sufficient, let
L be their summed weighted contribution and U = L + the unknown weight. Report
`provisional_interval=[L,U]` plus the evidence coverage and missing information.
For title-only LinkedIn leads, report high, medium or low preliminary relevance
from the title, employer and location. Keep these in a separate list without a
numeric score. If available body text supports no scoring dimension, report
[0,100] and explain the lack of discriminating evidence.
When all dimensions can be supported but access/association remains uncertain,
show the triage score explicitly provisional with those issues; it is not a
verified recommendation. Salary, language, contract and other unknown hard-gate
facts stay FLAG, not invented PASS/FAIL; explicit actual deal-breakers still apply.
An unavailable/missing salary does not authorize changing the user's threshold.

Present provisional results in a separate visible table with role/company/link,
score or interval, body source, original-verification status and key unknowns
such as pay, required language, work authorization and contract. Order by the
supported score (the lower bound for an interval), while keeping the upper bound
visible for manual review. Do not count provisional rows as ready for formal scoring.
They remain in the evaluation queue even if a full-score count is zero. In a
combined scrape/rank run pass these in-memory leads to this provisional table;
do not require a formal seen-job row just to show their assessment. Provisional
rows are report-only: do not send incomplete scores to `rank_state.py apply`,
write `ranked`/`expired`, overwrite historical scores or invent a new state schema.
A confirmed deadline/closure may still be reported under existing expiry rules;
network failure or an identity error is never closure evidence on its own.

### Step 1: Search

Use only the local strategy and source selection resolved in Step 0. By default,
run its top 3 priority query categories. If the user said "broad", run all query
categories within that selected market; broad does not enable every source. If the
user specified a focus area (e.g. "data science"), prioritize that category. A
missing local strategy stops the selected market as specified in Step 0.

**Use eligible installed CLI tools as the primary search mechanism.** Apply the
source-access gate below before any network call, including WebSearch fallback
when a CLI or `bun` is unavailable.

#### 1a. Check bun availability

```bash
bun --version
```

If this fails (bun not installed), consider **1c (WebSearch fallback)** only for
eligible sources and note the fallback in the Step 5 output. Missing `bun` is not
permission to access a source.

#### 1b. Run CLI tools (primary — run these in parallel where possible)

Discover installed portal skills from their short frontmatter only. Keep two
roots separate: the **project data root** contains `tools/`, `.claude/`,
`documents/`, `company_pages.json`, and job state; the **skill discovery root**
contains the installed `.agents/skills/`. Run project commands with the project
as cwd. Select the discovery boundary explicitly for the actual deployment:

| Layout | Command from the project data root |
| --- | --- |
| Standalone checkout (skills inside the project) | `python3 tools/portal_catalog.py --root .` |
| Workspace with an `ai-job-search/` child project and skills at the workspace root | `python3 tools/portal_catalog.py --root ..` |

The second form permits only that direct workspace parent, never an arbitrary
ancestor or external root. Do not remove boundary checks, move skill directories,
or retry with successively wider roots after a discovery error. From another cwd,
use an absolute script path and an explicit absolute discovery root. For example,
from the configured workspace this is equivalent to the second form:

```bash
python3 ai-job-search/tools/portal_catalog.py --root .
```

The JSON remains an array of each skill's name, path and enabled flag. `path` is
relative to the selected **discovery root**, not necessarily the project or cwd;
resolve it against that root before reading the skill or locating its CLI.
Missing directories, escaping links, and invalid frontmatter are discovery
errors, not evidence that no portals exist. Report the error and use only the
documented, policy-permitted fallback; never edit a toggle to recover discovery.
Report disabled names
without loading their full descriptions. Read the full `SKILL.md` **only** for
enabled skills selected for this market, or for the one named portal in
`/scrape health <portal>`. Its own documentation supplies exact CLI flags; do
not guess them. A new `/add-portal` skill is picked up automatically.

**Honor the `enabled` toggle.** Missing means enabled. Skip disabled portals
in ordinary runs and record their names for the Step 5 summary.

**Source-access gate (search, fallback, detail and health).** Installation and
`enabled: true` do not grant access permission. Before scheduling a source, read
its selected skill's access restrictions and the applicable source/tool rules.
User authorization is necessary. Route LinkedIn list search and authorized Indeed
GraphQL country lists to Step 1e before evaluating the general access table.
Apply the table to the other request paths. Use the documented eligibility and
stopping rules in Step 1e for its two list methods.
Where the request path requires the real checker, retain its permission check
for the actual path and every permitted redirect; do not replace it with this
selection gate. Missing/failed checker or unknown permission stays unconfirmed.
Keep this source-level decision and its evidence/reason in the run summary:

| Source access | Network action | Summary |
| --- | --- | --- |
| `permitted` | `eligible` | Access permitted for the documented method/scope; coverage still unverified until results establish it. |
| `denied` | `skip` | `skipped (access): denied`; coverage unverified, never healthy/no jobs. |
| `unconfirmed` | `skip` | `skipped (access): unconfirmed`; coverage unverified, never healthy/no jobs. |

Missing permission evidence is `unconfirmed`, not `permitted`. LinkedIn list
search follows Step 1e; direct LinkedIn detail and health probes remain excluded.
Never fetch people-search links.
Keep disabled portals disabled; a named health request can select a disabled
portal but still must pass this gate. Never edit toggles to recover access.

For each **selected enabled and access-permitted** portal skill on the general path:

1. Read its `SKILL.md` to find the correct `bun run …` invocation and supported flags.
   Use the selected skill's resolved path while keeping the project as cwd.
   Discovery `--root` does **not** set a portal CLI's data root. Before using a
   registry-driven CLI, verify how that CLI locates its data: a tool that derives
   `company_pages.json` or `tools/robots_check.py` from its own module location
   can resolve to the workspace after following a skill link, even with project
   cwd. If it cannot explicitly select and verify this project's data root, mark
   that CLI path incompatible and use the permitted fallback. Do not copy or read
   a workspace-level registry as a substitute, change state-helper defaults, or
   modify protected skill code to recover it. Repair of such a protected adapter
   requires a separate patch/deployment handoff.
2. Use that priority's **Plain terms** from the selected local strategy, never
   tracked examples or `[YOUR_...]` placeholders. **One plain term per CLI call**
   (a multi-word role is one term), using the portal's documented keyword flag.
   Never pass a `site:` expression, boolean `OR`, or combined alternatives to a
   CLI. For a legacy priority without usable Plain terms, derive only explicit
   role/skill terms from that same priority's personal queries: remove the site
   selector and separately specified location, and split alternatives into terms
   while retaining multi-word roles. If that separation is ambiguous, skip that
   query and record `query_unconfirmed`; do not guess, broaden the search, or read
   another market's strategy. Do not rewrite personal files.

   Follow the portal's `Query syntax:` line for literal quote/operator semantics,
   not another portal's behavior. Shell grouping quotes are not literal quotes
   inside the argument the CLI receives: `--query "protein engineer"` sends bare
   `protein engineer`, while `--query '"protein engineer"'` also sends the double
   quote characters. Add literal quotes only when that branch documents them as
   supported. Missing/unverified syntax gets one bare term with no phrase-match
   claim and no operators, not a live syntax probe. Existing source-access gates,
   enabled flags and per-source request/page budgets still apply across all terms;
   defer terms that exceed the budget, never multiply the budget per query.
3. Scope to the last 14 days using the portal's supported recency **filter** flag (`--jobage`, `--since <YYYY-MM-DD>`, etc. — as documented per portal). A portal with **no recency flag** (jobdanmark offers none) still gets scoped: every portal's search output carries a `date` field, so filter client-side — drop results whose `date` is older than 14 days after the call returns, and never invent a flag the portal's SKILL.md does not document (the CLIs reject unknown flags). `--order PublicationDate` is a sort, and a sort is not a filter — pairing it with a `--limit` is a defensible approximation on a portal that offers nothing better (jobnet), but apply the client-side date filter on top all the same.
4. Cap results to ~20 per call using the portal's limit flag.
5. Use `--format json` for machine-readable output.

Run all portal CLI calls in parallel where possible using the Agent tool. Before
pooling `results`, retain each response's source portal, per-employer `meta.errors`
and `meta.coverage` in the run summary; do not reduce the response to its array.
For company-pages-search, use only the employers selected for this market and its
exact documented `--company` flag; omitting it queries the whole registry. Follow
its skill for the supported Workday and VTT list/detail branches and budgets.

For each employer consume coverage and errors independently, even after exit 0:

- `partial` retains usable identity-verified jobs but never proves full coverage.
- `blocked`, `rate_limited`, `parse_failed`, `unknown` or any per-employer error
  means incomplete/unconfirmed, not no openings or confirmed closure. Preserve the
  reason and Retry-After. Do not retry or choose a fallback to bypass a denied or
  unconfirmed checker, access restriction or rate limit.
- `valid_empty` is an explicitly verified empty scan within its scope. Zero emitted
  results, a client-side limit/filter, or absent coverage is not that evidence.
  `complete` describes only the adapter's stated scope, not all employer channels.

Keep these employer-level facts through detail, deduplication and Step 5, including
employers whose jobs are all filtered or duplicates. Do not create a job/state row
for an employer-level failure. No new state schema is required: keep coverage in
the run summary, while job records keep the existing Step 4 contract.

Pool usable results for Step 2 with their source portal tag and original stable ID,
canonical URL, and nullable date. Apply the 14-day filter only to known publication
dates. A null date stays unknown; neither capture time, first_seen nor today's date
is a replacement. A deduplication decision of `new` means unseen, not recently posted.

Across terms and portals, deduplicate the pool by exact original posting URL
before Step 2, within the selected market only. Keep query strings and distinct
known URLs/IDs; do not merge different jobs just because their titles match.
Do not silently merge conflicting identities for the same URL; retain the
conflict for review. Keep every query's source/employer coverage and errors in
the run summary even when all its jobs are duplicates or filtered out. Pool
deduplication does not replace Step 2's state/tracker lookup or grant access to
detail, and several partial calls do not establish complete coverage.

If a CLI tool exits with a non-zero code, preserve its error and unverified
coverage; continue with independently eligible sources. Failure is not no jobs
or permission for a fallback.

#### 1c. WebSearch fallback

Apply the source-access gate before fallback. Use `WebSearch` only when that
method/scope is permitted and a selected source has no CLI, `bun` is unavailable,
or an eligible CLI has an ordinary runtime/parse failure. A CLI failure alone is
not permission. Do not use fallback, another client, headers or sentinel probes
to bypass denied/unconfirmed permission, a challenge, 403 or 429. Stop that source;
preserve the restriction and Retry-After without retrying. Independently permitted
sources may continue; do not relabel blocked-source coverage as successful.

Use the site-specific query strings from the selected local strategy directly
as WebSearch queries for these eligible portals. Source-guide examples are not
personal queries or proof of a working list/detail entry.

Tag each fallback result as WebSearch-sourced, keeping the portal tag when the fallback stands in for an installed portal whose CLI failed. Step 4 persists this as the entry's `source`, and Step 5 reports which portals ran on the fallback this run.

#### 1d. Selected Work in Finland structured fallback

When Step 0 selects Work in Finland, use the enabled `company-pages-search`
skill's explicit source mode; this does not query any company registry or enable
another source. Apply Step 1b's source-access gate and honor the skill's toggle.
Do not schedule an unfiltered company search to prepare this source.
Read the company skill for exact flags, then invoke its existing CLI:

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts search --source work-in-finland --format json
```

Pass one of Step 0's plain role terms through `--query` using Step 1b's query
rules, not search-engine `site:` syntax or unverified category/city IDs.
Do not combine `--source` with `--company`. The WIF VTT-only detail extension
below remains separately gated and is unavailable until deployed/accepted.
This is an independent source read, never a proxy or recovery path for a denied
Job Market Finland request; its upstream provider remains unverified.

The reusable source branch sends `GET https://www.workinfinland.com/api/jobs/?limit=6&page=1`
with the optional encoded query. It applies the real strict checker to the exact URL,
15-second request timeout and 128-KiB streamed body cap, without following redirects,
retry, browser headers or another client. Missing/failed checker stays unknown.
Historical success is not current permission. The CLI does not require native
WebFetch, a temporary registry or any script in outputs/. If it fails, retain the
error; do not recover using a one-off script or weaken its gate.
Read at most one page: the observed mobile page size is 6 (desktop 12); no complete
board claim follows from server counts. `--limit` caps emitted results only, not
requests or downloaded records; `--location` filters this page client-side.
Retain received_count, server counts, source `meta.coverage` and `meta.errors`
even if all results are filtered or duplicated. Do not fetch autocomplete or
unsupported external JD automatically. No login, cookies or source-JS execution.

Validate a JSON object with `jobs` as an array and nonnegative integer
`totalJobs`/`totalPages`. Validate each job's nonempty title, employer name and
absolute HTTPS posting URL; reject credential-bearing URLs. Preserve the supplied
`externalUrl`, including its query, without inventing an ID, replacing it with
the listing URL or stripping unknown identity parameters. Missing identity
fields are record errors, not permission to guess or silently report no jobs.

Map only these source fields into Step 2's existing result contract:

| Result field | Work in Finland value |
| --- | --- |
| title | title |
| company | employer.name |
| location | employer.city |
| url | externalUrl |
| date | null |

Missing location stays unknown. No publication/update date or stable ID was
present in the observed card schema: keep them unknown; use the existing
company/title/URL deduplication in Step 2. `expireDate` is not publication date
and is not proof of closure or an application deadline without posting evidence;
an invalid or absent deadline stays null. Never use
capture time, first_seen or today's date as publication date.

Keep source coverage and errors in the Step 5 summary even when all jobs are
duplicates or excluded. A validated nonempty page has `partial` coverage; an
explicit empty array with totalJobs=0 is `valid_empty` for that query/page only,
not a full-market check. An empty page with nonzero total is `unknown`; malformed
JSON/schema or missing identity is `parse_failed`. Denied/unknown checker,
403/challenge, 429 or failed requests retain their restriction/error and unknown
coverage; stop without retry. Never imitate the frontend's error handler that
clears the cards and counts to zero. Server counts do not prove page coverage.

Use `portal=work-in-finland` and `source=cli`; report
`mechanism=company_pages_cli_source` in the run summary. `source_ats=generic`
identifies the generic reader, not a verified employer ATS. The source has no
registry entry and does not broaden a company search.
Do not change old records or add a new state schema. Route usable results into
Step 2's existing batched lookup, not a separate state/ingestion path. The
external posting is a separately gated source: list identity is provisional
until its ID/canonical URL and full JD are checked there. No JD or full-workflow
success may be claimed from this list alone. An isolated dry-run uses only
explicit temporary state/tracker paths, never Step 2/4's production defaults.

VTT-only detail extension (candidate until deployed and actual sandbox accepted):
`detail --source work-in-finland --id <exact TalentAdore ID> --query <same list query>`
uses no registry. Omit query only if the selected list was unfiltered. Only a
card explicitly naming VTT with the supported HTTPS TalentAdore URL may enter;
the ID is derived from that URL, not invented as a source-wide ID. Re-read one
WIF page, then reuse existing VTT official-board membership and structured-detail
checks. Require exact source/official URL and compatible titles, same structured
ID/URL and nonempty description; unsupported employers/links remain leads.
Do not substitute list summaries. A list miss/denial/mismatch/missing body fails
without fallback or closure. Preserve both source coverage and errors, canonical,
stable ID, null publication date; VTT wire counts/Retry-After not exposed by the
existing reader remain unknown, never guessed. No retries. Existing redacted
structure fixtures do not independently prove full live JD completeness.
Only successfully verified details may reach Step 2/4 after the normal gates;
retain every list's partial/errors even after duplicate removal.

Jobly extension (local candidate; do not use until deployed and sandbox accepted):
VTT cards with an exact supported www.jobly.fi/en/job/<slug>-<ID> URL may expose
`jobly:<ID>`. Use that exact returned ID and the same list query in existing
`detail --source work-in-finland`, never convert it to a TalentAdore ID.
Re-read one WIF page and separately strictly gate one matched Jobly page; require
exact same-slug/same-number declared /tyopaikka/ canonical, one JobPosting,
matching VTT employer/title and the observed description/requirements structure.
A declared language canonical does not authorize fetching it. Keep source_url
as the supplied original and canonical_url/url as the validated declared URL;
existing URL dedup consumes verified canonical details and retains raw-source
provenance. Same titles on Academic Positions/other domains are not dedup proof.
Unknown dates remain null; preserve every source's partial/errors/Retry-After.
Do not infer independent full-body completeness from nonempty structured text.
Wrong identity/missing body/denial/redirect/429 stops without a list-summary
fallback or closure claim. This changes no source activation, market selection,
personal criteria, scheduler or formal state. For every unsupported or failed
detail, Step 0b retains the lead and its provisional assessment; this reader's
VTT-only implementation is not an employer exclusion for the overall workflow.

#### 1e. LinkedIn / Indeed and user-controlled discovery leads

**Europe/Finland source ledger.** Before live search, record a decision for
LinkedIn and each Indeed country in this market using the dedicated list rules
below. Reconcile the same scope before presenting results, including after a
run resumes. Run both checks from the project directory:

```sh
python3 tools/scrape_source_check.py plan --market <europe|finland> --input <local-plan.json>
python3 tools/scrape_source_check.py report --market <europe|finland> --input <local-outcomes.json>
```

Keep separate, local ledgers for the two markets. Use a JSON object keyed by
`linkedin` and `indeed:<country-code>`. The standard Europe scope expects
`GB`, `DK`, `DE`, `NL`, `BE`, and `CH`. Finland expects `FI` only.
Pass the same `--countries` in both checks when the selected market strategy
or run explicitly narrows Europe before search. Record a row even for an
ineligible country. Keep that scope through closeout.

Record `planned` or `skipped` at preflight and reserve the documented budget.
At closeout record `ran`, `failed`, `skipped`, or `deferred`. Include a short,
nonsecret evidence note for each disposition other than `planned`. For a
known source-specific refusal use `access_denied`. For absent standing Indeed
authorization for this method or country use `missing_indeed_scope`. A generic
`access_unconfirmed` verdict is not a valid reason to skip either list path.
Record any other concrete blocker with the checker’s documented reason code.

Resolve missing plan rows before network work. Before reporting, recover
missing outcomes or safely complete unattempted calls still in scope and
budget. Never resend a pending or uncertain request to satisfy the check.
Report each uncovered or partial source and country. Failed, skipped and
deferred rows do not establish zero jobs. This ledger validates the accounting;
only tool outcomes establish the actual calls and coverage.

**LinkedIn list search (personal-use exception).** Include it automatically in
ordinary Finland/Europe scrapes when the installed `linkedin-search` skill is
enabled and the run allows discovery. The user does not need to name LinkedIn.
Respect the current workspace's strategy, its explicit exclusions and the shared
request budget. The workspace owner's standing choice skips LinkedIn's terms and
robots precheck for this list call only.
Report inclusion as `user_opt_in`, not as platform permission.

- Use the installed LinkedIn CLI with `search --single-request --page 1
  --format json`, plus one keyword from the selected market strategy and one
  explicit location within that market. Limit to one list call per market per
  run. If the installed CLI lacks `--single-request`, record
  `reader_incompatible` and skip it.
- Stop LinkedIn for the rest of the run on a redirect, challenge, login wall,
  timeout or unsuccessful response (including 403 and 429). Record errors and
  Retry-After when supplied. Do not retry, change clients or follow the failure
  through WebSearch. Other sources may continue.
- Carry successful rows as partial list leads through normal market-scoped
  deduplication and provisional evaluation. A missing date stays unknown.
  Keep the list error or partial coverage even if no leads survive. This
  exception excludes LinkedIn detail and health requests.

A vendor interface needs documented permission for its actual data, method and scope.

**Indeed country list search (user-confirmed Indeed authorization).** Use the
company CLI `search --source indeed --query <keyword> --country <code> --format json`
to send one `jobSearch` POST to `https://apis.indeed.com/graphql` with the
approved runtime credential, without a robots precheck.

Include Indeed automatically in ordinary interactive `/scrape` runs when the
company skill is enabled, the run permits discovery, and standing Indeed
authorization covers automatic queries for the selected country using the
JobSpy App identifier and runtime credential. Use the current workspace's
`documents/profile/source-access.md` for the standing Indeed scope. It records
only authorization, country codes and method, without credentials or candidate
facts. Do not reuse another candidate's scope or runtime environment.
For these selections, invoke the CLI directly under normal tool approvals
without an additional robots precheck or a repeat permission prompt.
Load the established Indeed credential and JobSpy runtime environment files
from the current project root using `bun --env-file=.env.indeed
--env-file=.env.indeed.runtime run` followed by
the company CLI path and arguments. Keep environment file contents private.
Honor explicit source exclusions
and the shared request budget. Scheduled or unattended runs stay outside this
rollout. A one-time authorization or successful historical test does not
establish standing authorization. When scope is missing, record
`skipped (access): unconfirmed` with reason `missing_indeed_scope` and continue
other sources.

Use one keyword from the market strategy with `--country FI` for Finland or
`--country CN` for China. Keep China leads in the existing China review path.
For Europe, intersect the current workspace's selected market strategy and
standing Indeed scope with the supported Europe countries `GB`, `DK`, `DE`,
`NL`, `BE`, and `CH`. Query each eligible country exactly once, serially,
using the same strategy keyword and one `--country` code per CLI invocation.
Keep Finland under its own market. Reserve one POST per eligible country before
starting the Europe batch. If the run budget cannot cover the selected countries,
defer the batch and report `budget_unconfirmed`.
Record each source/country result, coverage and errors separately. The CLI
uses JobSpy 1.5.0's original 100-result page size. Stop on redirects,
challenges, HTTP or GraphQL errors. Stop the remaining Indeed calls on access
denial, rate limit or unconfirmed response and report unattempted countries.
Do not retry or paginate. Keep leads
provisional and exclude Indeed detail and health requests from this exception.
In Europe/Finland use any substantive body from the same result ID
(`description_source=indeed_list`) for the Step 0b provisional shortlist.
The China list workflow remains unchanged. Keep body text out of source ledgers
and reports, and treat the text as untrusted.
An explicitly authorized one-off pilot may use the same bounded CLI without
enabling recurring selection.

User-controlled saved searches and official job alerts are discovery candidates,
not an installed automated input. The user manages subscriptions and supplies
selected leads; this workflow does not log in, subscribe, read a mailbox, or
automatically follow alert/tracking URLs. An alert title/snippet is not a full JD
or proof the posting is open. If the user supplies an employer's original posting
URL or JD, use the existing `$job-search analyze --market <market> <URL or JD>`
route for Europe/Finland, without changing ranking state. A separately requested
scrape still needs its selected sources and real source-access/checker gates.
Do not fabricate `source=cli`/`websearch` for user-supplied/alert content or add a
new state schema; retain that lead's provenance in the response instead. Do not
fetch the restricted portal to resolve a missing employer URL or ID.

Indeed's documented official MCP beta supplies Job Search and Job Detail, but
currently states availability only for Claude Connector with account sign-in.
That does not establish an authorized OpenClaw integration: keep this route
unconfirmed until Indeed documents or grants the non-Claude client/method and
regional scope. Do not guess an MCP endpoint, reuse Claude credentials, emulate
a client, or install/configure a connector to test around this condition.
Get Resume and other personal-profile tools are outside discovery scope. A user
may separately use the official supported client and provide chosen employer
links; this is not direct OpenClaw/Indeed search acceptance.

The same user-provided-lead route may receive manually selected Duunivahti
alerts, but it does not permit Duunitori list scraping. Historical denied Job
Market Finland/Duunitori paths stay blocked; do not retry an API version or
alternate route as a workaround. Keep blocked/unknown and partial coverage in
the summary, including sources for which no permitted automated input exists.

#### 1f. Selected EURAXESS source

When this source is selected and the deployed company CLI actually supports it,
use its documented `search --source euraxess` or `detail --source euraxess --id`
branch, not an employer registry entry labelled EURAXESS. Honor the parent skill
toggle, source-access/strict checker gate, selected market and shared budget.
The verified list entry is `https://euraxess.ec.europa.eu/jobs/search`; `/jobs`
is an introduction. One-page client filtering is not server filtering or complete
coverage. Keep the per-source meta.coverage/errors even when no jobs survive.

List employer/publication fields can be unknown. An empty company with
`needs_detail=true` is a provisional lead, not a valid record to write in Step 4.
Require the source detail's same-ID canonical/title and employer/body checks
before passing identity-complete records to existing batched deduplication.
The detail metadata extension is candidate-only until deployed and sandbox
accepted; preserve list warnings alongside separate detail coverage, including
on failure and plain output stderr. Canonical URL is explicit. Section-level
reading does not prove independently complete live JD; report exactly the
observed Offer Description/Requirements/Additional Information scope.
Detail rescans the first page then reads at most one matched posting: account
for both requests and do not prepend search if that exceeds a one-list budget.
Missing IDs or detail failures remain unconfirmed, never closed. Preserve
partial, source errors and unknown publication dates; do not use deadlines or
header/capture dates as publication. Local structural replay is not online CLI
or full-JD acceptance; undeployed/unsupported branches stay unverified rather
than silently falling back to an unfiltered registry search.

#### 1g. Selected EURES list source

EURES is eligible for the user-approved limited rollout in Step 0a, when selected
for Europe and separately permitted/budgeted. This removes the maintenance-only
selection block for that scope; it does not start a scrape or grant access,
unlimited requests, Finland country filtering or complete market coverage.

Only when selected, permitted and supported by the deployed company CLI, use
`search --source eures` under the parent skill toggle and shared request budget.
Do not add an EURES employer to the personal registry or silently query all
employers if the source flag is unsupported. The CLI reads one unfiltered page
of at most ten records with the documented minimal POST body. Only if the
deployed CLI includes the server-keyword change, `--query` sends a trimmed plain
keyword under EVERYWHERE; do not title-filter its description matches again.
The earlier deployed CLI used a title-only client filter: a local candidate is
not deployment evidence. `--location`/`--limit` still filter output only; country
selection remains unsupported, and no query is a Europe-wide complete scan.
Preserve meta.coverage.query_scope/country_scope where provided; an omitted
query means an unfiltered page, not a targeted check.

Treat results as provisional leads: stable raw ID/title are observed, while
employer, location, publication, canonical webpage and full JD remain unknown.
The `url_kind=unverified_api_detail_reference` URL is a declared source API
reference, not a verified posting webpage; `canonical_url=null` and
`needs_detail=true` must survive. Do not write these leads into Step 4/state or
present them as verified recommendations. The deployed detail branch supports `detail --source eures --id <exact raw search ID>`; only call it after
explicit source permission and verified deployment, not generic company detail.
Without an explicitly supported original link it spends one strict checker
and one GET, requires an exact response ID/unambiguous profile, and returns
`JD_completeness=unverified`, `needs_detail=true`, `canonical_url=null` and partial
coverage/errors. Such API-only records stay outside Step 4: a description field
and its length do not prove the complete JD; employer homepages are not canonicals.

The deployed original reader may additionally read only a supplied BA posting
link bound to the exact API reference: maximum two GETs, each separately gated
by the real strict checker. Require canonical/JobPosting URL and identifier
agreement, employer agreement, compatible titles and duties/requirements markers.
Use only the original JobPosting.description as JD; preserve API raw identity,
title and description separately, never splice bodies or delete meaningful
hyphens. `needs_detail=false` here means that canonical description was read,
not a full source scan or independent proof of every section's completeness.
Both branches remain partial, and dates remain unknown. A failed original read
must not silently downgrade to API text or imply closure. API-only results remain
provisional. Only currently identity/canonical/JD-verified original-source details
may reach Step 2 under Step 0a, market selection, current-run access and budget,
and existing Step 4 deduplication/ingestion preconditions. Prior sample acceptance
does not establish that another source shape or current posting passed.
The detail-only CLI reports title_crosscheck=not_performed; the original title
relation is separate metadata, not a repeated list/title check.

Retain per-source meta.coverage/errors, request count, source-declared totals
and Retry-After. Partial/filter-zero is not a complete scan; failed/unknown
reads are not no jobs, and valid_empty applies only to this query page. Dates
stay unknown: source creation/modification fields and capture time do not
replace publication. Platform relevance scores do not replace project scoring.
Missing IDs or
failed detail checks never imply closure. A prior one-off API probe, synthetic
CLI replay and actual agent workflow acceptance are distinct evidence layers;
undeployed code remains unverified and does not formally enable this source.

### Step 2: Fetch & Parse

Apply the source-access gate again before any detail request, including an
indexed result whose original source was not directly fetched. A search-index hit
does not authorize fetching the target or prove that its posting is open.

In Europe/Finland, follow Step 0b first when usable same-posting body text is
already available. A provisional-only run does not request the employer original
solely to score that body.

For each promising result from Step 1:

**From CLI results:** Search output already includes title, company, location, date,
and URL. For jobs worth a deeper look, fetch full detail with that portal's `detail`
command (see its SKILL.md — do not guess flags) to extract **key requirements**,
**application deadline**, and a brief description snippet.

A detail failure, unconfirmed ID, HTTP 404 or missing description is not confirmed
closure. Preserve its error; do not silently join another listing or mark it expired.
For Europe/Finland retain the lead for Step 0b provisional evaluation; only a
confirmed different posting rejects the detail association, with the conflict
shown to the user. Do not equate a strict parser failure with exclusion.
Preserve partial list coverage even after a successful detail. A description-presence
flag alone does not prove complete JD content. Keep unknown dates/deadlines null.

**Closed-at-source detection:** `linkedin-search detail` also returns `isActive`.
`false` means the posting page itself renders LinkedIn's "No longer accepting
applications" banner — the job died between being indexed and being fetched (expired
LinkedIn URLs redirect to *similar live jobs*, so a search hit can be a ghost). Mark
such a job, never silently drop it: write its entry to `seen_jobs.json` in Step 4 with
`"status": "expired"` and leave it out of the Step 5 presentation — an absent entry
looks identical to a job never seen, and the recorded status is what makes a later
ghost report self-triaging. `isActive: true` is only the absence of that banner, not
proof the posting is open; deadlines and dead URLs remain `/rank`'s job.

**From WebSearch results:** Use `WebFetch` on the posting URL and extract the same
fields manually only within the permitted method/scope. On 403, 429, a challenge
or unknown permission, stop that source and preserve the reason/Retry-After; do
not retry with different headers, curl or another environment.

**Store a URL that actually resolves to the posting.** A listing-page URL with a
`#fragment` appended (`.../jobs/ciso/#ikerian`) is not a posting: it fetches fine and
returns unrelated job titles, which makes every later `/rank` and `/apply` run fail on
that entry. When WebSearch only yields a listing page, search the employer's own careers
site for the role within the permitted method/budget and store that URL instead.
If unresolved, keep the lead as provisional with `posting_url_unconfirmed` under
Step 0b rather than saving the fragment as a verified posting or dropping it.

Before fetching full details where the search result has a usable company,
title and URL, and again for any remaining candidates after extracting those
fields, save just `{company,title,url}` objects in a temporary JSON array
outside the repository. Query in one batch:

```bash
python3 tools/scrape_state.py lookup --input "<candidate-array.json>"
```

The result contains an `index` matching the array, `decision`, and only the
relevant key/market/status or reason. `new` includes the canonical key (or a
URL-specific collision key); `seen_url`, `tracked`, and `ambiguous` are never
added. If `seen_url` belongs to the other Europe/Finland market, use the
registration command below. Recheck immediately before saving in Step 4:
`add` validates every entry against the current state again. If a candidate
lacks a company or title, resolve it from the original posting first; never
guess an identity from a snippet.

For every candidate:
- If the URL matches any existing `seen_jobs.json` entry (`seen_url`), do not create a
  duplicate key. If the original market is Europe or Finland and this run
  selected the *other* of those markets, register that exact URL with
  `python3 tools/rank_state.py register-market --market "<selected-market>" --url "<URL>"`.
  The command requires exactly one existing record with a known market and
  preserves its old ranking. If it refuses, report the conflict for manual
  review; never retag the row by hand. Continue the search and allow the
  second market's `/rank` to evaluate it under its own gates. For a duplicate
  within the same market, skip as usual. China JDs require their saved local
  input and must not be cross-registered this way.
- For a matching company+title in existing state, skip only when the source
  URLs are the same or the new result has no URL and cannot be disambiguated.
  Different known URLs are distinct postings; verify a shared requisition ID or
  canonical employer URL before deciding that two URLs represent one job.
- For a matching company+role in the application tracker, skip only when its
  `source` URL matches (ignoring a trailing slash), or when a missing URL makes
  the posting ambiguous. Different known URLs must not be dropped. Report
  ambiguous no-URL results for manual review rather than overwriting either.

### Step 2.5: Mass-Posting Detection (within this run)

A distribution pattern worth flagging to the user as a caution signal, not as an accusation against the employer - it describes how a listing is being distributed, not a verdict on whether the company is legitimate. It alone proves nothing is wrong (companies do legitimately hire the same role across several cities); flag it so the user can factor it in when deciding whether to invest time, don't downgrade fit or silently exclude the result because of it.

If two or more results in this run's pool (from the same company, or sharing the same req/job ID visible in the URL or title) have substantially the same description and differ only in city/location/title, don't present them as separate rows. Consolidate into a single row and note the spread, e.g. "posted identically across 6 cities (BR, MX, GT)".

### Step 3: Quick Fit Assessment

For each new job, do a rapid fit check (NOT the full evaluation from `04-job-evaluation.md` - just a quick signal):

- **High match**: Role directly involves your core skills
- **Medium match**: Role is adjacent to your experience
- **Low match**: Role requires significant skills you lack

**Language override:** before assigning a match level, check the posting against
the tracked `04-job-evaluation.md`'s Language Gate (a required language you
haven't declared at all in `documents/profile/CLAUDE.md`'s Languages table). A
required language that's entirely undeclared overrides skill fit: mark it **Low**
regardless of how well the skills align, and name it in the highlight bullets so it
isn't buried under an otherwise-good-looking match. A **declared** language at a
requirement that reads higher than your declared level is *not* an override — score
fit normally, but add a red-flag bullet under that job's highlights (Step 5)
quoting the posting's requirement next to your declared level, so the gap is
visible without being auto-downgraded.

### Step 4: Deduplicate & Store

1. Use the `key` returned by `tools/scrape_state.py lookup` for each `new`
   result. It uses the same canonical helper:

```bash
python3 tools/job_key.py --company "<company>" --title "<title>" --url "<url>"
```

It prints one line: the canonical key for that posting. The key must be a pure function of the posting, because two runs that slugify differently store the same job twice and defeat the dedup this step exists to provide. The helper also length-caps long titles and disambiguates the cap with a hash of the full slug, so a truncated title is stable across runs and two different long titles never collide. `python3 tools/job_key.py --audit` reports entries in an existing state file that predate this rule; it only reports, and never rewrites keys, since a rewritten key breaks the tracker's own company+role matching.

If the ordinary key already belongs to a distinct known URL, lookup selects
the helper's stable `--collision` key. A missing URL or conflicting identity is
`ambiguous`; resolve it manually before any write.

2. Add new jobs and same-market skipped jobs to `seen_jobs.json` with the
   following schema. Build a temporary JSON **array of new entries only** outside the repository,
   each with `key` from lookup and the fields below. Add them in one call:

```bash
python3 tools/scrape_state.py add --input "<new-entries.json>"
```

The helper checks URLs, pair ambiguity, tracker exclusions and key collisions
again before writing atomically, and prints only the keys added. If any entry
conflicts, the entire batch is rejected; rerun `lookup` and reconcile, never
overwrite existing rankings. For `seen_url` from the other Europe/Finland
market, only register that market using Step 2's helper. Do not recreate the
existing row or alter its primary ranking.
```json
{
  "seen": {
    "<key from tools/job_key.py>": {
      "title": "...",
      "company": "...",
      "url": "...",
      "first_seen": "YYYY-MM-DD",
      "posted_date": "YYYY-MM-DD" | null,
      "deadline": "YYYY-MM-DD" | null,
      "fit": "high/medium/low",
      "status": "new/skipped/ranked/expired",
      "portal": "<source portal skill, e.g. jobindex-search>",
      "source": "cli/websearch",
      "market": "china/europe/finland"
    }
  }
}
```

The `portal` field records the producing CLI skill (preserve Step 1b's tag), or the explicitly selected source tag in Step 1d. Entries written before this field existed lack it; the health check (Step 4.75) attributes those by matching the URL's domain against each portal's base URL, so do not backfill.

The `source` field records the existing storage category: `cli` for Step 1b portal-CLI output, `websearch` for the Step 1c fallback. Step 1d now also uses `cli` through the reusable explicit source branch and reports `mechanism=company_pages_cli_source`. Do not retag historical fallback records. This is what keeps a ghost-job report diagnosable after the run's summary is gone: a stored entry whose URL later resolves to nothing (or to a different job) reads very differently depending on whether it came from live CLI output or from a search index that can be weeks stale - and a presented job with no entry here at all points at fabrication, which Rule 1 forbids. Entries written before this field existed lack it; never backfill it - the mechanism was not recorded.

The `market` field is the **original** explicit market for this posting. When the
same URL appears in Europe and Finland, the registration helper adds `markets`
with both markets. Do not change the original `market`, `status`, or ranking on
rediscovery; `market_rankings.<second market>` is written by `/rank`. Entries
predating `market` remain untagged and are reported by the rank state tool as
`unknown_market`; never infer or bulk-backfill their market from a portal,
language, or location.

`/rank` extends this schema additively: ranked entries also carry `rank_score` (0–100 overall score), `rank_verdict` (fit band, e.g. "strong fit"), `rank_date` (ISO date of ranking), the veto fields `location_verdict` and `language_gate` (both PASS/FAIL/FLAG) with `language_note` (the quoted requirement explaining a non-PASS), and `strengths`/`gaps` (1-3 verbatim bullets each, copied from the scoring agent's findings). The `status` field is set to `"ranked"`. Do not drop any of these fields when re-writing entries. Entries ranked before `strengths`/`gaps` existed simply lack them; readers tolerate their absence and never backfill by guessing. Entries ranked before the verdict rename may carry a legacy PASS/FAIL/FLAG string in `location` - read that as the verdict when `location_verdict` is absent; in fresh entries `location` is always a place, never a verdict.

`deadline` is a base field rather than a `/rank` extension: Step 2's detail fetch already extracts the application deadline, so it is written when the job is first seen and refreshed by `/rank` Step 4 when a scoring agent returns a different value. `null` means the posting states no deadline; a missing key means the entry predates this field - **never infer a deadline** from either, and never backfill by guessing.

`posted_date` is the posting's own publication date, taken from the `date` field Step 2's contract already guarantees on every portal CLI's search output. Step 1b uses that date to scope the run to the last 14 days and then drops it, so nothing downstream can distinguish a posting published yesterday from one published two years ago - `first_seen` is when this scraper first saw the entry, not when the employer posted it. Persisting it makes Step 1b's window auditable after the run and gives `/rank` a freshness signal to weigh, instead of rediscovering the date and recording it in prose that nothing reads. That gap landed for real: a freehire-search posting dated 2024-05-13 was scraped and ranked Strong Fit at position 1 of 133, its own scoring note observing the listing "may be long stale" with nothing able to act on it. `null` means the portal returned no date for that result (the CLIs emit `date: null` when a listing omits it); a missing key means the entry predates this field - **never infer a posting date** from either, and never backfill by guessing.

3. Present only `added` postings and newly registered cross-market hits,
   not already in the seen list or tracker by exact URL;
   for URL-less ambiguous postings ask before presenting them as new.

### Step 4.5: Generate Referral Contact Links (High & Medium Fit Only)

For every job from this run with `fit` of **high** or **medium** (skip low-fit jobs),
build two LinkedIn people-search URLs so the user can find a recruiter or team member to
reach out to for a referral or a warm intro. This is deliberately a link-generation step,
not an automated lookup: no scraping, no third-party API, zero runtime dependencies or
credentials required.

**A. Recruiters / Talent Acquisition (the referral path)**
```
https://www.linkedin.com/search/results/people/?keywords=<url-encoded "<Company Name> recruiter">&origin=GLOBAL_SEARCH_HEADER
```

**B. Role/team peers (informational-outreach / warm-intro path)**
```
https://www.linkedin.com/search/results/people/?keywords=<url-encoded "<Company Name> <role keyword>">&origin=GLOBAL_SEARCH_HEADER
```
Use a short keyword drawn from the posting's title for `<role keyword>` - e.g. a posting
titled "AI Program Manager" becomes `"<Company Name> AI Program Manager"`.

Both links are for the user to open and browse themselves - never fetch or scrape the
LinkedIn people-search result pages programmatically. Never fabricate contacts or claim a
specific person was found; these are search links, not results.

### Step 4.75: Portal Health Check

Scraper-based portal CLIs rot silently: when a portal changes its markup, the parser usually exits 0 with zero results or with null/garbled fields, and the Step 1c fallback never fires because it only triggers on hard failure. This step catches that from evidence the run already holds.

Apply the source-access gate in ordinary and probe-only health modes, including
explicitly named disabled portals. Denied/unconfirmed sources get no sentinel,
retry or detail requests; report inconclusive with the access reason. An explicit
health request is not an override. Zero results or missing coverage alone cannot
establish healthy, valid-empty, or full coverage.

**Free pass (no extra requests).** First retain the per-employer coverage/errors
from Step 1b; explicit non-success coverage must not be replaced by a zero-yield
verdict. The generic sentinel escalation below is not permission to override a
company adapter's own request budget, stop condition or strict checker.
For each enabled portal that ran in Step 1b:

- **Degraded scan:** inspect the results it returned this run. Flags: `company` null or empty on every result, empty titles, undecoded entities (`&amp;`) or HTML fragments in titles, URLs that do not point at the portal. Any of these means the parser is half-working and `/scrape` is silently collecting junk.
- **Yield history:** if a portal returned zero results, run
  `python3 tools/scrape_state.py history --portal "<portal-name>" --domain "<portal-hostname>"`.
  `previous_results` checks the saved portal field or, for older rows without
  it, the URL hostname. A portal with prior results and none now is suspect.

**Escalation (bounded, on suspicion only).** A suspect portal gets **one** sentinel probe: run its documented `search` with the example query from its own SKILL.md (that query provably worked when the skill was registered), the portal's limit flag capped at 3, `--format json`. If that returns nothing, retry **once** with a single common word. Only then is the verdict **broken**. A 429 or block page is **never** evidence of breakage - record the portal as **inconclusive (rate-limited)**, back off, and do not retry.

**Verdicts.** Healthy portals get silence - no table, no line. Anything else surfaces in the Step 5 summary as a health line.

**Probe-only mode (`/scrape health`).** Skip Steps 1-4 and this step's free pass (there is no fresh run to scan); instead probe every installed portal directly - enabled ones by default, a disabled one only when named explicitly (e.g. `/scrape health jobnet`). Each portal gets the sentinel probe above, the degraded criteria applied to whatever it returns, and - since the user explicitly asked for diagnosis - one `detail` fetch on the first result of each healthy portal (description must be readable decoded text; a failure downgrades to degraded). Report all statuses in this mode, including healthy. Volume stays bounded: one search, at most one retry, at most one detail per portal.

### Step 5: Present Results

For a normal Europe or Finland scrape, run Step 1e's closeout ledger check before
presenting results. Include its uncovered sources and countries. If the check
could not finish, report LinkedIn/Indeed coverage as incomplete and explain why.

For Europe/Finland, name the resolved market, local strategy path and source-guide
path from Step 0, plus selected/attempted/skipped sources and selection reasons.
Keep these separate per market. Historical evidence is not this run's acceptance;
not-attempted sources remain unverified even if they previously worked.

Include every selected source's access decision/reason from the source-access
gate, even if it never ran, failed, or produced no surviving jobs. Print
`skipped (access): <portal> - denied|unconfirmed; <reason>` for skipped sources;
keep it separate from `skipped (disabled)` and retain runtime errors. Missing
coverage is unverified, never healthy/no jobs. Do not count an access skip or
failed request as an empty scan, and do not create a job/state row for it.

Include an employer-level `coverage:` line for each response carrying coverage or
errors: employer, status, scope/reason and any error (including partial and zero
output). Missing coverage is unverified. Preserve these lines even if deduplication
leaves no new jobs; never summarize such a run as a complete market scan or no jobs.
Label null publication dates unknown, and distinguish unseen from newly published.

Present new jobs in a table sorted by fit (high first). When Step 1b skipped
portals (`enabled: false`), report them with the `skipped (disabled):` line below
so opting one out stays visible rather than silent; omit the line when nothing
was skipped. When any portal's results came from the Step 1c fallback this run
(bun unavailable, or its CLI failed at runtime), report it with the
`fallback (websearch):` line - fallback results come from a search index that
can be stale, so the reader should know which rows carry that caveat; omit the
line when every portal ran its CLI. When Step 4.75 found a portal degraded, broken, or inconclusive,
add one `health:` line per suspect portal (healthy portals get no line); after
the report, offer to set that portal's `enabled: false` so `/scrape` stops
running it until it is fixed; disabling it does not authorize a Step 1c fallback - only
edit the toggle with the user's confirmation, and never edit anything else in
the skill.

```
## New Job Matches - YYYY-MM-DD

Found X new positions (Y high, Z medium, W low match).

skipped (disabled): <portal-name>, <portal-name>

fallback (websearch): <portal-name>, <portal-name>

health: <portal-name> - degraded (company null on all 12 results); parsing anchors in .agents/skills/<portal-name>/url-reference.md
health: <portal-name> - broken (0 results for the SKILL.md test query and a broader retry); parsing anchors in .agents/skills/<portal-name>/url-reference.md

| # | Fit | Title | Company | Location | Deadline | URL |
|---|-----|-------|---------|----------|----------|-----|
| 1 | High | ... | ... | ... | ... | [Link](...) |

If Step 2.5 flagged a mass-posting pattern, note it in the Title cell (e.g. "Frontend Developer (posted in 6 cities)") rather than burying it. Do the same for a declared-language-insufficient-level flag from the Language Gate (e.g. "Backend Engineer ⚠ fluent English required") - both are signals the user should see at a glance, not just in the detail highlights below.

### High-Match Highlights
For each high-match job, add 2-3 bullet points:
- Why it matches your profile
- Key requirements to check
- Any red flags (including mass-posting signals from Step 2.5)

### Contacts
For each high/medium-fit job from Step 4.5, add a short contacts block with the two
LinkedIn search links:
- Recruiters/TA search link, for the referral path
- Role/team-peer search link, for the warm-intro / informational-outreach path
```

After presenting, ask:
> "Want me to evaluate any of these in detail? Just give me the number(s)."

If the user picks a number, invoke the **job-application-assistant** skill workflow (fit evaluation first, then CV + cover letter if approved).

If the run found many new jobs (roughly 8+), also suggest `/rank` - it batch-scores all new postings against the full fit framework and returns a ranked shortlist, which beats eyeballing a long table. (`/rank` sets the `ranked` and `expired` status values in `seen_jobs.json`; treat both as already-seen for dedup purposes.)

### Step 6: Update Tracker (Optional)

If the user decides to apply to any job, the tracker row is written by **job-application-assistant Step 3b**, which Step 5 already routes into - do not add a second row here. Only when the user says they applied to something outside that path, add a row using the header and the match-then-update rule in `/outcome` Step 1.

---

## Important Rules

1. **Never fabricate job postings.** Only present jobs from actual CLI search/detail output or WebSearch/WebFetch results.
2. **Respect deduplication.** Always check seen_jobs.json AND job_search_tracker.csv before presenting.
3. **Focus on configured geographic area.** Skip jobs that require relocation or are clearly outside commute range.
4. **Only open positions.** Skip postings with expired deadlines or those marked as closed.
5. **Be efficient with detail fetches.** Don't run `detail` or WebFetch on every search hit — pre-filter by title/snippet, then fetch only promising matches.
6. **Parallel searches.** Run portal CLI searches in parallel; use WebSearch only for gaps the CLIs don't cover.
7. **No automated people lookups.** Referral contacts (Step 4.5) are LinkedIn search links only - never fetch or scrape LinkedIn people-search result pages programmatically.
8. **Health checks are bounded and honest.** Step 4.75 spends at most one probe, one retry, and (in `health` mode) one detail fetch per portal - a diagnosis, not a crawl. A rate-limit is never evidence of breakage. Health verdicts come only from observed CLI output; a portal that could not be tested is reported as inconclusive, never guessed. The `enabled` toggle is the only thing the health check may edit, and only with confirmation.
9. **Flag distribution patterns, never accuse.** The mass-posting signal (Step 2.5) describes how a listing is being distributed, not a claim that the employer is a scam. Never name a company as fraudulent or untrustworthy - present the observation and let the user decide.
