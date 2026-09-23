"""Guard the offline, candidate-local profile refresh contract."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class ProfileRefreshWorkflowTests(unittest.TestCase):
    def test_router_uses_canonical_workflow_without_a_market(self):
        skill = read("skills/job-search/SKILL.md")
        self.assertIn("$job-search profile-refresh linkedin", skill)
        self.assertIn("$job-search profile-refresh audit", skill)
        self.assertIn(".claude/commands/profile-refresh.md", skill)
        self.assertIn("needs no market", skill)

    def test_review_requires_supplied_linkedin_and_local_facts(self):
        command = read(".claude/commands/profile-refresh.md")
        for required in (
            "documents/profile/01-candidate-profile.md",
            "documents/linkedin/",
            "not shown",
            "needs verification",
            "documents/profile/linkedin-refresh/",
            "Do not overwrite an existing draft",
            "Do not access LinkedIn with browser automation",
        ):
            self.assertIn(required, command)
        self.assertIn("documents/profile/**", read(".gitignore"))
        self.assertIn("documents/linkedin/**", read(".gitignore"))

    def test_deployment_explains_nested_checkout_discovery(self):
        instructions = read("OPENCLAW_SETUP.md")
        self.assertIn("workspace-jobs-hongbo/ai-job-search", instructions)
        self.assertIn("checkout directory", instructions)
        self.assertIn("tools/doctor.py --agent <agent-id>", instructions)


if __name__ == "__main__":
    unittest.main()
