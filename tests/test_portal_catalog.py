"""Offline portal discovery contracts; never touch a real registry or job state."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import portal_catalog  # noqa: E402

SOURCE = Path(portal_catalog.__file__)


class PortalCatalogPathTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="portal-catalog-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.workspace = self.base / "workspace"
        self.project = self.workspace / "ai-job-search"
        (self.project / "tools").mkdir(parents=True)
        self.script = self.project / "tools/portal_catalog.py"
        shutil.copyfile(SOURCE, self.script)
        self.other = self.base / "unrelated-cwd"
        self.other.mkdir()

    def skill(self, root, name="demo", body=None):
        skill = root / ".agents/skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(body if body is not None else f"---\nname: {name}\n---\n", encoding="utf-8")
        return skill

    def linked(self, link_agents=True):
        self.skill(self.workspace, "active")
        self.skill(self.workspace, "disabled", "---\nname: disabled\nenabled: false # keep disabled\n---\n")
        if link_agents:
            (self.project / ".agents").symlink_to("../.agents", target_is_directory=True)
        else:
            (self.project / ".agents").mkdir()
            (self.project / ".agents/skills").symlink_to("../../.agents/skills", target_is_directory=True)

    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(self.script), *map(str, args)],
                              cwd=cwd or self.project, capture_output=True, text=True, timeout=10)

    def assert_records(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        records = json.loads(proc.stdout)
        self.assertEqual([(r["name"], r["enabled"]) for r in records],
                         [("active", True), ("disabled", False)])
        self.assertEqual([r["path"] for r in records],
                         [f".agents/skills/{name}/SKILL.md" for name in ("active", "disabled")])
        return records

    def assert_failure(self, proc, message):
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "", "failure must not emit a partial catalog")
        self.assertIn(message, proc.stderr)

    def test_standalone_default_is_independent_of_cwd(self):
        self.skill(self.project, "active")
        self.skill(self.project, "disabled", "---\nname: disabled\nenabled: false\n---\n")
        for cwd in (self.project, self.workspace, self.other):
            with self.subTest(cwd=cwd):
                self.assert_records(self.run_cli(cwd=cwd))

    def test_standalone_explicit_root(self):
        self.skill(self.project, "active")
        self.skill(self.project, "disabled", "---\nname: disabled\nenabled: false\n---\n")
        self.assert_records(self.run_cli("--root", "."))
        self.assert_records(self.run_cli("--root", self.project, cwd=self.other))

    def test_linked_agents_explicit_workspace_from_different_cwds(self):
        self.linked()
        for cwd, root in ((self.project, ".."), (self.workspace, "."), (self.other, self.workspace)):
            with self.subTest(cwd=cwd):
                records = self.assert_records(self.run_cli("--root", root, cwd=cwd))
                for record in records:
                    self.assertTrue((self.workspace / record["path"]).is_file())

    def test_linked_skills_directory(self):
        self.linked(link_agents=False)
        self.assert_records(self.run_cli("--root", self.workspace))

    def test_linked_default_does_not_automatically_trust_parent(self):
        self.linked()
        self.assert_failure(self.run_cli(), "outside this checkout")

    def test_internal_skill_link_is_allowed(self):
        original = self.skill(self.project)
        renamed = original.parent.with_name("stored-demo")
        original.parent.rename(renamed)
        (self.project / ".agents/skills/demo").symlink_to("stored-demo", target_is_directory=True)
        self.assertEqual(len(portal_catalog.catalog(self.project)), 2)

    def test_external_skill_directory_is_rejected_even_with_workspace_root(self):
        self.linked()
        outside = self.skill(self.base / "workspace-other", "escape").parent
        (self.workspace / ".agents/skills/escape").symlink_to(outside, target_is_directory=True)
        self.assert_failure(self.run_cli("--root", self.workspace), "outside this checkout")

    def test_external_skill_file_is_rejected(self):
        path = self.skill(self.project)
        outside = self.base / "external-SKILL.md"
        outside.write_text(path.read_text())
        path.unlink()
        path.symlink_to(outside)
        self.assert_failure(self.run_cli(), "outside this checkout")

    def test_external_skills_root_is_rejected(self):
        outside = self.base / "external"
        self.skill(outside)
        (self.project / ".agents").symlink_to(outside / ".agents", target_is_directory=True)
        self.assert_failure(self.run_cli(), "outside this checkout")

    def test_grandparent_and_unrelated_explicit_roots_are_rejected(self):
        self.linked()
        for root in (self.base, self.other):
            with self.subTest(root=root):
                self.assert_failure(self.run_cli("--root", root), "discovery root must be")

    def test_arbitrary_parent_layout_is_not_accepted(self):
        self.skill(self.workspace)
        self.project = self.workspace / "arbitrary-child"
        (self.project / "tools").mkdir(parents=True)
        self.script = self.project / "tools/portal_catalog.py"
        shutil.copyfile(SOURCE, self.script)
        self.assert_failure(self.run_cli("--root", ".."), "discovery root must be")

    def test_missing_root_or_skills_directory_is_an_error(self):
        self.assert_failure(self.run_cli(), ".agents/skills")
        self.assert_failure(self.run_cli("--root", self.base / "missing"), "No such file")

    def test_skills_path_must_be_a_directory(self):
        (self.project / ".agents").mkdir()
        (self.project / ".agents/skills").write_text("not a directory")
        self.assert_failure(self.run_cli(), "not a directory")

    def test_existing_empty_skills_directory_is_an_empty_catalog(self):
        (self.project / ".agents/skills").mkdir(parents=True)
        proc = self.run_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [])

    def test_broken_skill_link_is_not_silently_ignored(self):
        (self.project / ".agents/skills").mkdir(parents=True)
        (self.project / ".agents/skills/broken").symlink_to("missing", target_is_directory=True)
        self.assert_failure(self.run_cli(), "No such file")

    def test_relative_root_is_relative_to_cwd_not_script(self):
        self.linked()
        self.assert_failure(self.run_cli("--root", ".", cwd=self.other), "discovery root must be")

    def test_help_describes_discovery_root_and_data_boundary(self):
        proc = self.run_cli("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--root", proc.stdout)
        self.assertIn("project data root", proc.stdout)

    def test_discovery_neither_reads_nor_rewrites_project_or_workspace_data(self):
        self.linked()
        before = {}
        # Different synthetic decoys would expose an accidental data-root swap.
        for root, marker in ((self.project, "project-only"), (self.workspace, "workspace-decoy")):
            for rel in ("company_pages.json", "job_scraper/seen_jobs.json", "job_search_tracker.csv"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(marker + ": deliberately not valid data\n")
                before[path] = path.read_bytes()
        self.assert_records(self.run_cli("--root", self.workspace, cwd=self.other))
        self.assert_failure(self.run_cli(), "outside this checkout")
        self.assertEqual({p: p.read_bytes() for p in before}, before)


class PortalCatalogFrontmatterTests(unittest.TestCase):
    def test_invalid_headers_fail_without_partial_output(self):
        invalid = [
            ("name: demo\n", "missing skill frontmatter"),
            ("---\nname: demo\n", "unclosed skill frontmatter"),
            ("---\nenabled: false\n---\n", "missing name"),
            ("---\nname:\nenabled: false\n---\n", "missing name"),
            ("---\nname: demo\nenabled: yes\n---\n", "invalid enabled"),
            ("---\nname: demo\nenabled:\n---\n", "invalid enabled"),
            ("---\nname: demo\nenabled: false\nenabled: true\n---\n", "duplicate"),
            ("---\nname: demo\nname: other\n---\n", "duplicate"),
            ("---\nname: demo\n enabled: false\n---\n", "invalid enabled"),
            ("---\nname: demo\nenabled : false\n---\n", "invalid enabled"),
        ]
        for body, message in invalid:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                folder = root / ".agents/skills/demo"
                folder.mkdir(parents=True)
                (folder / "SKILL.md").write_text(body)
                with self.assertRaisesRegex(ValueError, message):
                    portal_catalog.catalog(root)

    def test_disabled_flag_is_not_overridden_by_body_and_no_files_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / ".agents/skills/demo"
            folder.mkdir(parents=True)
            path = folder / "SKILL.md"
            path.write_text("---\nname: demo\nenabled: FALSE # intentional\n---\nenabled: true\n")
            before = path.read_bytes()
            self.assertEqual(portal_catalog.catalog(root)[0]["enabled"], False)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
