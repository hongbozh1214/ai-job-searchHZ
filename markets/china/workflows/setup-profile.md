# China Profile Setup Workflow

You are setting up the China-market overlay profile.

There are two parallel locations involved — keeping them separate is what
prevents personal data from being committed to a public repo:

- `markets/china/profile/` — **templates**, tracked in git. Read-only for end
  users. They define the structure (section headings, China-specific fields
  like 薪资口径 / 五险一金 / 试用期 / 不接受外包) and serve as the starting point.
- `documents/china/profile/` — **local China wording and preferences**, gitignored
  via `documents/*/profile/**`. The canonical identity, experience, skills,
  dates and evidence live in `documents/profile/`; these China files may retain
  localized summaries and evidence pointers, never independent factual updates.

**Never edit files under `markets/china/profile/`. Only edit files under
`documents/china/profile/`.** If you find yourself wanting to change a template
section heading or add a new field, that is a framework change — discuss it
with the user as such, do not silently mutate the template.

## Step 1: Initialize Personal Copies (First Run)

Check each personal file independently and initialize only missing files. A
partial setup may already contain preferences or evidence even when
`candidate.md` is missing. Preserve every existing file, including empty files;
review gaps with the user later rather than replacing their files with templates.

```bash
mkdir -p documents/china/profile
for name in candidate.md preferences.md evidence.md; do
  target="documents/china/profile/$name"
  if [ ! -e "$target" ] && [ ! -L "$target" ]; then
    cp -n "markets/china/profile/$name" "$target"
  fi
done
```

If all personal copies already exist, this block makes no changes. Do not
replace it with a bulk copy gated only on `candidate.md`.

## Step 2: Read Current State

Read these personal files once:

- `documents/china/profile/candidate.md`
- `documents/china/profile/preferences.md`
- `documents/china/profile/evidence.md`

Read `documents/profile/01-candidate-profile.md`, `02-behavioral-profile.md`, and
the local profile notes (`CLAUDE.md`) when present. The shared profile is the
factual authority. A first-time China setup also initializes missing shared
profile files through `.claude/commands/setup.md` before accepting candidate
facts. If a populated China file has an extra or contradictory claim, present a
field-by-field comparison for the user's decision; never silently promote it
to the shared profile, replace it, or claim it is verified.

## Step 3: Detect Gaps

Check for:

- Empty profile sections.
- Placeholders that still need user input.
- Missing target roles, target cities, salary expectations, and hard exclusions.
- Missing China-market logistics: years of experience, availability, expected
  monthly salary and salary months, acceptable work schedule, social insurance
  requirements, probation limits, and whether outsourcing / labor dispatch is acceptable.
- Experience claims in `candidate.md` that do not have matching support in
  `evidence.md`.

If many sections are empty, ask the user whether to proceed by:

1. Reading source documents from `documents/` (e.g., CV PDFs, LinkedIn exports).
2. Importing a pasted CV.
3. Running a short interview.

## Step 4: Build Or Update Profile

When the user provides new or corrected candidate facts, update the shared
gitignored `documents/profile/01-candidate-profile.md` (or the appropriate
shared behavioral/STAR file) **first**, after asking about any conflict. Then
update only the relevant localized wording, evidence pointers and China-specific
preferences in the gitignored market files:

- `documents/china/profile/candidate.md` (translated summary; do not introduce facts)
- `documents/china/profile/preferences.md`
- `documents/china/profile/evidence.md` (references and wording linked to shared evidence)

Keep Chinese market wording practical and specific. Do not add claims that the
user has not supplied or that are not supported by source material.

## Step 5: Cross-Check

Before finishing, verify:

- Candidate identity and contact details are consistent.
- Target roles and hard exclusions are present.
- Salary expectations are either filled in or explicitly marked as undecided.
- Work schedule, social insurance, probation, outsourcing / labor dispatch, and
  availability preferences are either filled in or explicitly marked as undecided.
- Every major claimed strength has evidence.
- The shared profile contains each approved factual change, and China-only
  wording agrees with it. If a China file differs, leave the disputed text
  untouched but mark it as requiring confirmation; do not draft from it.
- Unsupported claims are moved to `需要补充证据的内容` or `不应声称的内容`.

## Step 6: Present Summary

Report:

- What was updated.
- What evidence-backed selling points are strongest.
- What information is still missing.
- Which command to run next, usually `$job-search analyze --market china markets/china/jobs/inbox/<job>.md`.

Remind the user that personal files under `documents/china/profile/` are
gitignored — they will not appear in `git status` and will not be committed.
