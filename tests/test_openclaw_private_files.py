"""Use Git itself to verify that ordinary staging excludes personal runtime data."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OpenClawPrivateFilesTests(unittest.TestCase):
    def test_git_add_keeps_runtime_data_private_and_framework_trackable(self):
        private = [
            "USER.md", "MEMORY.md", "memory.md", "memory/2026-09-26.md",
            "memory/imports/prior-context.md", "SOUL.md", "IDENTITY.md",
            "TOOLS.md", "HEARTBEAT.md", "BOOT.md", "BOOTSTRAP.md", "DREAMS.md",
            ".openclaw/workspace-state.json", "documents/profile/01-candidate-profile.md",
        ]
        framework = ["AGENTS.md", "CLAUDE.md", "skills/job-search/SKILL.md",
                     ".agents/skills/example/SKILL.md", "documents/profile/.gitkeep"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(
                    ["git", "-c", "core.excludesfile=/dev/null", *args], cwd=root,
                    capture_output=True, text=True, check=True,
                ).stdout
            git("init", "--quiet")
            shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
            for name in private + framework:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic test content\n", encoding="utf-8")
            git("add", "--all")
            staged = set(git("ls-files", "-z").split("\0")) - {""}
            self.assertEqual(staged, set(framework) | {".gitignore"})
