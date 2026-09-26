"""Guards for /reset's two scopes: documents and profile.

Both scopes have the same failure mode - /reset promises a clean slate it
does not deliver, because something that writes personal data is missing
from the Step 1 preview the user confirms and from the Step 3 execution.

Documents scope: /reset ends its documents pass by telling the user "The
`documents/` folder is now empty." That statement is only true if every
personal-data drop folder is actually covered by both the Step 1 preview
and the Step 3 delete block. `documents/postings/` was missing from both
while being documented in documents/README.md and protected as personal
data by tools/security_guards.py (review finding F26, 2026-08-19), so a
reset silently kept the user's hand-pasted job postings.

Profile scope now clears the complete gitignored `documents/profile/` directory.
The tracked files are templates and are deliberately not reset; this prevents
`/reset` from rewriting the public framework or destroying methodology updates.

Both file lists are derived - the documents folders from the repository
tree, the profile files from /setup Step 3's own headings - so a new drop
folder or a new /setup target fails this test until /reset covers it.
"""
import re

from tools import reset_state
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESET = REPO / ".claude" / "commands" / "reset.md"
SETUP = REPO / ".claude" / "commands" / "setup.md"


def tracked_document_subfolders():
    """Names of documents/ subfolders tracked in git (ignores local noise)."""
    out = subprocess.run(
        ["git", "ls-files", "documents/"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    folders = set()
    for line in out.splitlines():
        parts = line.split("/")
        if len(parts) >= 3:  # documents/<subfolder>/<file...>
            folders.add(parts[1])
    return folders


class TestResetCoversEveryDocumentsSubfolder(unittest.TestCase):
    def setUp(self):
        self.text = RESET.read_text(encoding="utf-8")
        # `profile` has its own separately confirmed destructive scope. A
        # documents-only reset must preserve it.
        self.folders = tracked_document_subfolders() - {"profile"}
        # The tree must actually contain the folders this test is about,
        # or the assertions below would pass vacuously.
        self.assertGreaterEqual(len(self.folders), 5, self.folders)

    def test_documents_scope_covers_tracked_document_subfolders(self):
        configured = {Path(name).parts[1] for name in reset_state.DOCUMENT_DIRS}
        self.assertFalse(self.folders - configured)
        self.assertIn("--scope <scope>", self.text)
        self.assertIn("--expected-digest", self.text)

    def test_documents_scope_excludes_profile_and_shell_globs(self):
        self.assertNotIn("documents/profile", reset_state.DOCUMENT_DIRS)
        self.assertNotIn("rm -rf", self.text)
        self.assertNotIn("find documents/", self.text)


def section(text: str, start: str, end: str) -> str:
    """The slice of text from the start marker up to the end marker."""
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def setup_step3_skill_files():
    """Skill files /setup Step 3 populates, derived from its own headings.

    Step 3's targets are written as '### <n>. <verb> `<target>`'. Local profile
    targets are retained so the reset contract covers the complete local profile.
    """
    step3 = section(SETUP.read_text(encoding="utf-8"), "## Step 3:", "## Step 4:")
    files = set()
    for target in re.findall(r"^###\s+\d+\.\s+\w+\s+`([^`]+)`", step3, re.MULTILINE):
        if target.startswith("documents/profile/"):
            files.add(Path(target).name)
    return files


class TestResetCoversEveryPersonalizedSkillFile(unittest.TestCase):
    def setUp(self):
        self.text = RESET.read_text(encoding="utf-8")
        self.files = setup_step3_skill_files()
        # /setup must actually still name these targets, or every assertion
        # below would pass vacuously against an empty set.
        self.assertGreaterEqual(len(self.files), 6, self.files)
        self.assertIn("04-job-evaluation.md", self.files)
        self.assertIn("search-queries.md", self.files)

    def test_preview_lists_every_personalized_skill_file(self):
        preview = section(
            self.text, "### If scope includes `profile`:", "### If scope includes `documents`:"
        )
        missing = sorted(f for f in self.files if f not in preview)
        self.assertEqual(
            missing,
            [],
            "reset.md's profile preview never mentions these files that /setup "
            "Step 3 writes candidate data into, so the user types RESET against "
            f"a list that omits them: {missing}",
        )

    def test_profile_scope_inventories_complete_profile_tree(self):
        source = __import__("inspect").getsource(reset_state.inventory)
        self.assertIn('collect(root / "documents/profile")', source)
        self.assertIn('scope in ("profile", "all", "full")', source)

    def test_preserved_list_claims_no_personalized_file_is_framework_only(self):
        """A file /setup personalizes must never be listed as framework-only.

        This is the specific regression: 04-job-evaluation.md was named in the
        "NOT touched (they contain framework rules, not candidate data)" list,
        so merely searching reset.md for the filename would have found it.
        """
        preserved = section(self.text, "The following files are NOT touched", "```")
        mislabeled = sorted(f for f in self.files if f in preserved)
        self.assertEqual(
            mislabeled,
            [],
            "reset.md tells the user these files contain 'framework rules, not "
            "candidate data', but /setup Step 3 writes candidate data into them: "
            f"{mislabeled}",
        )


if __name__ == "__main__":
    unittest.main()
