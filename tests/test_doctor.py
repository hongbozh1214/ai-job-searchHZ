"""Behavioral checks for the read-only workspace doctor."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import doctor


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

    def test_agent_runtime_inventory_must_include_available_job_search(self):
        with patch("tools.doctor.shutil.which", return_value="/bin/openclaw"), patch("tools.doctor.subprocess.run") as run:
            run.return_value.stdout = json.dumps({"skills": [{"name": "job-search", "eligible": True}]})
            self.assertFalse(doctor.runtime_skill("candidate-2", Path("/tmp")))
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ["openclaw", "skills", "list", "--agent", "candidate-2", "--json"])
            run.return_value.stdout = json.dumps({"skills": [{"name": "job-search", "eligible": False}]})
            self.assertTrue(doctor.runtime_skill("candidate-2", Path("/tmp")))
            run.return_value.stdout = json.dumps({"skills": []})
            self.assertTrue(doctor.runtime_skill("candidate-2", Path("/tmp")))


if __name__ == "__main__":
    unittest.main()
