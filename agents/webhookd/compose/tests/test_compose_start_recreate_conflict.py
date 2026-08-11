import re
import unittest
from pathlib import Path


START_SCRIPT = Path(__file__).resolve().parents[1] / "start.sh"


class ComposeStartRecreateConflictTest(unittest.TestCase):
    def test_start_cleans_stopped_project_containers_before_up(self):
        script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("cleanup_stopped_project_containers", script)
        self.assertRegex(
            script,
            re.compile(r'docker ps -aq .*label=com\.docker\.compose\.project=\$\{ID\}', re.DOTALL),
        )
        self.assertIn("for status in created exited dead", script)
        self.assertRegex(script, r'docker rm \$containers')

    def test_start_removes_orphans_and_retries_name_conflict_once(self):
        script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertRegex(script, r'\$DC up -d --remove-orphans')
        self.assertRegex(script, re.compile(r"container name.*already in use", re.IGNORECASE | re.DOTALL))
        self.assertIn("Retrying after cleaning stopped compose containers", script)


if __name__ == "__main__":
    unittest.main()
