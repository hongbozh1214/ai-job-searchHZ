"""Full reset must preview private state and preserve tracked or shared files."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import reset_state


class ResetStateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("documents/**\nmarkets/*/jobs/**\njob_search_tracker.csv\ncompany_pages.json\n", encoding="utf-8")
        (self.root / "documents/profile").mkdir(parents=True)
        (self.root / "documents/profile/.gitkeep").touch()
        (self.root / "documents/profile/private.md").write_text("secret", encoding="utf-8")
        (self.root / "job_search_tracker.csv").write_text("private", encoding="utf-8")
        (self.root / "markets/china/jobs/inbox").mkdir(parents=True)
        (self.root / "markets/china/jobs/inbox/jd.md").write_text("private", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "documents/profile/.gitkeep"], check=True)

    def run_reset(self, *args):
        if "--execute" in args and "--expected-digest" not in args:
            preview_output = io.StringIO()
            scope = args[args.index("--scope") + 1] if "--scope" in args else "full"
            with contextlib.redirect_stdout(preview_output):
                reset_state.main(["--scope", scope], self.root)
            args += ("--expected-digest", json.loads(preview_output.getvalue())["digest"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            code = reset_state.main(list(args), self.root)
        return code, json.loads(output.getvalue().split("\nDeleted ")[0])

    def test_preview_is_read_only_and_execute_clears_only_ignored_files(self):
        code, preview = self.run_reset()
        self.assertEqual(code, 0)
        self.assertEqual(preview["mode"], "preview")
        self.assertEqual(set(preview["files"]), {
            "documents/profile/private.md", "job_search_tracker.csv",
            "markets/china/jobs/inbox/jd.md"})
        self.assertTrue((self.root / "documents/profile/private.md").exists())
        code, actual = self.run_reset("--execute", "--confirm", "RESET")
        self.assertEqual(code, 0)
        self.assertEqual(actual["files"], preview["files"])
        self.assertTrue((self.root / "documents/profile/.gitkeep").exists())
        self.assertTrue((self.root / ".gitignore").exists())
        self.assertFalse((self.root / "documents/profile/private.md").exists())

    def test_nonignored_file_aborts_without_partial_deletion(self):
        (self.root / ".gitignore").write_text("job_search_tracker.csv\n", encoding="utf-8")
        code, preview = self.run_reset("--execute", "--confirm", "RESET")
        self.assertEqual(code, 1)
        self.assertIn("documents/profile/private.md", preview["preserved"])
        self.assertTrue((self.root / "job_search_tracker.csv").exists())

    def test_symlink_to_another_checkout_is_removed_without_following(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        other = Path(outside.name)
        (self.root / "documents/profile/alias").symlink_to(other, target_is_directory=True)
        code, _ = self.run_reset("--execute", "--confirm", "RESET")
        self.assertEqual(code, 0)
        self.assertTrue(other.is_dir())
        self.assertFalse((self.root / "documents/profile/alias").exists())

    def test_documents_scope_preserves_profile_and_tracker(self):
        (self.root / "documents/cv").mkdir()
        (self.root / "documents/cv/private.tex").write_text("secret")
        code, actual = self.run_reset("--scope", "documents", "--execute", "--confirm", "RESET")
        self.assertEqual(code, 0)
        self.assertEqual(actual["files"], ["documents/cv/private.tex"])
        self.assertTrue((self.root / "documents/profile/private.md").exists())
        self.assertTrue((self.root / "job_search_tracker.csv").exists())

    def test_stale_preview_refuses_new_files(self):
        _, preview = self.run_reset()
        (self.root / "documents/profile/new.md").write_text("new private data")
        code, _ = self.run_reset("--execute", "--confirm", "RESET", "--expected-digest", preview["digest"])
        self.assertEqual(code, 1)
        self.assertTrue((self.root / "documents/profile/private.md").exists())

    def test_documents_symlink_to_other_checkout_does_not_follow(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name)
        (target / "important.txt").write_text("keep")
        (self.root / "documents/cv").symlink_to(target, target_is_directory=True)
        code, _ = self.run_reset("--scope", "documents", "--execute", "--confirm", "RESET")
        self.assertEqual(code, 0)
        self.assertEqual((target / "important.txt").read_text(), "keep")
        self.assertFalse((self.root / "documents/cv").is_symlink())

    def test_full_scope_covers_market_jobs_root(self):
        (self.root / "markets/china/jobs/root.md").write_text("secret")
        code, preview = self.run_reset()
        self.assertEqual(code, 0)
        self.assertIn("markets/china/jobs/root.md", preview["files"])

    def test_repo_ignores_direct_market_jobs_files(self):
        repo = Path(__file__).resolve().parent.parent
        for market in ("europe", "finland"):
            result = subprocess.run(["git", "check-ignore", "--no-index", "-q",
                                     f"markets/{market}/jobs/raw.md"], cwd=repo, check=False)
            self.assertEqual(result.returncode, 0)

    def test_parent_symlink_refuses_reset(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        other = Path(outside.name)
        (self.root / "markets/china/jobs/inbox/jd.md").unlink()
        (self.root / "markets/china/jobs/inbox").rmdir()
        (self.root / "markets/china/jobs").rmdir()
        (self.root / "markets/china").rmdir()
        (self.root / "markets/china").symlink_to(other, target_is_directory=True)
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            code = reset_state.main(["--execute", "--confirm", "RESET", "--expected-digest", "stale"], self.root)
        self.assertEqual(code, 1)
        self.assertTrue((self.root / "documents/profile/private.md").exists())


if __name__ == "__main__":
    unittest.main()
