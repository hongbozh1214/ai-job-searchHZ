"""Regression guards for the local-only candidate profile contract."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class LocalProfileIgnoreTests(unittest.TestCase):
    def test_shared_profile_is_ignored_but_directory_marker_is_trackable(self):
        gitignore = read(".gitignore")
        self.assertIn("documents/profile/**", gitignore)
        self.assertIn("!documents/**/.gitkeep", gitignore)

    def test_security_guard_requires_shared_profile_ignore(self):
        guard = read("tools/security_guards.py")
        self.assertIn('"documents/profile/**"', guard)


class LocalProfileWorkflowTests(unittest.TestCase):
    def test_setup_writes_only_local_profile_targets(self):
        setup = read(".claude/commands/setup.md")
        step3 = setup.split("## Step 3: Generate Profile Files", 1)[1].split(
            "## Step 4: Confirm & Next Steps", 1
        )[0]
        self.assertIn("documents/profile/CLAUDE.md", step3)
        self.assertIn("documents/profile/01-candidate-profile.md", step3)
        self.assertIn("tracked counterparts are never write", step3)
        self.assertNotIn("### 1. Update `CLAUDE.md`", step3)
        self.assertNotIn("### 8. Update `cv/main_example.tex`", step3)

    def test_core_workflows_read_local_profile(self):
        required = {
            ".claude/commands/apply.md": "documents/profile/01-candidate-profile.md",
            ".claude/commands/rank.md": "documents/profile/01-candidate-profile.md",
            ".claude/commands/interview.md": "documents/profile/01-candidate-profile.md",
            ".claude/commands/expand.md": "documents/profile/01-candidate-profile.md",
            ".claude/skills/job-scraper/SKILL.md": "documents/profile/search-queries.md",
            ".claude/skills/upskill/SKILL.md": "documents/profile/01-candidate-profile.md",
        }
        for file, needle in required.items():
            with self.subTest(file=file):
                self.assertIn(needle, read(file))

    def test_reset_never_rewrites_tracked_framework_files(self):
        reset = read(".claude/commands/reset.md")
        self.assertIn("documents/profile/", reset)
        self.assertIn("Do not run `git restore`, `git checkout`", reset)
        self.assertIn("cv/main_example.tex", reset)

    def test_openclaw_contract_is_per_checkout(self):
        setup = read("OPENCLAW_SETUP.md")
        self.assertIn("separate local checkout/workspace per candidate or agent", setup)
        self.assertIn("documents/profile/", setup)


if __name__ == "__main__":
    unittest.main()
