---
name: company-pages-search
version: 1.2.0
description: >
  Registry-driven lookups of specific employers' own career pages when they
  do not syndicate every position to job boards.
  Trigger phrases: check company career pages, openings at <company>, watch
  these companies, any new roles at <company>, monitor <company>'s careers page.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
metadata: {"openclaw":{"requires":{"bins":["bun"]}}}
allowed-tools: Bash(bun run .agents/skills/company-pages-search/cli/src/cli.ts *)
---

# Company Pages Search Skill

Looks up job openings directly on a **registry of specific employers you care about**,
rather than a generic job board. Many employers post only a subset of their open roles
to aggregators and keep the full list on their own `careers`/`jobs` page. This
skill uses the public JSON APIs behind the four most common applicant-tracking systems
(Greenhouse, Lever, SmartRecruiters, Oracle Cloud HCM), plus the verified IFF and
Novonesis Workday boards, the VTT official list/TalentAdore detail branch, and
the scoped Ashby branch described below. It
falls back to a best-effort HTML scrape (or a WebFetch by the agent) otherwise.

The registry and named acceptance employers are priority inputs and technical
reader contracts, not an employer allowlist for the overall job search. Relevant
employers discovered outside them remain candidates. For Europe/Finland, failed or
unsupported detail paths retain their list leads and provisional evaluation per
canonical job-scraper Step 0b; parser rejection alone is not confirmed mismatch. Unsupported detail methods
must be reported separately from source access denial; use only a documented
permitted reading route, with the real checker where required. This instruction
does not make the current VTT-only Jobly parser support other employers. Canonical
market/query selection and budget rules live in job-scraper Step 0a/1b.

No package installation is needed; the CLI requires `bun`.
The same CLI also supports the explicitly selected Work in Finland source mode
below; it is separate from registry-driven employer searches.

## ⚠️ Personal use only

This reads companies' own public career APIs and pages. Keep volume low, don't use it
commercially or for bulk data collection, and respect each site's terms of use. Run it
on your own responsibility.

## The registry

The company list lives in **`company_pages.json` at the repo root** — personal, and
gitignored (see `.gitignore`). A committed example lives at
`.agents/skills/company-pages-search/company_pages.example.json`. The example is
documentation only and is never queried automatically. If the personal file is missing,
the CLI exits with `NO_REGISTRY` before making a network request.
This applies to registry-backed commands; explicit Work in Finland source mode
does not load the registry and does not require it.
The default is resolved from the physical skill location, not the current directory.
Workspace + subproject installs retain their existing registry compatibility link.
`COMPANY_PAGES_REGISTRY` may select an isolated data registry; it does not authorize
an external checker or change the installed project layout.

**To start using this skill:** copy the example to the repo root and edit it.

```bash
cp .agents/skills/company-pages-search/company_pages.example.json company_pages.json
```

Delete every example employer you did not intentionally select before running `search`.

Each entry:

```json
{
  "name": "Example Employer",
  "careers_url": "https://example.com/careers",
  "ats": "greenhouse",
  "ats_id": "replace-with-greenhouse-board-token",
  "locations_filter": ["Your city", "Remote"],
  "notes": "free text"
}
```

- `name` — display name; also the `--company` key used by `search`/`detail`.
- `careers_url` — the company's own careers/jobs page (used for `generic` scraping and
  as a human-readable link).
- `ats` — one of `greenhouse` | `lever` | `smartrecruiters` | `oracle` | `workday` | `ashby` | `generic`.
- `ats_id` — the ATS's board/company token. Required for the four named ATS types;
  for `ashby`, use exactly the mapped board token below; leave empty (`""`) for `generic` and `workday` (Workday uses the verified `careers_url`). **Oracle is the exception to the single-token rule:**
  its API host is tenant-specific and cannot be derived from the company name, so
  `ats_id` carries both halves as `"<host>|<siteNumber>"`, e.g.
  `"iaadtu.fa.ocs.oraclecloud.eu|CX_1"`.
- `locations_filter` — optional. If non-empty, results are kept only when their
  location string contains one of these substrings (case-insensitive). Jobs with no
  parsed location are always kept (rather than silently dropped).
- `notes` — free text, e.g. how you found the ATS token, or quirks of that page.

### How to find a company's ATS

