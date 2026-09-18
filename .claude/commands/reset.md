# /reset - Reset Local Candidate Data

You are resetting parts of the job-search workspace back to a blank state so the
user can start fresh with `/setup`.

**This command is destructive.** Nothing is deleted until the user explicitly
confirms. Follow these steps exactly in order.

## Step 0: Parse scope

Recognize these scope keywords in `$ARGUMENTS`:

- `profile` — clear only the gitignored shared profile under `documents/profile/`
- `documents` — delete source documents and application archives under `documents/`
- `all` — both of the above

If no recognized scope is supplied, ask:

> What would you like to reset?
>
> - **`profile`** — Clear the local candidate facts, preferences, STAR examples,
>   search queries, and local CV baseline. Tracked framework templates are untouched.
> - **`documents`** — Delete CVs, LinkedIn exports, diplomas, references, projects,
>   postings, and application archives. The folder structure and README are preserved.
> - **`all`** — Both of the above.
>
> Reply with `profile`, `documents`, or `all`.

## Step 1: Show exactly what will be cleared

### If scope includes `profile`:

For `profile`, inspect and list these files (or mark each as missing/empty):

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

Explain that these are the only candidate-profile files cleared.

The following files are NOT touched (they contain framework rules and templates):

```text
CLAUDE.md
.claude/skills/**
cv/main_example.tex
```

They must not be edited or reset by this command.

### If scope includes `documents`:

For `documents`, list files in `documents/cv/`, `documents/linkedin/`,
`documents/diplomas/`, `documents/references/`, `documents/projects/`,
`documents/postings/`, and `documents/applications/`. Do not list or delete
`documents/README.md` or `.gitkeep` files.

## Step 2: Require explicit confirmation

Present:

> **This cannot be undone.**
>
> Type **`RESET`** (all caps) to confirm, or anything else to cancel.

Wait. Only an exact `RESET` proceeds; otherwise report “Reset cancelled. Nothing
was changed.”

## Step 3: Execute the reset

### Profile reset

For `profile`, delete the contents of the local profile directory but preserve its
directory marker:

This clears `CLAUDE.md`, `01-candidate-profile.md`, `02-behavioral-profile.md`,
`03-writing-style.md`, `04-job-evaluation.md`, `05-cv-templates.md`,
`06-cover-letter-templates.md`, `07-interview-prep.md`, `search-queries.md`, and
`cv/main_example.tex` within `documents/profile/`.

```bash
find documents/profile -type f ! -name .gitkeep -delete
```

### Documents reset

For `documents`, delete only user-provided source and application files:

```bash
rm -f documents/cv/*
rm -f documents/linkedin/*
rm -f documents/diplomas/*
rm -f documents/references/*
rm -f documents/projects/*
rm -f documents/postings/*
rm -rf documents/applications/*/
```

Do not run `git restore`, `git checkout`, or any command that rewrites tracked
framework files. In local-profile mode those files contain templates only.

## Step 4: Report

Report exactly which local files/folders were cleared and which were already empty
or intentionally preserved. Then tell the user:

> The local profile is now blank. Run `/setup --market <market>` (or `/setup`) to
> initialize `documents/profile/` again. Personal data stays gitignored; verify
> with `git status --ignored` and never force-add it.

If documents were reset, point to `documents/README.md` and explain that source
documents can be added again before `/setup`.
