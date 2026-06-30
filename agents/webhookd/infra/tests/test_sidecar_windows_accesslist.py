import re
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "sidecar.sh"


class SidecarWindowsAccessListTest(unittest.TestCase):
    def test_windows_install_script_allows_nested_collector_binaries(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        match = re.search(
            r'collector_binaries_accesslist:\n(?P<entries>(?:- ".*"\n)+)',
            script,
        )

        self.assertIsNotNone(match)
        entries = match.group("entries").splitlines()
        self.assertIn(r'- "${INSTALL_PATH}bin\*"', entries)
        self.assertIn(r'- "${INSTALL_PATH}bin\*\*"', entries)


if __name__ == "__main__":
    unittest.main()
