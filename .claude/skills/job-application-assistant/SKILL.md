---
name: job-application-assistant
description: >
  Assists with job applications: evaluating job postings, tailoring CVs, writing cover letters,
  and preparing for interviews. Triggers on keywords like: job posting, job application, CV,
  cover letter, resume, interview prep, job fit, career, application, apply, ansøgning, stilling
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Bash, Edit, Write, AskUserQuestion
framework_version: 1.3.5
---

# Job Application Assistant

---

## Workflow

When the user provides a job posting (URL or text), follow this workflow:

Before starting, require the gitignored local profile under `documents/profile/`.
If `documents/profile/01-candidate-profile.md` or
`documents/profile/CLAUDE.md` is missing, stop and ask the user to run `/setup` (or
`$job-search setup --market <market>` in OpenClaw). The tracked files in this
skill directory are methodology and blank templates, never candidate evidence.

### Step 1: Research & Evaluate Fit
- Fetch the job posting content (use WebFetch for URLs). **A 403 is not a dead end** - follow the escalation order in `09-web-research.md` before concluding a page is unavailable, and prefer the employer's own careers posting over an aggregator listing
- Keep the **full posting text verbatim** for Step 3b to archive - never a summary
- Analyze the posting for required competencies, keywords, and priorities
- Research the company (website, LinkedIn, mission, recent news), per `09-web-research.md`
- Read the scoring rules from `04-job-evaluation.md`, the candidate-specific
  preferences from `documents/profile/04-job-evaluation.md`, and the candidate
  facts from `documents/profile/01-candidate-profile.md`
- Score the posting against those local facts and preferences
- Present the evaluation table and verdict
- Suggest whether the candidate should call the employer before applying (see `04-job-evaluation.md` for guidance)
- Ask the user if they want to proceed with an application

### Step 2: Tailor CV
- Before writing either document, choose one application slug by `/apply` Step 2: derive the ordinary slug by the **Subfolder naming** rule in `documents/README.md`; reuse the tracker row’s `posting_key:<slug>` for the same source URL, or use `python3 tools/job_key.py --collision` for a distinct URL when that slug is occupied. Reuse the chosen slug for the CV, cover letter, tracker marker, and Step 3b archive path. If existing applications make a missing URL ambiguous, ask before writing. If the rule says to stop because the derived name is empty, stop before creating any file.
- Use `documents/profile/cv/main_example.tex` as the factual master CV and read
  only a role-specific file under `cv/` for structure when one already exists
- Follow the methodology and active template in tracked `05-cv-templates.md`,
  candidate-specific statements in `documents/profile/05-cv-templates.md`,
  and contact data from `documents/profile/01-candidate-profile.md` and the
  local master CV; never copy tracked placeholders into a generated CV
- Create `cv/main_<company>_<role>.tex` with tailored content
- Adjust: profile statement, skills section, experience bullet emphasis, section order

### Step 3: Write Cover Letter
- Follow the rules in `03-writing-style.md` plus the candidate-specific patterns
  in `documents/profile/03-writing-style.md` (critical: no em-dashes, no cliches)
- Follow the structure and active template in tracked `06-cover-letter-templates.md`,
  approved personal patterns in `documents/profile/06-cover-letter-templates.md`,
  and contact/signature facts in `documents/profile/01-candidate-profile.md`
- Create `cover_letters/cover_<company>_<role>.tex`
- Ensure the letter connects specific experience to the role requirements

### Step 3b: Record the Application
- Run this once both documents exist. A CV or cover letter drafted alone is not yet an application.
- Follow **`/apply` Step 6b** (`.claude/commands/apply.md`) exactly: same header, same match-then-update rule, same `drafted` row, same posting archive, same prohibition on touching `job_scraper/seen_jobs.json`. It is stated there once so the two paths cannot drift. Four of its values are named in `/apply`'s own terms: `cv_file`/`cover_letter_file` are the paths written in Steps 2 and 3 here, `source` is the posting URL from Step 1, `deadline` is the application deadline from the posting text Step 1 keeps verbatim (empty when the posting states none - never guess one), and the posting text item 7 archives is the one Step 1 read.
- This step exists here because `/scrape` Step 5 routes straight into this skill. Without it, that path writes two documents and records nothing.

### Step 4: Interview Preparation
- Follow the framework in `07-interview-prep.md` and use only the candidate's
  STAR material from `documents/profile/07-interview-prep.md`
- Prepare STAR-format answers for likely questions
- Identify role-specific talking points
- Draft questions the candidate should ask the interviewer

---

## Reference Files

The tracked files in this directory define methodology and placeholders. Candidate
facts are read from the gitignored local copies under `documents/profile/`; setup
must initialize them before any application workflow runs. New local files use
the short `profile-templates/` outlines, except 01/02, which use tracked blank
profile outlines. For older full local copies, read only personal additions and
offer the reviewed compaction described in `/setup`.

| File | Purpose |
|------|---------|
| `documents/profile/01-candidate-profile.md` | Education, experience, skills, publications, awards |
| `documents/profile/02-behavioral-profile.md` | Behavioral assessment, strengths, ideal environments |
| `documents/profile/03-writing-style.md` | Candidate tone and style; tracked counterpart supplies rules |
| `documents/profile/04-job-evaluation.md` | Candidate preferences; tracked counterpart supplies scoring rules |
| `documents/profile/05-cv-templates.md` | Approved personal statements; tracked counterpart supplies tailoring rules |
| `documents/profile/06-cover-letter-templates.md` | Approved personal phrasing; tracked counterpart supplies structure |
| `documents/profile/07-interview-prep.md` | Personal STAR examples and approved answers; tracked counterpart supplies interview rules |
| `08-application-forms.md` | Portal free-text fields: self-introduction, project entries, character-limited pitches |
| `09-web-research.md` | Fetching postings and company pages: trust boundary, the WebFetch 403 fallback, escalation order, claim verification |

---

## Quick Commands

The user may also ask for individual steps without the full workflow:
- "Evaluate this job posting" - Step 1 only
- "Write a CV for [company]" - Step 2 only
- "Write a cover letter for [role] at [company]" - Step 3 only
- "Help me prepare for an interview at [company]" - Step 4 only
- "What jobs should I look for?" - Career strategy discussion using profile + evaluation framework
