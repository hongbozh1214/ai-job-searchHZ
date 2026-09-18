# Market overlays

The repository keeps one evidence-backed candidate profile and separate market overlays. Choose one market per run:

| Market | Value | Primary scope |
| --- | --- | --- |
| China mainland | `china` | Chinese-language channels, China-specific communication and application conventions |
| Europe | `europe` | Cross-border EU/EEA/Switzerland plus optional UK; country and work-authorization filters are mandatory |
| Finland | `finland` | Finland-specific public services, English/Finnish/Swedish language requirements, local employers and research roles |

The shared files under `.claude/skills/job-application-assistant/` are authoritative for identity, experience, education, skills, and evidence. Market overlays may define search terms, locations, language expectations, salary display, application conventions, and deal-breakers.

Use `$job-search <operation> --market <value>` in OpenClaw. Do not combine markets into one ranking unless the user explicitly requests a comparison.
