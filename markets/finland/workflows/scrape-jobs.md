# Finland scrape workflow

1. Read the shared candidate profile and all files in this market overlay.
2. Build English and Finnish title/skill queries from evidence-backed experience.
3. Search direct employers first, then Job Market Finland, Work in Finland, EURAXESS/Academic Positions, LinkedIn, Duunitori, and Jobly.
4. For aggregator hits, locate and prefer the employer's original posting.
5. Record canonical URL, municipality, remote/hybrid status, posting and required working languages, contract duration, deadline, salary, and required attachments.
6. Apply hard gates, deduplicate, and then score fit.
7. Save results under `markets/finland/jobs/` and report blocked or incomplete sources.
