# Search Queries for Job Scraper

<!-- This tracked file contains query rules and examples. /setup writes the
candidate's actual terms to documents/profile/search-queries.md. -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers installed skills, then selects sources using the canonical
[job-scraper Step 0](SKILL.md#step-0-load-state). Its source-access gate applies to
CLI, fallback, detail and health requests; installation or `enabled` is not source
selection or permission. This file supplies query examples only, not a source
allowlist or a replacement for the selected market's personal strategy.

The `site:` templates below illustrate WebSearch fallback only within the
canonical workflow's permitted selection/method. CLI failure does not authorize
fallback past an access restriction; a site query does not prove a platform scan.

**Language scope:** write every query category in every language listed in
`documents/profile/CLAUDE.md`'s Languages table (typically 1-2, sometimes more).
A posting requiring a language you have *not* declared, as a job condition, is
excluded before scoring; a posting requiring a *higher level* than you declared in
a language you *do* work in is flagged for your own judgment, not excluded — see
the Language Gate in tracked `.claude/skills/job-application-assistant/04-job-evaluation.md`.
Translate each category's keywords rather than
machine-translating word-for-word (e.g. "Frontend Developer" -> "Desarrollador
Frontend", not a literal word-for-word translation) if you work in more than one
language.

## Search Sites

Primary (your market's job boards - scaffold one with `/add-portal`):
- **[YOUR_JOB_BOARD]** - your market's largest general job board
- **linkedin.com/jobs** - LinkedIn job listings (filter: [YOUR_COUNTRY] / [YOUR_CITY]); direct CLI subject to the canonical source-access gate
- **[YOUR_INDUSTRY_JOB_BOARD]** - a niche/industry board for your field (optional)
- **[YOUR_ADDITIONAL_JOB_BOARD]** - another major board for your market (optional)

Secondary (company career pages via Google):
- Direct Google searches with `site:` filters for known target companies

## Query Categories

Queries are grouped by priority. Write **each category in every language from your Languages table** (see Language scope above). Combine each query with your location terms (e.g. your city, region, or metro area) where the site supports it.

Each priority separates **Plain terms (portal CLIs)** from **WebSearch-only**
examples. A plain term is one role or skill, without `site:`, boolean `OR`,
alternative strings, or a separately specified location. Use one term per CLI
call; the selected skill's `Query syntax:` determines literal quote semantics.
Shell grouping quotes do not add quote characters to the argument. Exact-phrase
or boolean behavior is never inferred from another portal. Legacy personal
queries and request budgets follow canonical Step 1b; these tracked placeholders
are not a personal strategy and must never be executed.

**Organize by function, not job title.** The same underlying work carries different titles across companies and markets (a "Data Scientist" role at one employer may be posted as "Insights Analyst" or "Data Consultant" at another). Name each priority category after the function it covers, and list several plausible job titles as query variants within that category rather than betting an entire priority tier on one exact title string.

### Priority 1: [YOUR_PRIMARY_ROLE_TYPE]

These match your strongest and most desired career direction.

#### Plain terms (portal CLIs)

```text
[YOUR_PRIMARY_JOB_TITLE_1]
[YOUR_PRIMARY_JOB_TITLE_2]
[YOUR_KEY_SKILL]
```

#### WebSearch-only (`site:` fallback)

```
site:[YOUR_JOB_BOARD] "[YOUR_PRIMARY_JOB_TITLE_1]" [YOUR_CITY]
site:[YOUR_JOB_BOARD] "[YOUR_PRIMARY_JOB_TITLE_2]" [YOUR_CITY]
site:[YOUR_JOB_BOARD] "[YOUR_KEY_SKILL]" [YOUR_CITY]
site:linkedin.com/jobs "[YOUR_PRIMARY_JOB_TITLE_1]" [YOUR_COUNTRY]
```

### Priority 2: [YOUR_DOMAIN_EXPERTISE]

These match your domain expertise.

#### Plain terms (portal CLIs)

```text
[YOUR_DOMAIN_KEYWORD_1]
[YOUR_DOMAIN_KEYWORD_2]
```

#### WebSearch-only (`site:` fallback)

```
site:[YOUR_JOB_BOARD] [YOUR_DOMAIN_KEYWORD_1] [YOUR_CITY] OR [YOUR_REGION]
site:[YOUR_JOB_BOARD] [YOUR_DOMAIN_KEYWORD_2] [YOUR_COUNTRY]
site:linkedin.com/jobs [YOUR_DOMAIN_KEYWORD_1] [YOUR_CITY] [YOUR_COUNTRY]
```

### Priority 3: [YOUR_ADJACENT_ROLE_TYPE]

Adjacent roles you could pivot into.

#### Plain terms (portal CLIs)

```text
[YOUR_ADJACENT_TITLE_1]
[YOUR_ADJACENT_TITLE_2]
```

#### WebSearch-only (`site:` fallback)

```
site:[YOUR_JOB_BOARD] "[YOUR_ADJACENT_TITLE_1]" [YOUR_KEY_SKILL] [YOUR_CITY]
site:[YOUR_JOB_BOARD] "[YOUR_ADJACENT_TITLE_2]" [YOUR_KEY_SKILL] [YOUR_CITY]
```

### Priority 4: Broader Technical / Consulting

Wider net for general technical roles.

#### Plain terms (portal CLIs)

```text
[YOUR_KEY_SKILL] developer
technical consultant
```

#### WebSearch-only (`site:` fallback)

```
site:[YOUR_JOB_BOARD] [YOUR_KEY_SKILL] developer [YOUR_CITY]
site:linkedin.com/jobs "[YOUR_KEY_SKILL] developer" [YOUR_CITY]
site:[YOUR_JOB_BOARD] "technical consultant" [YOUR_DOMAIN] [YOUR_CITY]
```

## Location Filter

When evaluating results, verify the job location is within reasonable commute distance from your home. Define acceptable areas:
- [YOUR_CITY] and surrounding areas
- [ACCEPTABLE_AREA_1]
- [ACCEPTABLE_AREA_2]
- [BORDERLINE_AREA] (borderline - ~X min by transit)
- [TOO_FAR_AREA] (too far)

## Language Filter

Your working languages and levels are in `documents/profile/CLAUDE.md`'s
Languages table. When filtering scraped results, apply
the tracked `.claude/skills/job-application-assistant/04-job-evaluation.md`'s Language Gate: a posting requiring a
language you haven't declared at all is excluded; a posting requiring a higher
level than you declared in a language you do work in is not excluded, flag it
clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how
the flag surfaces in `/scrape` output). Postings simply *written* in a language
you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
