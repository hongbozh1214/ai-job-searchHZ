# OpenClaw deployment

This repository is an OpenClaw workspace. It uses the OpenAI model configured in OpenClaw and does not require Claude Code or an Anthropic API key.

## Install

Clone the private working repository inside the OpenClaw workspace, install Bun/Python/LaTeX prerequisites as needed, and verify that OpenClaw discovers `skills/job-search/SKILL.md` plus the portal skills under `.agents/skills/`.

Use a private repository or local-only clone for populated profiles and applications. Keep this public fork free of personal data.

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
