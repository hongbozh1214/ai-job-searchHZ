"""Execute the documented initialization with fresh, partial and existing profiles."""

import itertools
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("candidate.md", "preferences.md", "evidence.md")
WORKFLOW = ROOT / "markets/china/workflows/setup-profile.md"


class ChinaInitializationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.personal = self.root / "documents/china/profile"
        self.personal.mkdir(parents=True)
        self.templates = self.root / "markets/china/profile"
        shutil.copytree(ROOT / "markets/china/profile", self.templates)
        self.command = re.search(r"```bash\n(.*?)```", WORKFLOW.read_text(encoding="utf-8"), re.S).group(1)

    def initialize(self):
        result = subprocess.run(["sh", "-eu", "-c", self.command], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_partial_profiles_preserve_existing_files_and_fill_missing_ones(self):
        for existing in itertools.product((False, True), repeat=len(NAMES)):
            with self.subTest(existing=existing):
                expected = {}
                for name, present in zip(NAMES, existing):
                    path = self.personal / name
                    path.unlink(missing_ok=True)
                    if present:
                        path.write_text(f"CONFIRMED: {name}\n", encoding="utf-8")
                        expected[name] = path.read_bytes()
                    else:
                        expected[name] = (self.templates / name).read_bytes()
                self.initialize()
                self.initialize()  # re-running setup must be harmless
                for name in NAMES:
                    self.assertEqual((self.personal / name).read_bytes(), expected[name])

    def test_empty_existing_file_is_preserved(self):
        (self.personal / "preferences.md").touch()
        self.initialize()
        self.assertEqual((self.personal / "preferences.md").read_bytes(), b"")

    def test_dangling_link_is_not_replaced_or_written_through(self):
        target = self.root / "not-created.md"
        link = self.personal / "preferences.md"
        link.symlink_to(target)
        self.initialize()
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())
