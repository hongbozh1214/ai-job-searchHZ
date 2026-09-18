# Europe scrape workflow

1. Read the shared candidate profile, `documents/europe/profile/preferences.md`, `markets/europe/search-queries.md`, and `markets/europe/evaluation.md`. If the personal preferences file is missing, stop and run `$job-search setup --market europe`; do not read user data from or write it to the tracked template.
2. Confirm the included countries if they remain empty. A broad `Europe` run without country scope may be used only when the user explicitly asks for it.
3. Search direct ATS/employer sources, EURES, EURAXESS, and enabled global portal skills.
4. Verify the employer posting for every shortlisted aggregator result.
5. Record source, canonical URL, country, location/remote status, posting language, required languages, authorization/sponsorship wording, contract type, deadline, and salary as stated.
6. Deduplicate and apply hard gates before fit scoring.
7. Save results under `markets/europe/jobs/` and report sources that were blocked or incomplete.