Open the company's careers page and either:
1. **Look at the URL** — many career pages are just an iframe/redirect to
   `boards.greenhouse.io/<token>`, `jobs.lever.co/<company>`, or
   `jobs.smartrecruiters.com/<Company>`. The token/company slug in that URL is your
   `ats_id`.
2. **Open browser devtools → Network tab**, click into a job listing, and look for an
   XHR request to `boards-api.greenhouse.io`, `api.lever.co`, or
   `api.smartrecruiters.com`. The path segment right after `/boards/` or `/companies/`
   or `/postings/` is the `ats_id`. For **Oracle Cloud HCM** the XHR goes to
   `<tenant>.fa.<region>.oraclecloud.com/hcmRestApi/...` and carries
   `finder=findReqs;siteNumber=CX_1` — take the host and that `siteNumber` and join them
   with a pipe. Oracle career sites render listings client-side, so without this adapter they fall to
   `generic` and return nothing.
3. Workday support is limited to `https://iff.wd5.myworkdayjobs.com/en-US/IFF_Careers`
   and `https://novonesis.wd103.myworkdayjobs.com/en-US/Novonesis_Careers`
   (the same paths without `en-US/` also work). Set `ats: "workday"`, `ats_id: ""`.
   Do not derive another employer's tenant/site from its name.
4. VTT uses `ats: "generic"`, `ats_id: ""`, and exactly
   `https://www.vttresearch.com/en/careers/come-and-build-future-vtt`.
   This special branch reads its table and TalentAdore links, not every generic site.
5. The Ashby candidate uses `ats: "ashby"` and `ats_id` exactly `cradlebio`,
   `adaptyv` or `basecamp-research`. These tokens are from the historical official
   mapping, not new live verification. Never derive a board from a company name.
   The personal registry is not updated automatically.
6. Other unimplemented systems, including SAP SuccessFactors, remain `generic`;
   this does not assert reliable list or detail support.

## Commands

Query syntax: registry-backed `search --company` and `--source euraxess` use a case-insensitive literal title substring, not a search-engine query; multi-word text stays in order and literal quote characters, `site:` and `OR` have no operator meaning. Group words as one shell argument (`--query "protein engineer"`), without embedded quote characters. Explicit `--source work-in-finland` sends the bare term to the server (trimmed/lowercased); server phrase quoting and boolean operators are unverified. Use one plain term per call under canonical scrape Step 1b and its shared request budget. EURES `--query` sends a trimmed plain keyword with the evidenced `specificSearchCode=EVERYWHERE`; do not apply an additional title-only filter, because it may match the source description. Only the plain term `protein` has bounded live evidence; phrase/boolean syntax is unverified. These are distinct branches, not a promise of common search semantics across sites.

### Work in Finland source (no registry)

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts search --source work-in-finland --query "protein" --limit 6 --format json
```

This explicit mode never reads the personal registry. It cannot combine with
`--company`, and is not supported by `list`. It reads one six-card
page from the verified same-origin `/api/jobs/` route; `--query` is a server query,
`--location` a client-side location filter, and `--limit` an emitted-result cap.
Each request requires the real strict checker; requests have a 15-second timeout,
128-KiB streamed body cap, and no redirects/retry/browser fallback. Failure remains
coverage/errors, not no jobs. Output retains the existing results/meta contract
and source coverage with received count, declared totals and Retry-After.
The default coverage is partial even when a page has fewer than six results.
Company/title/location/externalUrl are mapped; date stays null, no source ID is
invented, and expireDate is not used as publication date or verified deadline.
`portal=work-in-finland`; `source_ats=generic` does not identify an employer ATS.
The deployed VTT direct-link route reuses the official VTT board/detail reader.
A local-only extension adds `detail --source work-in-finland --id jobly:<ID>
--query <same list query>` for VTT cards pointing directly at the observed
`https://www.jobly.fi/en/job/<slug>-<ID>` shape. It is not deployed or sandbox/
online accepted yet. `jobly:<ID>` is a separate namespace, not a TalentAdore ID.
The list retains the supplied URL; detail preserves it as source_url and emits
the explicitly declared same-slug/same-ID `/tyopaikka/` canonical as url and
canonical_url. Only exact HTTPS www.jobly.fi paths without credentials/query/
fragment are supported. Require one canonical, one JobPosting, matching title
and VTT employer, and a nonempty description with observed duties/requirements
markers. Missing structured identifier/url may be bound by the declared
canonical; if supplied, those fields must not conflict. No link following,
redirects, retry or fallback; each exact URL requires the real strict checker.
Jobly detail uses 15 seconds/2MiB and keeps per-stage partial/errors/Retry-After.
It re-reads one WIF page then one selected Jobly page (two GETs plus checker
calls); an extra search consumes an additional page request. Publication stays
null; description-field extraction is not independent full-visible-JD proof.
Other employers, Academic Positions and other external links remain leads.
Canonical Step0a/1d controls eligibility and requires deployment/acceptance of
the Jobly extension before its use. Existing direct-link behavior is unchanged.
Canonical selection/downstream rules remain job-scraper Step 1d. This mode neither
enables a source nor verifies upstream provider, external JD or full board coverage.

