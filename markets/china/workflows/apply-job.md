# China Job Application Workflow

You are creating China-market application material for a manually saved job
description. Do not contact the employer or operate any job platform.

## Step 0: Parse Input

`$ARGUMENTS` may contain:

```text
apply --market china <job-file | pasted full JD | URL>
```

For a local file, use a complete JD under `markets/china/jobs/inbox/`. For pasted
text, require a company, role and substantial duties/requirements; save it as a
new Markdown file under that gitignored inbox using `# <Role> @ <Company>` and
`## Paste Full JD Below`. Do not overwrite an existing file with different
content; choose a distinct safe filename or ask which version is current. For a
URL alone, ask the user to paste/save the full JD with its source URL: never
fetch a China job platform during this workflow. Do not draft from a search
snippet. The saved inbox file is the single posting input used throughout
drafting and archiving. A job does not need a rank-state entry to be drafted.

## Step 1: Read Inputs

Read:

- The job file.
- `documents/china/profile/candidate.md`
- `documents/china/profile/preferences.md`
- `documents/china/profile/evidence.md`
- `markets/china/templates/boss-greeting.md`
- `markets/china/templates/recruiter-message.md`
- `markets/china/templates/chinese-cover-letter.md`
- `markets/china/templates/interview-answer.md`
- For full-document mode only, the **local candidate CV baseline** at
  `documents/profile/cv/main_example.tex` and the tracked structural guides
  `cv/chinese/main_example.tex` and `cover_letters/chinese/cover_example.tex`.

If an evaluation exists under `markets/china/jobs/evaluated/` for the same
posting URL or posting-specific key, read it and use its score, strengths,
gaps, and red flags. Do not reuse an evaluation for a different URL solely
because the company and role names match.
If none exists, assess this JD against local candidate evidence and China
preferences using the six dimensions in `markets/china/workflows/analyze-job.md`;
record the actual numeric score or leave the tracker rating empty if evidence
is insufficient. Never invent a score. Verify deadline and hard constraints
before drafting; report an expired deadline or a hard veto rather than
recommending submission.

## Step 2: Factual Guard

Before drafting, identify:

- Claims that are fully supported by evidence.
- Claims that are plausible but need user confirmation.
- Gaps that must remain visible.

Do not write unsupported claims as facts. If the job asks for a missing skill,
phrase it as a learning/adjacent-experience angle only when honest.

## Step 3: Draft Outputs

Produce:

- BOSS 直聘打招呼话术: 1 concise version under 80 Chinese characters, plus 1
  slightly fuller version under 140 Chinese characters.
- 招聘者/猎头私信: one message suitable for Maimai, WeChat, or email.
- 中文求职信/邮件: concise, role-specific, evidence-backed.
- 简历修改建议: bullets to emphasize, bullets to remove, keywords to add only if
  evidence supports them.
- 中文 LaTeX 简历/求职信生成建议: if the user explicitly asks for full `.tex`
  files, use `cv/chinese/main_example.tex` and
  `cover_letters/chinese/cover_example.tex` as structural references. Otherwise,
  keep the output as targeted resume-editing guidance and a concise letter/email.
- 面试准备重点: likely questions and evidence-backed answer angles.

Tone:

- Specific, direct, and professional.
- Avoid exaggerated slogans such as "我对贵司仰慕已久" unless the user provides a
  concrete reason.
- Avoid pretending to have experience the profile does not support.

There are two output modes:

- **Text pack (default):** save the Markdown application pack in Step 4. Review
  each claim against the local evidence and mark unsupported wording for user
  confirmation. Do not call the generic PDF compilation, PDF layout inspection,
  ATS extraction or two-document reviewer steps: there are no CV/cover files
  to inspect in this mode.
- **Full documents (only on explicit request):** also draft the role-specific
  CV and cover letter as `cv/chinese/main_<slug>.tex` and
  `cover_letters/chinese/cover_<slug>.tex`. Use the shared `/apply` reviewer,
  factual guard, compile, page-count, visual inspection, ATS text-extraction
  and final-verification steps for these real files. Compile with LuaLaTeX for
  the CV and XeLaTeX for the cover letter unless a verified custom template
  declares its own commands. Fix failures before claiming the PDFs are ready.
  Do not replace tracked Chinese example templates with personal data.

## Step 4: Save Application Pack

Derive a safe posting-specific `<slug>` from `tools/job_key.py` and the saved
JD URL. If the same company/role already has an application or archive with a
**different** known URL, use the `make_url_collision_key` URL suffix from that
tool to keep both postings distinct. If a second posting lacks a URL or the
identity of an existing pack cannot be verified, stop and ask which posting
the user means; never replace an older pack. Keep this exact slug for the
pack, full-document filenames and application archive. Write
`markets/china/jobs/evaluated/<slug>-application.md`:

```markdown
# Application Pack: <Role> @ <Company>

**Source:** <job file>
**Date:** YYYY-MM-DD

## Supported Positioning

...

## BOSS Greeting

...

## Recruiter Message

...

## Chinese Cover Letter / Email

...

## Resume Tailoring Suggestions

...

## Chinese LaTeX Template Notes

Use `cv/chinese/main_example.tex` and `cover_letters/chinese/cover_example.tex`
only if the user asks for full compilable documents. Keep all generated personal
files out of git-tracked template paths.

## Interview Focus

...

## Gaps To Keep Honest

...

## User Confirmation Needed

...
```

## Step 5: Record Draft and Present Result

After the pack and any requested documents pass their applicable checks, run
the shared `.claude/commands/apply.md` Step 6b **before ending the turn**:

- Create or update the normal `job_search_tracker.csv` row with `status: drafted`;
  never record it as sent/applied without the user's explicit confirmation.
  Use the existing tracker header, open/final row rules and CSV-safe notes.
  Match an open row by its **source URL** first. When both source URLs exist
  and differ, append a separate row even if company and role are identical;
  never update the other posting's tracker row. With missing URLs, use the
  company/role pair only when unambiguous, otherwise ask.
- Add `china_posting_key:<slug>` to notes in either mode, so `/outcome` and
  `/interview` use the same archive when company/role names recur.
- In text-only mode, set `cv_file` and `cover_letter_file` to empty strings,
  and add the marker `china_text_pack:<relative-pack-path>` to `notes` (no
  commas, quotes or line breaks). Keep an existing draft's `cv_file` and
  `cover_letter_file` if it already has real generated files; never clear them
  on a text refresh. The marker points to the application pack, not a
  fictional CV or `.tex` cover letter.
- In full-document mode, set `cv_file` and `cover_letter_file` to the actual
  generated `.tex` files. Keep the pack path in notes for the greeting. If a
  prior text-only draft left a `china_text_pack:` marker on this same row,
  remove only that obsolete marker after writing the verified full documents;
  preserve the rest of the notes.
- For either mode, use the source URL **from the local JD** if present in the
  tracker `source` column, otherwise leave it empty; set `deadline` only from
  the JD; use the actual China evaluation score in `fit_rating` (or blank if
  not supportable). Archive the *full saved JD text* as
  `documents/applications/<slug>/job_posting.md`, leaving an existing
  archived copy intact. The tracker and archives remain gitignored. Never
  fetch a URL to reconstruct the archived JD. If a different posting already
  occupies that path, stop and choose a distinct URL-based slug before writing.

Show the BOSS greeting, recruiter message, mode, tracker draft status and
output path(s). Mention any user confirmations needed before the user sends
anything. A text-only pack is ready to review and manually copy; full
document mode also supplies verified PDFs.
