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

Install Bun/Python/LaTeX prerequisites as needed, and verify that OpenClaw
discovers `skills/job-search/SKILL.md` plus the portal skills under
`.agents/skills/`. Run setup once to initialize the gitignored
`documents/profile/` directory; never put candidate facts in tracked framework
files. A minimal dependency check is:

```bash
python3 --version
bun --version
lualatex --version
xelatex --version
```

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

Use a separate local checkout/workspace per candidate or agent. The code source can
be the same public fork, but each checkout must have its own gitignored
`documents/profile/`, market preferences, job state, and application outputs. Set
the public remote's push URL to a disabled value in a personal checkout so a normal
`git push` cannot publish local data:

If you need a remotely backed private copy, create a new private repository (not a
fork) and keep the public repository as `upstream`.

For a second candidate, repeat the clone and agent registration with a different
workspace path and agent name. Never point two candidates at the same checkout.

## Invoke

```text
$job-search setup --market finland
$job-search scrape --market finland
$job-search scrape --market europe
$job-search scrape --market china
$job-search rank --market europe
$job-search apply --market china <job URL or pasted JD>
```

The explicit market is resolved per run. The same candidate evidence is reused, while search sources, hard gates, wording, and application conventions come from the selected market overlay.
