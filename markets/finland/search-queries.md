# Finland search sources and query patterns

## Source order

1. Direct employer and university career pages; installed company-ATS skills.
2. Job Market Finland (`tyomarkkinatori.fi`) and Work in Finland (`workinfinland.com`).
3. EURAXESS and Academic Positions for research and university roles.
4. LinkedIn/Indeed user-controlled discovery leads and eligible Duunitori/Jobly
   methods for broader coverage; keep denied or unconfirmed methods skipped.
5. `valtiolle.fi` for central government and `kuntarekry.fi` for municipal/wellbeing-services roles when relevant.
6. Targeted searches of employers and sectors explicitly selected during setup.

## Query patterns

Use English and Finnish synonyms when appropriate:

```text
site:tyomarkkinatori.fi ("<English role>" OR "<Finnish role>")
site:workinfinland.com "<role keyword>"
site:euraxess.ec.europa.eu/jobs Finland "<research role keyword>"
site:academicpositions.com Finland "<academic role keyword>"
site:duunitori.fi ("<English role>" OR "<Finnish role>")
site:jobly.fi "<role keyword>"
```

Prefer the employer's original posting when an aggregator duplicates it.

EURAXESS job lists use `https://euraxess.ec.europa.eu/jobs/search`, not the
introduction at `/jobs`. Follow canonical Step 1f only when that CLI branch is
deployed and permitted; one-page client filtering is not a full Finland scan.

For LinkedIn/Indeed and manually selected Duunivahti leads, follow canonical
job-scraper Step 1e; this guide does not authorize scraping, mailbox access or
subscriptions. Indeed's documented Claude-only MCP is not verified for
OpenClaw. Job Market Finland's previously denied list API and Duunitori's denied
paths stay blocked until a separately documented permitted method is available;
do not substitute API versions or clients to retry them.

For selected Work in Finland reads, follow the canonical job-scraper workflow's
Step 1d explicit source mode; the HTML entry is
`https://www.workinfinland.com/en/open-jobs/`. Listing access, source selection
and downstream acceptance still require that workflow's gates and checks.

For priority employers versus broader market discovery, source eligibility and
leads-only versus verified-detail handling, follow canonical job-scraper Step 0a.
Priority companies are not an employer allowlist. This guide supplies no network
budget, unsupported reader capability or permission to access blocked services.
