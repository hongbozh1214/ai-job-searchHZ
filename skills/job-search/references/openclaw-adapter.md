# OpenClaw runtime adapter

The `.claude/` directory remains the canonical workflow specification. It contains no requirement to use Anthropic's API.

Translate upstream tool names by behavior:

| Upstream term | OpenClaw behavior |
| --- | --- |
| `Read`, `Glob`, `Grep` | Inspect files with the available workspace/file tools. |
| `Write`, `Edit` | Make scoped edits inside the job-search workspace. |
| `Bash` | Run only task-relevant local commands in the workspace. |
| `WebSearch`, `WebFetch` | Use an available web-search/fetch tool or a documented portal CLI. |
| `AskUserQuestion` | Ask one concise question only when the missing choice materially changes the result. |
| `Agent`, `Task` | Use an OpenClaw subagent for the independent reviewer or parallel scoring step when available. Otherwise perform a clearly labeled second-pass review in the same run. |
| `/name` | Treat as the named workflow. |

Use the OpenAI model already configured for the OpenClaw agent. Do not require Claude Code, an Anthropic account, or an Anthropic API key.

## Privacy boundary

- A public template fork is suitable for code, not personal profile data.
- Keep populated profiles, CVs, contact details, application archives, tracker data, and generated documents local or in a private repository.
- Before pushing, inspect the exact staged paths and exclude personal/job data.
- Never place credentials in a skill, prompt, tracked `.env`, or generated report.

## Human gate

Search, scoring, drafting, and preparation may run autonomously. Sending messages, submitting applications, editing logged-in profiles, accepting offers, and deleting records require an explicit user instruction at that step.
