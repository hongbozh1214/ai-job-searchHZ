# China Job Scrape Workflow

You are searching for China-market job postings from public pages. This workflow
uses the low-volume LinkedIn public CLI plus WebSearch and WebFetch. Do not log
in, use cookies, bypass anti-bot systems, message recruiters, apply to jobs, or
operate any platform account.

## Step 0: Parse Input

`$ARGUMENTS` should contain:

```text
scrape [focus|broad]
```

- No focus: use the top target roles, cities, and industries from
  `documents/china/profile/preferences.md`.
- `focus`: prioritize that role, skill, industry, or city.
- `broad`: run more query categories, but keep volume low.

## Step 1: Read Inputs

Read:

- `documents/china/profile/preferences.md`
- `documents/china/profile/candidate.md`
- `markets/china/search-queries.md`
- `.agents/skills/linkedin-search/SKILL.md` when that skill is installed and enabled
- `job_search_tracker.csv` if it exists
- `job_scraper/seen_jobs.json` if it exists; create it if missing with
  `{"seen": {}}`

Use target roles, cities, industries, hard exclusions, salary minimums, and work
mode preferences to build search terms.

## Step 2: Build Search Queries

Default public sources:

- BOSS Zhipin (`site:zhipin.com`)
- Liepin (`site:liepin.com`)
- Zhaopin (`site:zhaopin.com`)
- 51job (`site:51job.com`)
- Maimai (`site:maimai.cn`)
- Guopin (`site:iguopin.com`)
- LinkedIn public jobs (`linkedin-search` CLI)
- Company career pages

LinkedIn is an enabled China source, including for mainland roles; it is not
limited to foreign-company or English-language searches. Translate each selected
city into a LinkedIn location string such as `"Shanghai, China"`, and preserve
the user's Chinese or English role keywords instead of silently broadening them.

Do not include discontinued or user-excluded job boards.

Generate a small set of targeted WebSearch queries:

- Default: up to 8 queries.
- Focus mode: up to 6 focused queries.
- Broad mode: up to 15 queries.

Prefer precise queries over broad scraping. Include city and role terms whenever
possible.

For LinkedIn, use the installed CLI rather than a `site:linkedin.com` WebSearch:

```bash
bun run .agents/skills/linkedin-search/cli/src/cli.ts search \
  --query "<role or skill>" --location "<city, China>" \
  --jobage 14 --limit 10 --format json
```

Default to at most 3 LinkedIn role/location searches, 2 in focus mode, or 5 in
broad mode. If Bun is unavailable, the skill is disabled, or LinkedIn rejects or
rate-limits the request, report LinkedIn as unavailable and continue with the
other China sources; do not replace it with logged-in browser automation.

## Step 3: Search Public Results

Run the LinkedIn CLI searches and WebSearch queries. For each promising result,
keep:

- Title.
- URL.
- Search snippet.
- Source site.
- Apparent company and role if visible.

Skip results that are clearly expired, unrelated, outside hard location
constraints, or duplicates.

## Step 4: Fetch Public Pages

For promising LinkedIn results, fetch detail through the CLI once per shortlisted
job ID:

```bash
bun run .agents/skills/linkedin-search/cli/src/cli.ts detail <id> --format json
```

For other promising results, use WebFetch once per URL. Do not fetch every
LinkedIn search hit before deduplication and basic relevance filtering.

Classify each result:

- `ready`: full JD is publicly readable and includes enough responsibilities and
  requirements for evaluation.
- `manual_required`: result is relevant, but WebFetch returns a login page,
  anti-bot page, partial snippet, empty body, or otherwise incomplete JD.
- `blocked`: page explicitly blocks automated/public access.
- `duplicate`: URL or company+role already appears in `seen_jobs.json`,
  `job_search_tracker.csv`, or `markets/china/jobs/inbox/`.
