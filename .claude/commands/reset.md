# /reset - Reset Local Candidate Data

You are resetting parts of the job-search workspace back to a blank state so the
user can start fresh with `/setup`.

**This command is destructive.** Nothing is deleted until the user explicitly
confirms. Follow these steps exactly in order.

## Step 0: Parse scope

Recognize these scope keywords in `$ARGUMENTS`:

- `profile` — clear only the gitignored shared profile under `documents/profile/`
- `documents` — delete source documents and application archives under `documents/`
- `all` — both of the above; job state and market preferences remain
- `full` — preview and clear candidate data across this checkout, including
  market preferences, scraper state, tracker, registry, generated output and memory

If no recognized scope is supplied, ask:

> What would you like to reset?
>
> - **`profile`** — Clear the local candidate facts, preferences, STAR examples,
>   search queries, and local CV baseline. Tracked framework templates are untouched.
> - **`documents`** — Delete CVs, LinkedIn exports, diplomas, references, projects,
>   postings, and application archives. The folder structure and README are preserved.
> - **`all`** — Both of the above; keeps job state and market preferences.
> - **`full`** — All local candidate data in this checkout (preview before deletion).
>
> Reply with `profile`, `documents`, `all`, or `full`.

## Step 1: Show exactly what will be cleared

From the current checkout run `python3 tools/reset_state.py --scope <scope>`,
where `<scope>` is the chosen `profile`, `documents`, `all`, or `full`.
Show the exact `files` and `preserved` lists and the `digest` from this preview.
If `preserved` is nonempty, explain why those files cannot be safely deleted;
the command will refuse a partial reset. Do not read or print file contents.

### If scope includes `profile`:

For `profile`, the preview covers these files when present:

- `documents/profile/CLAUDE.md`
- `documents/profile/01-candidate-profile.md`
- `documents/profile/02-behavioral-profile.md`
- `documents/profile/03-writing-style.md`
- `documents/profile/04-job-evaluation.md`
- `documents/profile/05-cv-templates.md`
- `documents/profile/06-cover-letter-templates.md`
- `documents/profile/07-interview-prep.md`
- `documents/profile/search-queries.md`
- `documents/profile/cv/main_example.tex`
- `documents/profile/legacy-backup/` (if a prior local profile was compacted,
  this contains the original personal files and will also be deleted)

Explain that all gitignored personal files under `documents/profile/`, including
additional notes and legacy backups, are cleared. Include any additional files
found by the preview before asking for confirmation.

The following files are NOT touched (they contain framework rules and templates):

```text
CLAUDE.md
.claude/skills/**
cv/main_example.tex
```

They must not be edited or reset by this command.

### If scope includes `documents`:

For `documents`, preview files in `documents/cv/`, `documents/linkedin/`,
`documents/diplomas/`, `documents/references/`, `documents/projects/`,
`documents/postings/`, and `documents/applications/`. Do not list or delete
`documents/README.md` or `.gitkeep` files.

### If scope is `full`:

Use the `full` scope preview and show its `files` and `preserved` lists. This
includes `documents/profile/`, `documents/<market>/profile/`, source documents,
`markets/<market>/jobs/{inbox,evaluated,archived}/`, scraper `seen_jobs.json`,
`job_search_tracker.csv`, `company_pages.json`, application and generated CV/letter
outputs, reports and OpenClaw workspace memory. The script refuses to clear
tracked or non-ignored files. `.gitkeep` files and tracked examples remain.
`full` never applies to another candidate's checkout. Tell the user
that external services (such as Notion and the model provider), browser sessions,
and backups remain outside this checkout; `.env` secrets are deliberately not
cleared. If `COMPANY_PAGES_REGISTRY` points outside this checkout, that file is
also not cleared. Never claim those locations were reset.

## Step 2: Require explicit confirmation

Present:

> **This cannot be undone.**
>
> Type **`RESET`** (all caps) to confirm, or anything else to cancel.

Wait. Only an exact `RESET` proceeds; otherwise report “Reset cancelled. Nothing
was changed.”

## Step 3: Execute the reset

After showing the preview and receiving the exact confirmation, run:

```bash
python3 tools/reset_state.py --scope <scope> --execute --confirm RESET --expected-digest <preview-digest>
```

Substitute only the scope and digest shown in Step 1. The script will refuse
to run if files changed since that preview or any unignored/tracked file would
remain. It never follows directory links into another workspace. If the script fails,
stop and report what remains. Do not improvise a recursive delete.

Do not run `git restore`, `git checkout`, or any command that rewrites tracked
framework files. In local-profile mode those files contain templates only.

## Step 4: Report

Report exactly which local files/folders were cleared and which were already empty
or intentionally preserved. Then tell the user:

> If your reset included `profile` (or `full`), the local profile is now blank.
> Run `/setup --market <market>` (or `/setup`) to initialize it again. Personal
> files should remain gitignored; verify with `git status --ignored` and never
> force-add them.

If documents were reset, point to `documents/README.md` and explain that source
documents can be added again before `/setup`.
