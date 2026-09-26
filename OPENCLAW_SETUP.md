# OpenClaw deployment

This repository is an OpenClaw workspace. It uses the OpenAI model configured in OpenClaw and does not require Claude Code or an Anthropic API key.

## Install

Until this branch becomes the repository default, clone it explicitly as the
agent's workspace root:

```bash
git clone --branch feature/local-profile-mode --single-branch \
  https://github.com/hongbozh1214/ai-job-searchHZ.git \
  /home/node/.openclaw/workspace-job-search
cd /home/node/.openclaw/workspace-job-search
git remote set-url --push origin DISABLED
```

Install Bun/Python/LaTeX prerequisites as needed. Run setup once to initialize
the gitignored `documents/profile/` directory; never put candidate facts in
tracked framework files.

Register the agent with this repository as its workspace. Omit `--model` to
inherit the configured default, or add the model already authorized in your
OpenClaw installation:

```bash
openclaw agents add job-search \
  --workspace /home/node/.openclaw/workspace-job-search \
  --non-interactive \
  --json
openclaw gateway restart
```

Run the read-only preflight **from each checkout**, using that checkout's own
agent ID (use the second agent's ID in its separate workspace):

```bash
python3 tools/doctor.py --agent job-search
```

The check reports Bun, Python, both LaTeX engines, local portal skill files,
OpenClaw's actual discovery of `job-search` for that agent, and the personal
`company_pages.json` registry. A missing registry is a warning until you choose
employers; a copied example registry is an error. A missing dependency or
undiscovered runtime skill gives exit code 1. The reported `workspaceDir` must
resolve to the current checkout, and the discovered `job-search` file must
resolve to this checkout's `skills/job-search/SKILL.md`. A same-named skill from
another workspace or a global override does not pass. Missing path information
also fails: a skill name alone cannot prove isolation. Run this check in the
same container/host as the agent so runtime paths refer to the same filesystem.
It reads files and calls only `openclaw skills list` and `openclaw skills info`;
it does not contact job sites or print registry entries.

To diagnose a failure, inspect these read-only commands in that environment:

```bash
openclaw agents list --json
openclaw skills list --agent job-search --json
openclaw skills info job-search --agent job-search --json
```

Use your actual agent ID in place of the `--agent job-search` value. Fix the
workspace/skill configuration before running setup; doctor never changes it.

Use a separate local checkout/workspace per candidate or agent. The code source can
be the same public fork, but each checkout must have its own gitignored
`documents/profile/`, market preferences, job state, and application outputs. Set
the public remote's push URL to a disabled value in a personal checkout so a normal
`git push` cannot publish local data.

OpenClaw's root `USER.md`, `MEMORY.md`, legacy `memory.md`, `memory/`, personal
bootstrap files, and `.openclaw/` state are also gitignored. Keep the tracked
root `AGENTS.md` and `CLAUDE.md` candidate-neutral. These ignore rules protect
new files; they do not untrack files already committed or staged. If personal
runtime files were previously tracked, back them up privately and remove only
those paths from the Git index before committing. Existing published history
requires a separate review; adding `.gitignore` rules cannot erase it.

If you need a remotely backed private copy, create a new private repository (not a
fork) and keep the public repository as `upstream`.

For a second candidate, repeat the clone and agent registration with a different
workspace path and agent name. Never point two candidates at the same checkout.
If the repository is cloned inside an existing workspace, for example
`workspace-jobs-hongbo/ai-job-search`, register the **checkout directory** as
that agent's workspace. An outer workspace with manually added skill paths is
not accepted by this isolation check: its default file operations and memory
would still use a different root. Preserve any existing personal bootstrap and
memory files when relocating an agent; do not overwrite the repository's
tracked instructions with them. Do not use one shared skill directory for two
candidates' local data.
OpenClaw discovers `skills/job-search/SKILL.md` relative to its configured
workspace, not by recursively searching an arbitrary child checkout. Run
`python3 tools/doctor.py --agent <agent-id>` in **each** checkout to confirm
runtime discovery before setup.

## Invoke

```text
$job-search setup --market finland
$job-search scrape --market finland
$job-search scrape --market europe
$job-search scrape --market china
$job-search rank --market europe
$job-search apply --market china <job URL or pasted JD>
$job-search profile-refresh audit
$job-search profile-refresh linkedin
```

The explicit market is resolved per run. The same candidate evidence is reused, while search sources, hard gates, wording, and application conventions come from the selected market overlay.
`profile-refresh` needs no market. Supply your own LinkedIn PDF export or pasted
profile fields under `documents/linkedin/`; this workflow produces only local
comparison and copy-ready text. Make LinkedIn edits yourself.