### EURAXESS source (no registry)

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts search --source euraxess --query "protein" --limit 1 --format json
bun run .agents/skills/company-pages-search/cli/src/cli.ts detail --source euraxess --id <numeric-ID-from-first-page> --format json
```

Reads only `https://euraxess.ec.europa.eu/jobs/search`, not the `/jobs` introduction.
Query/location/limit filter this one page client-side; they are not verified
server filters and do not imply a complete Europe/Finland scan. List IDs come
from same-origin numeric posting URLs; original URLs/IDs survive deduplication.
The list employer field is deliberately empty with `needs_detail=true` and a
source warning: do not invent an employer from metadata position or save a lead
before detail confirms it. Unknown publication dates remain null; a deadline
is not publication. A missing list or malformed identities fail explicitly;
only an explicit zero Search results count with no cards is valid_empty for
this page. All nonempty scans remain partial.

Detail scans the first page again to bind the selected ID/title, then at most one
same-origin posting GET. An ID absent from that page stays unconfirmed, never
closed. The explicit canonical ID/URL must match the listed URL and title; it
also requires Organisation/Company, Offer Description and Requirements from
that same response. Additional Information is retained if present. It does not
claim an extra Drupal ID field or independently verified full-JD completeness.
The header date without a publication label stays unknown; only a labelled
Application Deadline is parsed as deadline.

Each URL uses the real strict checker, GET only, 15 seconds/2MiB maximum,
credentials omitted, no redirects/retry/browser fallback. Denied/unknown, 403,
429/Retry-After, parse failure and partial stay visible. One search makes at most
one checker+GET; detail at most two checker+GET pairs. Do not run search and then
detail if a one-list budget would be exceeded. Existing list/detail code is
deployed with bounded historical sample evidence; this metadata/downstream
extension is local-only until separately deployed and sandbox accepted.
JSON detail adds canonical_url and per-stage meta.coverage/errors; plain output
keeps those on stderr, including failures and Retry-After when supplied.
The list-employer warning is retained as list provenance after detail resolves
that selected employer. Redacted structure replay is not complete live JD proof;
canonical Step0a/1f owns eligibility, budgets and downstream handling.

### EURES list source (bounded server keyword; no registry)

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts search --source eures --query "protein" --limit 1 --format json
```

Uses the observed official POST at
`https://europa.eu/eures/api/jv-searchengine/public/jv-search/search` with the
accepted minimal body: page 1, resultsPerPage 10, BEST_MATCH, optional keywords,
minNumberPost null, requestLanguage en and a fresh anonymous client grouping ID.
It never reads the personal registry and cannot combine with `--company`.
`--query` is now a server EVERYWHERE keyword (trimmed, nonempty, at most 200
characters; this is a local input budget). Omission preserves keywords=[].
`--location`/`--limit` remain client output filters only. There is no country
selector: the response location facets contained codes without country labels,
so Finland mapping and server country semantics remain unverified. Do not use
`--location Finland` as a server country filter. Pagination and `list` remain unsupported. Keep query_scope/country_scope in
meta.coverage. The deployed bounded detail branch is described below; rollout scope is canonical Step 0a.

Original opaque IDs, including suffixes, survive deduplication; conflicting
titles for the same ID are rejected. Only observed ID/title types are mapped.
Employer, location, publication date and canonical page stay unknown; source
creation/modification times are not treated as publication. Output is a
provisional lead with `needs_detail=true` and `canonical_url=null`. Its `url`
is a safely encoded reference to the source's declared English detail API,
`url_kind=unverified_api_detail_reference`; it has not been fetched and is not a
verified posting webpage. List descriptions are not emitted as full JDs.

