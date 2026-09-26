# China Job Ranking Workflow

You are ranking manually saved China-market job descriptions. Do not fetch,
scrape, log in to, or automate any job platform.

## Step 1: Load Jobs

Find Markdown files under `markets/china/jobs/inbox/`. Import complete files into
the canonical state **before** running `candidates`:

```bash
python3 tools/rank_state.py import-local --market china
# Or target one file: ... import-local --market china --file "markets/china/jobs/inbox/<company>-<role>.md"
```

The importer accepts `# <Role> @ <Company>` and either substantial
`## Responsibilities` and `## Requirements` sections or a full JD pasted
under `## Paste Full JD Below` (at least 160 characters). A search snippet,
empty placeholder or symlink outside the inbox is rejected and reported; ask
the user to provide the full JD. It reuses any matching China scrape entry,
keeps its original URL and source, and marks changed local content as `new` for
re-ranking. Distinct source URLs retain separate state entries even when company
and role names match; when a second file has the same identity and no URL, ask
for a source URL rather than overwrite the first. It never uploads the JD or fetches a job board. Do not insert
`manual_required` snippets directly into scoring results.

If none exist, tell the user to save job descriptions as:

```text
markets/china/jobs/inbox/<company>-<role>.md
```

Skip files that are too thin to evaluate, such as files with only a title and no
responsibilities or requirements.

## Step 2: Load Profile

Read:

- `documents/china/profile/candidate.md`
- `documents/china/profile/preferences.md`
- `documents/china/profile/evidence.md`

If the profile is too sparse, stop and ask the user to run `$job-search setup --market china`.

## Step 3: Score Each Job

Run `candidates --market china` and score only selected rows with `job_file` by
reading that file. Do not run WebFetch on its source URL. If a candidate lacks
`job_file`, ask for a complete inbox JD and import it before scoring; never
score from a search snippet. The `awaiting_local_jd` count reports those rows,
which do not use a scoring batch slot. Use the canonical dimensions, weights, veto handling, and state tools in
`.claude/commands/rank.md`. The China rules below are market-specific gates and
risk notes, not a second incompatible scoring or persistence system.

Apply hard vetoes for:

- City/work mode outside stated hard constraints.
- Salary clearly below minimum expectation.
- Salary package that hides salary months, tax basis, or variable pay in a way
  that prevents honest comparison.
- 996,大小周, frequent unpaid overtime, or on-call expectations outside stated
  preferences.
- Outsourcing, labor dispatch / 劳务派遣, contractor, or驻场 arrangements outside
  stated preferences.
- Social insurance / 五险一金 or probation terms that violate stated hard requirements.
- Required skill or credential that the candidate clearly lacks and cannot
  credibly bridge.
- Role type listed under `暂不考虑岗位`.

Record each required China gate (`compensation`, `work_schedule`,
`employment_type`, `social_insurance`, `role_type`, `qualifications`) in the
`market_gates` object sent to `rank_state.py apply`. Record unsupported facts
as `FLAG` with a reason; only explicit violations of recorded hard preferences
are `FAIL`. Location uses `location_verdict`. The apply tool excludes any
market gate `FAIL` even if the weighted fit score is high.

## Step 4: Write Ranking Report

Use `tools/rank_state.py` with `--market china` exactly as required by `.claude/commands/rank.md` so
matching China entries in `job_scraper/seen_jobs.json` move from `new` to
`ranked` (or `expired`) and retain the canonical rank fields. Never rewrite the
whole state file by hand. The report below is an additional China-market view.

Write `markets/china/jobs/evaluated/ranking-YYYY-MM-DD.md`:

```markdown
# China Job Ranking - YYYY-MM-DD

## Summary

Ranked <N> jobs. Skipped <M> jobs due to insufficient JD detail.

## Shortlist

| Rank | Score | Verdict | Company | Role | Location | Next Action |
|---:|---:|---|---|---|---|---|

## Why The Top Jobs Ranked Highest

...

## Below Threshold

...

## Vetoed / Skipped

...

## China-Market Risk Notes

- Salary months / tax basis:
- Work schedule:
- Social insurance / probation:
- Employment type:

## Assumptions / Missing Info

...
```

## Step 5: Present Result

Show the top five jobs, any vetoed jobs, and the report path. Remind the user
that `$job-search apply --market china <job-file>` creates materials for a selected job.