- `skip`: unrelated, expired, outside explicit constraints, or too weak to keep.
  Education or credential wording is an automatic exclusion only when the user
  explicitly recorded that exact boundary under `documents/china/profile/preferences.md`
  "学历与资质硬门槛" and the shared candidate evidence confirms the mismatch.
  Otherwise keep it as `manual_required` and name the unresolved requirement;
  never infer a candidate's degree, school tier, or certificate status. For an
  explicit mismatch, record `skip_reason` as
  `education_or_credential_mismatch:<quoted requirement>`.

Never infer missing responsibilities, requirements, salary, or benefits from the
title alone.

## Step 5: Save Job Files

For `ready` results, write:

```text
markets/china/jobs/inbox/<company>-<role>.md
```

Use this structure:

```markdown
# <Role> @ <Company>

**Source:** <site>
**Source URL:** <url>
**Fetch Status:** ready
**Saved Date:** YYYY-MM-DD

## Job Facts

- Company:
- Role:
- Location:
- Work Mode:
- Salary:
- Employment Type:

## Responsibilities

...

## Requirements

...

## Preferred Qualifications

...

## Benefits / Work Conditions

...

## Notes

- Search snippet:
- Missing info:
```

For `manual_required` or `blocked` results that look relevant, write:

```text
markets/china/jobs/inbox/<company>-<role>-manual-required.md
```

Use this structure:

```markdown
# <Role> @ <Company>

**Source:** <site>
**Source URL:** <url>
**Fetch Status:** manual_required
**Saved Date:** YYYY-MM-DD
**Manual Action Needed:** Open the source URL yourself and paste the full JD below.

## Search Snippet

...

## Paste Full JD Below

```

Derive the canonical key with `python3 tools/job_key.py`, then add every new or
skipped URL to `job_scraper/seen_jobs.json`. Do not create a second entry for a
duplicate. Use the shared state contract, adding `market` and `fetch_status`
without replacing canonical fields:

```json
{
  "title": "...",
  "company": "...",
  "url": "...",
  "first_seen": "YYYY-MM-DD",
  "posted_date": "YYYY-MM-DD or null",
  "deadline": "YYYY-MM-DD or null",
  "fit": "high/medium/low or null when the JD is incomplete",
  "status": "new/skipped",
  "portal": "linkedin-search",
  "source": "cli",
  "market": "china",
  "fetch_status": "ready/manual_required/blocked/skipped"
}
```

`status` is the lifecycle field consumed by the canonical rank workflow. Keep
fetch/access state only in `fetch_status`; never write `ready`, `blocked`, or
`manual_required` into `status`. Use `status: "new"` for relevant records kept
for evaluation and `status: "skipped"` for explicit exclusions. If fit cannot
be judged from an incomplete JD, use `null` rather than guessing.

The JSON block shows a LinkedIn result. For WebSearch results, set `source` to
`websearch` and set `portal` to the originating site (`zhipin`, `liepin`,
`zhaopin`, `51job`, `maimai`, `guopin`, or `company-careers`). Never store the
explanatory labels themselves as field values.

## Step 6: Present Results

Present a concise table:

```markdown
## China Job Search Results - YYYY-MM-DD

| # | Status | Company | Role | Source | Location | File |
|---:|---|---|---|---|---|---|
```

Then show:

- Ready to analyze: files that can be passed to `$job-search analyze --market china`.
- Manual required: files where the user must paste the full JD.
- Skipped/duplicates: count only, unless the user asks for details.

If no ready results are found, say whether the blocker was search quality,
platform blocking, sparse profile preferences, or too-strict filters. Suggest
either refining `documents/china/profile/preferences.md` or manually adding a JD.

## Important Rules

1. Do not log in, use cookies, bypass anti-bot systems, message recruiters, or
   apply to jobs.
2. Public search and single-page public fetch are allowed; platform operation is
   not.
3. Do not fabricate JD details. If content is incomplete, create a
   `manual_required` file.
4. Keep all China-market output under `markets/china/jobs/` unless the user
   explicitly asks to update `job_search_tracker.csv`.
5. Respect deduplication before presenting jobs.