Every invocation requires the real strict checker, then at most one POST;
15-second timeout, 2MiB streamed body cap, credentials omitted, no redirects,
retry, alternative client or fallback. Requests remain bounded even if output
limit is larger than ten. Preserve meta.coverage/errors and Retry-After. Only
an explicit jvs=[]/numberRecords=0 is valid_empty for this query page; nonempty
results always remain partial, even with a zero declared total or zero output
matches. Unknown/checker/transport/schema failures are never an empty market or
confirmed closure. Canonical orchestration is job-scraper Step 1g.

The list/keyword and bounded original-detail branches are deployed. Recorded
acceptance includes actual sandbox keyword search, one original posting read,
and a same-description-hash entity-decoding diagnosis plus isolated rule
consumption. This is bounded historical evidence, not a new run, all-original
source support or full coverage. Eligibility/budget and leads-versus-details
handling are owned only by canonical job-scraper Step 0a/Step 1g.

### EURES bounded detail/original reader

`detail --source eures --id <exact raw ID from search>` reads the observed
API detail endpoint, without an implicit list. Preserve the raw ID and suffixes.
An exact response ID and an unambiguous language profile with nonempty
title/employer/description are mandatory. The standalone CLI reports
`title_crosscheck=not_performed`; it has not compared a previous list title.

If the selected profile's applicationInstructions explicitly supplies an HTTPS
www.arbeitsagentur.de/jobsuche/jobdetail/ URL matching the exact source reference,
the reader reads that page too. Maximum: two GETs, each separately permitted
by the real strict checker, no retries/redirects or guessed URLs. No other
application/employer links are fetched. Missing permission, errors or invalid
original-page identity fail explicitly, without falling back to the API body.

Require one matching canonical, one JobPosting, exact identifier/reference and
JobPosting URL, matching employer and a compatible title. The evidenced title
relation allows only equality or the original title followed by one parenthesized
feed classification; preserve both titles and record the relation. It never
normalizes IDs or deletes ordinary hyphens to force body equality. The original
JobPosting.description is the sole returned JD, verbatim, with duties/requirements
markers required; no API text or page navigation is appended. Preserve API
source_id/source_title/source_description/source_api_url and source_reference.
`needs_detail=false`, `canonical_url` and the read-description coverage describe
this one identity-verified field, not proof of whole-market or page completeness.

Without an explicitly supported original link, preserve the API-only result:
`needs_detail=true`, `JD_completeness=unverified`, `canonical_url=null` and an
explicit warning. An API URL/employer homepage is not a canonical posting.
Both branches keep partial meta.coverage/errors; failure never means closure.
Dates remain unknown; capture/source timestamps are not publication dates.
No contact records are copied. Plain output keeps metadata/warnings on stderr.

The recorded one-ID source-body acceptance joins actual CLI output and an
independent same-hash BA diagnosis; the old entity-encoding false-negative stays
in its historical record. Acceptance text decoding is test-only, not a production
body rewrite. Other original sources and full page/market coverage remain
unverified. Canonical Step 0a/Step 1g controls limited use; this skill does not
activate normal/weekly tasks or expand a run's network budget.

### List the registry

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts list [--format json|table|plain]
```

### Search

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts search [flags]
```

Flags:
- `--company <name>` / `-c <name>` — restrict to one registry entry (exact name match,
  case-insensitive). Omit to query every entry in the registry.
- `--query <text>` / `-q <text>` — keyword filter on job title (client-side substring).
- `--location <text>` — location filter (client-side substring, in addition to any
  registry-level `locations_filter`).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side), not requests or pages.
- `--format json|table|plain` — default `json`.

Per-`ats` behavior:
- `greenhouse` → `GET https://boards-api.greenhouse.io/v1/boards/<ats_id>/jobs`
- `lever` → `GET https://api.lever.co/v0/postings/<ats_id>?mode=json`
- `smartrecruiters` → `GET https://api.smartrecruiters.com/v1/companies/<ats_id>/postings`
- `oracle` → `GET https://<host>/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=<siteNumber>,...`
- `workday` → verified boards only; POST list pages, at most 5 pages of 20.
  Later `total=0` does not terminate a nonempty page; repeats/budget exhaustion
  remain partial. There is no CLI page-budget flag.
