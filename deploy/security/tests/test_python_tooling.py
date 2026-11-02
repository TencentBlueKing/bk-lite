import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "upgrade_ubuntu_python.sh"


class PythonToolingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("dpkg"), "需要 Linux 的真实 dpkg 版本比较")
    def test_installed_packages_are_upgraded_or_build_is_rejected(self):
        for scenario in ("safe", "old-pip", "old-wheel", "missing", "apt-failure", "other-os"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = {
                    "apt-get": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TRACE"\nexit "$APT_STATUS"\n',
                    "dpkg-query": '''#!/bin/sh
case "$*" in
 *Status-Abbrev*) [ "$PRESENT" = 1 ] || exit 1; printf 'ii ' ;;
 *python3-pip*) printf '%s' "$PIP_VERSION" ;;
 *) printf '%s' "$WHEEL_VERSION" ;;
esac
''',
                    "rm": '#!/bin/sh\ntouch "$CLEANED"\n',
                }
                for name, body in fixture.items():
                    path = root / name
                    path.write_text(body)
                    path.chmod(0o755)
                distribution = "debian" if scenario == "other-os" else "ubuntu"
                script = SCRIPT.read_text().replace(". /etc/os-release", f"ID={distribution}; VERSION_ID=24.04")
                env = {"PATH": str(root) + ":/usr/bin:/bin", "PRESENT": "0" if scenario == "missing" else "1",
                       "APT_STATUS": "100" if scenario == "apt-failure" else "0", "TRACE": str(root / "trace"),
                       "CLEANED": str(root / "cleaned"),
                       "PIP_VERSION": "24.0+dfsg-1ubuntu1.3" if scenario == "old-pip" else "24.0+dfsg-1ubuntu1.3+esm1",
                       "WHEEL_VERSION": "0.42.0-2" if scenario == "old-wheel" else "0.42.0-2ubuntu0.1~esm1"}
                result = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, timeout=5)
                expected = 100 if scenario == "apt-failure" else 1 if scenario.startswith("old-") else 0
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual((root / "cleaned").exists(), scenario == "safe")
                if scenario in {"missing", "other-os"}:
                    self.assertFalse((root / "trace").exists())
                elif scenario == "safe":
                    commands = (root / "trace").read_text()
                    self.assertIn("--only-upgrade", commands)
                    self.assertIn("python3-pip-whl", commands)
                    self.assertIn("python3-wheel", commands)


if __name__ == "__main__":
    unittest.main()
