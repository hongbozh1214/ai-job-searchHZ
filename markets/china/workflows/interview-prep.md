# China Interview Preparation Workflow

You are preparing interview material for a China-market role.

## Step 0: Parse Input

`$ARGUMENTS` should contain:

```text
interview <job-file-or-evaluation>
```

Use `.claude/commands/interview.md` Step 0 to identify **one exact tracker
application row**, including its source URL, status/date and
`china_posting_key:<slug>` marker. A saved inbox JD or evaluation file is an
input for locating that row, not permission to match only a company/role. When
several rows fit, list the sources and dates and ask which application has the
interview. For an untracked interview, accept the full JD directly and prepare
from it without claiming any old pack or submitted materials belong to it.

## Step 1: Read Inputs

Read:

- The selected row's archived posting and, if present, its evaluation file;
  confirm the evaluation's `**Source:**` or URL is this same saved JD.
- The exact application's archive under `documents/applications/<slug>/`,
  chosen from `china_posting_key:<slug>` in that row; apply the shared
  `/interview` legacy ambiguity rule when the marker is missing.
- The row's `china_text_pack:<relative-pack-path>` if present; check its
  `**Source:**` against the selected JD. A pack for a sibling posting or
  a prior application attempt must never be used.
- `documents/profile/01-candidate-profile.md` and approved local STAR notes.
- `documents/china/profile/candidate.md`
- `documents/china/profile/preferences.md`
- `documents/china/profile/evidence.md`
- `markets/china/templates/interview-answer.md`

For a text-only application, ask what the user actually sent before describing
pack text as submitted. For a full-document application, prefer the archive's
submitted CV and letter; use the selected tracker row's exact file paths only
when the submitted archive is unavailable. Stop and ask if these disagree.
China-only notes are translations or references; resolve conflicting facts
against the shared profile with the user before writing answers.

## Step 2: Identify Interview Themes

Extract:

- Core technical or professional questions.
- Project deep-dive topics.
- Business/domain questions.
- Collaboration and communication questions.
- Motivation and stability questions.
- Salary, city, work mode, and offer-risk topics.

## Step 3: Build Answer Outlines

For each important question, provide:

- What the interviewer is testing.
- Evidence-backed answer angle.
- STAR or CAR outline.
- Metrics or facts to mention.
- What not to overclaim.

Ground claims in approved evidence in `documents/profile/`, using the China
evidence file only for localized wording or pointers to that shared evidence.

## Step 4: Prepare Questions To Ask

Suggest questions about:

- Team responsibilities.
- Success metrics for the role.
- Reporting line and collaboration model.
- Product/business priorities.
- Onboarding expectations.
- Compensation structure if appropriate for the interview stage.

## Step 5: Write Prep File

For a tracked application, save `documents/applications/<slug>/interview_prep_<stage>.md`
as the shared interview workflow does; `<slug>` is the selected row's marker,
and `<stage>` is the specific interview stage. Preserve older stages. If the
same stage is prepared again, review the existing pack and save a dated
revision rather than silently overwriting it. For an untracked interview,
ask the user where to keep a clearly labeled prep draft and do not place it
in an existing application archive.

```markdown
# Interview Prep: <Role> @ <Company>

**Source:** <input file>
**Date:** YYYY-MM-DD

## Positioning

...

## Likely Questions And Answer Outlines

...

## Project Deep Dives

...

## Questions To Ask

...

## Risk Topics

...

## Salary / Offer Conversation Notes

...
```

## Step 6: Present Result

Summarize the most important preparation points and mention the output file path.
