"""Behavioral checks for the read-only workspace doctor."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import doctor

DEFAULT = object()


class DoctorTests(unittest.TestCase):
    def test_registry_never_accepts_example_or_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "company_pages.json"
            with patch.dict("os.environ", {}, clear=True):
                self.assertFalse(doctor.registry(root))  # optional before setup
                path.write_text("{", encoding="utf-8")
                self.assertTrue(doctor.registry(root))
                path.write_text(json.dumps([{"name": "Example Employer", "careers_url": "https://example.com", "ats": "generic"}]), encoding="utf-8")
                self.assertTrue(doctor.registry(root))
                path.write_text(json.dumps([{"name": "Acme", "careers_url": "https://careers.acme.test", "ats": "generic"}]), encoding="utf-8")
                self.assertFalse(doctor.registry(root))

    def test_registry_cannot_point_to_another_candidates_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "candidate-1"
            root.mkdir()
            other = base / "candidate-2.json"
            other.write_text('[]', encoding="utf-8")
            with patch.dict("os.environ", {"COMPANY_PAGES_REGISTRY": str(other)}):
                self.assertTrue(doctor.registry(root))
            (root / "company_pages.json").symlink_to(other)
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(doctor.registry(root))

    def test_private_symlink_isolation_even_when_leaf_does_not_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "candidate-1"
            other = base / "candidate-2"
            (root / "documents").mkdir(parents=True)
            (other / "profile").mkdir(parents=True)
            (root / "documents" / "profile").symlink_to(other / "profile", target_is_directory=True)
            self.assertTrue(doctor.private_paths(root))
            (root / "documents" / "profile").unlink()
            (root / "documents" / "profile").mkdir()
            (root / "documents" / "profile" / "candidate.md").symlink_to(other / "profile" / "facts.md")
            self.assertTrue(doctor.private_paths(root))
            (root / "documents" / "profile" / "candidate.md").unlink()
            self.assertFalse(doctor.private_paths(root))

    def test_pdf_and_font_checks_only_warn_when_unavailable(self):
        output = io.StringIO()
        with patch("tools.doctor.importlib.util.find_spec", return_value=None), \
                patch("tools.doctor.shutil.which", return_value=None), \
                contextlib.redirect_stdout(output):
            doctor.optional_dependencies()
        self.assertIn("WARN PDF text extraction", output.getvalue())
        self.assertIn("WARN Chinese fonts", output.getvalue())


class RuntimeIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "candidate-1"
        self.other = self.base / "candidate-2"
        for root in (self.root, self.other):
            skill = root / "skills/job-search/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: job-search\n---\n", encoding="utf-8")
        # Match OpenClaw's actual shapes: list includes workspaceDir but omits
        # filePath; info returns the complete individual skill object.
        self.skill = {"name": "job-search", "eligible": True, "disabled": False,
                      "blockedByAllowlist": False, "blockedByAgentFilter": False}
        self.inventory = {"workspaceDir": str(self.root), "skills": [dict(self.skill)]}
        self.detail = {**self.skill, "filePath": str(self.root / "skills/job-search/SKILL.md")}

    def check_runtime(self, inventory=DEFAULT, detail=DEFAULT, error=None):
        responses = [Mock(stdout=json.dumps(self.inventory if inventory is DEFAULT else inventory)),
                     Mock(stdout=json.dumps(self.detail if detail is DEFAULT else detail))]
        output = io.StringIO()
        with patch("tools.doctor.shutil.which", return_value="/bin/openclaw"), \
                patch("tools.doctor.subprocess.run", side_effect=error or responses) as run, \
                contextlib.redirect_stdout(output):
            failed = doctor.runtime_skill("candidate-1", self.root)
        return failed, output.getvalue(), run.call_args_list

    def test_matching_workspace_and_skill_pass_with_only_read_only_commands(self):
        failed, output, calls = self.check_runtime()
        self.assertFalse(failed, output)
        self.assertEqual([call.args[0] for call in calls], [
            ["openclaw", "skills", "list", "--agent", "candidate-1", "--json"],
            ["openclaw", "skills", "info", "job-search", "--agent", "candidate-1", "--json"],
        ])
        self.assertTrue(all(call.kwargs["cwd"] == self.root for call in calls))

    def test_other_candidate_workspace_fails_even_with_same_named_skill(self):
        self.inventory["workspaceDir"] = str(self.other)
        failed, output, calls = self.check_runtime()
        self.assertTrue(failed)
        self.assertIn("workspace does not match", output)
        self.assertEqual(len(calls), 1)

    def test_other_candidate_skill_fails_even_when_workspace_matches(self):
        self.detail["filePath"] = str(self.other / "skills/job-search/SKILL.md")
        failed, output, _ = self.check_runtime()
        self.assertTrue(failed)
        self.assertIn("check skill overrides", output)

    def test_workspace_alias_resolves_to_same_checkout(self):
        alias = self.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.inventory["workspaceDir"] = str(alias)
        self.detail["filePath"] = str(alias / "skills/job-search/SKILL.md")
        self.assertFalse(self.check_runtime()[0])

    def test_local_skill_symlink_cannot_escape_checkout(self):
        local = self.root / "skills/job-search/SKILL.md"
        local.unlink()
        local.symlink_to(self.other / "skills/job-search/SKILL.md")
        self.assertTrue(self.check_runtime()[0])

    def test_missing_invalid_or_relative_workspace_does_not_pass(self):
        for payload in ([], None, "invalid", {}, {"skills": [self.skill]},
                        {**self.inventory, "workspaceDir": "candidate-1"},
                        {**self.inventory, "workspaceDir": 123}):
            with self.subTest(payload=payload):
                self.assertTrue(self.check_runtime(inventory=payload)[0])

    def test_missing_duplicate_or_unavailable_skill_fails(self):
        for entries in ([], [self.skill, self.skill], "invalid",
                        [{**self.skill, "eligible": False}],
                        [{"name": "job-search"}]):
            with self.subTest(entries=entries):
                self.assertTrue(self.check_runtime(inventory={**self.inventory, "skills": entries})[0])

    def test_readiness_flags_are_checked_in_inventory_and_detail(self):
        for flag, value in (("disabled", True), ("enabled", False),
                            ("blockedByAllowlist", True), ("blockedByAgentFilter", True),
                            ("eligible", False)):
            with self.subTest(flag=flag):
                self.assertTrue(self.check_runtime(inventory={
                    **self.inventory, "skills": [{**self.skill, flag: value}],
                })[0])
                self.assertTrue(self.check_runtime(detail={**self.detail, flag: value})[0])

    def test_missing_invalid_or_relative_skill_path_does_not_pass(self):
        for path in (None, "", "skills/job-search/SKILL.md", 123, str(self.base / "missing")):
            with self.subTest(path=path):
                self.assertTrue(self.check_runtime(detail={**self.detail, "filePath": path})[0])
        for payload in (None, [], "invalid", {}, {**self.detail, "name": "different"}):
            with self.subTest(payload=payload):
                self.assertTrue(self.check_runtime(detail=payload)[0])

    def test_command_failure_does_not_print_private_cli_output(self):
        error = subprocess.CalledProcessError(1, ["openclaw"], output="PRIVATE", stderr="PRIVATE")
        failed, output, _ = self.check_runtime(error=error)
        self.assertTrue(failed)
        self.assertNotIn("PRIVATE", output)


if __name__ == "__main__":
    unittest.main()
