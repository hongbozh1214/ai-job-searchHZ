"""The markdown workflows are executable instructions; pin the language routes."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class MarketCvLanguageContract(unittest.TestCase):
    def test_finland_europe_english_independent_of_legacy_global_field(self):
        apply = read(".claude/commands/apply.md")
        self.assertIn("For Finland and Europe, create an **English** CV by default", apply)
        self.assertIn("different language requires an explicit request", apply)
        self.assertIn("An old `CV language:` line in a local profile does not override", apply)
        self.assertNotIn("CV language from the profile", apply)

    def test_china_choice_is_per_full_application_only(self):
        overlay = read("markets/china/workflows/apply-job.md")
        router = read("skills/job-search/SKILL.md")
        self.assertIn("English, Chinese or both", overlay)
        self.assertIn("ask before drafting the full CV", overlay)
        self.assertIn("Wait for the answer", overlay)
        self.assertIn("text-pack route, which needs no CV language question", overlay)
        self.assertIn("do not\n  prompt for CV language in text-pack mode", router)
        self.assertIn("cv/main_<slug>.tex", overlay)
        self.assertIn("cv/chinese/main_<slug>.tex", overlay)

    def test_both_versions_are_verified_and_recorded_separately(self):
        apply = read(".claude/commands/apply.md")
        overlay = read("markets/china/workflows/apply-job.md")
        outcome = read(".claude/commands/outcome.md")
        self.assertIn("pass every requested CV and the letter inline", apply)
        self.assertIn("every selected CV PDF", apply)
        self.assertIn("both text layers", apply)
        self.assertIn("china_extra_cv:cv/main_<slug>.tex", overlay)
        self.assertIn("remove any obsolete `china_extra_cv:`", overlay)
        self.assertIn("ask which CV language(s) the user actually submitted", outcome)
        self.assertIn("cv_draft_en.tex", outcome)

    def test_setup_no_longer_writes_a_global_language_setting(self):
        setup = read(".claude/commands/setup.md")
        profile = read("profile-templates/CLAUDE.md")
        self.assertIn("Do not collect a global CV-language preference", setup)
        self.assertNotIn("[YOUR_CV_LANGUAGE]", profile)


if __name__ == "__main__":
    unittest.main()
