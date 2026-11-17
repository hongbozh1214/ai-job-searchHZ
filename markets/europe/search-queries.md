# Europe search sources and query patterns

## Source order

1. Direct employer career pages and installed company-ATS skills.
2. EURES for EU/EEA/Swiss mobility and vacancies.
3. EURAXESS for research and university roles when the user selects that sector.
4. LinkedIn and Indeed as user-controlled discovery leads, or an expressly
   approved interface; installation/enabled is not automated-access permission.
5. Remote boards installed in the workspace, restricted to Europe-compatible locations and time zones.
6. Country-specific public services or portal skills only for countries included in the run.

The official EURES job-search entry is
`https://europa.eu/eures/portal/jv-se/home?lang=en` (not the old eures.europa.eu
path). The deployed bounded keyword/detail branch follows canonical Step 0a
and Step 1g: it is eligible for the selected, budgeted Europe supplemental
scope, with provisional list leads and separately verified original details.
Keep query_scope/country_scope; historical acceptance is not coverage for a new run.
Location remains a client filter, not country selection; Finland codes are
unverified, and a single page is not a full Europe scan. EURAXESS's list is
`https://euraxess.ec.europa.eu/jobs/search`; follow canonical Step 1f and check
deployed source support. Its `/jobs` introduction is not a list scan.

Priority employers are search preferences, not an employer allowlist; follow
canonical Step 0a/1 for broader market keyword discovery under the shared budget.

For LinkedIn/Indeed follow canonical job-scraper Step 1e: selected user-provided
employer URLs/JDs use the existing analyze route; alerts are not an installed
mailbox collector or full JD. Indeed's documented Claude-only MCP is not verified
for OpenClaw. Do not schedule restricted direct scraping or assume licensed
access from an API key. Freehire is excluded from this user's repair priorities.

## Query patterns

Generate queries from the candidate's role families and evidence-backed skills. Combine one role family with one geography at a time. Examples:

```text
site:europa.eu/eures/portal/jv-se "<role keyword>" <country>
site:euraxess.ec.europa.eu/jobs "<role keyword>" <country>
site:jobs.lever.co "<role keyword>" <country>
site:boards.greenhouse.io "<role keyword>" Europe
site:jobs.ashbyhq.com "<role keyword>" Europe
```

Do not use an English-language query as evidence that local-language requirements are absent. Verify each shortlisted posting.