- `ashby` → one GET to `https://api.ashbyhq.com/posting-api/job-board/<ats_id>`
  after the real strict checker permits that exact path. The response can contain
  the whole board; `--limit` only truncates emitted results, not downloaded bytes.
  Only `isListed: true` records with a matching `jobs.ashbyhq.com/<board>/<UUID>`
  URL are accepted; unlisted records are excluded, missing identity/listing flags
  remain parse failures or partial coverage. IDs are derived from that URL and
  cross-checked against an explicit response ID if present.
  This is a candidate response contract tested with synthetic fixtures only:
  current public schema, listing-flag semantics and board completeness remain
  unverified until separately permitted evidence is obtained. Valid records stay
  `partial`; `valid_empty` means only an empty validated response, not all sources
  checked. Unexpected continuation is reported partial without inventing pages.
- VTT's exact `generic` URL → one official table, stable TalentAdore IDs/URLs;
  always partial, including when `--limit` truncates output.
- Other `generic` → fetches `careers_url`, strips tags, and extracts links whose href/text
  look job-related (contains "job", "career", "vacan", "position", "opening",
  "opportunit", or "role"), emitting a best-effort "manual review" record per link with
  no parsed location/date. **This is intentionally shallow.**

### Detail

```bash
bun run .agents/skills/company-pages-search/cli/src/cli.ts detail --company <name> --id <job id> [--format json|plain]
```

`<job id>` is the ATS's own id from a `search` result's `id` field. Only works for
`greenhouse`/`lever`/`smartrecruiters`/`oracle`, the two supported `workday`
boards, `ashby`, and VTT's exact `generic` URL. Other generic entries have no CLI detail.
Workday detail searches the bounded list again (up to 5 pages) before requesting
one detail; it verifies the raw ID including suffix, requisition and URL path.
VTT detail reads one list before one detail, requiring independent JSON-LD ID,
URL, title and nonempty description agreement. Never strip suffixes or substitute
another listing. `jobDescription_present`/`structured_description_present` means
that field exists, not that every page section or every job has been verified.
Unknown dates remain null; `observed_at`/`posted_raw` are not publication dates.
Ashby detail decodes one board response and selects exactly the requested board/ID;
there is no guessed single-job endpoint or cross-invocation persistent cache. It
requires descriptionHtml or descriptionPlain with text; missing body or conflicting
identity fails. `response_description_present` is not a verified-full-JD claim.
Search does not emit all JD bodies. `publishedAt` is retained as `published_raw`;
only a valid ISO timestamp supplies `date` and `date_source=publishedAt`; missing or
invalid dates remain null. Capture time is separate, never a publication date.

## ⚠️ `generic` entries: WebFetch is the primary path, not the CLI scrape

Many employer career pages are JS-rendered (React/Angular SPA) or sit behind
Cloudflare, and won't yield anything useful to a plain HTML fetch + regex link scrape.
For generic entries **other than the exact VTT branch above**:

1. Try `search`/`list` first — it's free and sometimes works for simple static pages.
2. If it returns nothing (or junk links), **the agent should `WebFetch` the
   `careers_url` directly** and read the rendered listings itself, or fall back to
   `WebSearch site:<company domain> careers <role>` for a JS-heavy or protected page.
   This mirrors the `job-scraper` skill's own WebSearch fallback pattern (Step 1c in
   `.claude/skills/job-scraper/SKILL.md`) — do not force the mechanical CLI scrape when
   it can't see the real content.
3. These other generic entries have no CLI detail; use the specific job URL only
   through an independently permitted access path. A denial is not fallback permission.

## Orchestrator discovery (`/scrape`)

This skill follows the same portal-skill convention as `linkedin-search`, so
`.claude/skills/job-scraper/SKILL.md`'s Step 1b auto-discovers it: any orchestrator run
uses `tools/portal_catalog.py` to inspect frontmatter, checks the `enabled` key
(default enabled), then reads selected skills and calls this CLI with flags translated from
`search-queries.md`. No changes to `job-scraper` are needed to pick this skill up — set
`enabled: false` above to opt a fork out without deleting the directory.

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing `id` to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the
process exits with code `1`. Per-entry fetch failures during `search` are collected into
`meta.errors` in JSON output (or a stderr `warnings` line for `table`/`plain`) rather than
aborting the whole run — one bad registry entry never blocks the others.
Workday/VTT/Ashby can instead return a non-success state in per-employer
`meta.coverage` (`company`, `status`, `reason`, `requests`), even with exit 0 and
empty `meta.errors`. Both must be consumed; table/plain put coverage on stderr.
`requests` is the adapter counter (Workday counts a list attempt even when its
gate refuses it), not checker requests or an audited network total. Missing coverage
means unverified, not complete. See the canonical scrape rules for downstream
handling; never discard coverage when pooling results.

## How this skill identifies itself

Every request identifies honestly, as
`company-pages-search-skill/1.2 (+https://github.com/hongbozh1214/ai-job-searchHZ)`.
Browser-shaped headers are **not** the default and are never sent speculatively.

Outside the Workday/VTT/Ashby branches, a `401`/`403` may trigger a retry; the status
alone does not establish permission. The existing generic CLI
retries once through `curl` with a full browser header set — but only after
`tools/robots_check.py` confirms the site's published policy permits that path. That is
the boundary `.claude/skills/job-application-assistant/09-web-research.md` states: the
retry exists to get past bot-filtering firewalls on sites whose robots.txt permits
access, and it is never used to override a site that has said no.

Redirects are followed **one hop at a time, and every hop is gated.** Using `curl -L`
would have sent the browser header set to whatever host the chain ended on, whose
`robots.txt` was never consulted, so permission granted for one origin was silently
spent on another.

A `200` whose body is not a robots.txt (an HTML error page, a JSON blob) counts as
unreadable, not as permission. Such a body parses to zero rules and zero rules read as
"allowed", which is a fail-open. A genuinely empty file is still allow-all per RFC 9309.

The gate fails closed. If `robots.txt` cannot be read, if the checker is missing, or if
`python3` is unavailable, permission is unconfirmed and the retry does not run — the
entry remains unconfirmed, not evidence of no jobs. A fallback must not bypass denial. The CLI
does not carry its own robots parser: it shells out to `tools/robots_check.py` so the
repo has exactly one definition of what "the site permits this" means.

## Notes

- Workday/VTT/Ashby gate every actual list/detail/redirect path with the real checker in
  strict mode: one UA/request, no automatic robots redirects; refusal or unknown
  prevents the protected request. These branches have no browser fallback and no
  429/5xx retry. 429 stops and retains Retry-After. Other adapters retain their
  existing retry behavior; do not extend it to these branches.
- `locations_filter` on a registry entry and `--location` on the CLI both apply (AND);
  set `locations_filter: []` to disable the registry-level filter for that company.
- A 401/403 distinguishes **`robots_unconfirmed`** (we may not fetch it) from `bot_blocked`
  (we may, and the WAF beat the retry anyway) - different problems, different fixes.
- A list endpoint answering 404, an unknown `ats` value, or a Lever error object now
  **throw** instead of returning `[]`. A wrong `ats_id` used to read as "this employer
  has no openings" indefinitely.
- Fetch failures are classified (`bot_blocked`, `url_not_found`, `rate_limited`,
  `server_error`, `timeout`, `dns_failure`, `tls_error`) so a wrong URL is
  distinguishable from a block.
- See `url-reference.md` for the four ATS APIs' exact shapes and known quirks.
- The reviewed VTT offline entry is `bun run tools/company-cli-offline/run.ts`
  from the project directory; it first proves rejection, then runs scoped replay
  tests. The same entry with `ashby` selects only `tests/ashby.test.ts` after the
  same rejection checks. Ashby subprocess fixtures explicitly set the separate
  `COMPANY_OFFLINE_ASHBY_ROBOTS_FIXTURE` test flag (`1` allows, `deny` disallows);
  otherwise the existing curl stub rejects every Ashby robots request. Exact
  response fixture misses throw `OFFLINE_UNMOCKED_FETCH_DENIED`, never real fetch.
  Its protection covers only the reviewed chain, not arbitrary code or the
  full test suite. Workday fixture command tests use explicit injected transports;
  do not run a whole suite bare or treat fixture replay as live workflow execution.
