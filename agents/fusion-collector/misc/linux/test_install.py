"""Run the real installer script against a disposable filesystem and command seam."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class InstallServiceFailureTest(unittest.TestCase):
    def test_service_start_failure_is_not_success(self):
        source = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = root / "opt/fusion-collectors"
            install.mkdir(parents=True)
            (root / "etc/systemd/system").mkdir(parents=True)
            commands = root / "commands"
            commands.mkdir()
            for name, body in {"id": "echo 0", "systemctl": 'echo "$1" >> "$INSTALL_TEST_CALLS"\n[ "$1" != enable ]'}.items():
                target = commands / name
                target.write_text("#!/bin/sh\n" + body + "\n")
                target.chmod(0o755)
            script = (source / "install.sh").read_text().replace("/opt/fusion-collectors", str(install)).replace("/etc/systemd/system", str(root / "etc/systemd/system"))
            (install / "install.sh").write_text(script)
            (install / "sidecar.yml").write_text((source / "sidecar.yml").read_text())
            (install / "bk-sidecar.service").write_text("[Service]\n")
            result = subprocess.run(["bash", "install.sh", "https://example.test", "test-token", "1", "2", "host", "node"], cwd=install,
                env={**os.environ, "BK_LITE_CONFIG_PREPARED": "1", "INSTALL_TEST_CALLS": str(root / "calls"), "PATH": str(commands) + ":" + os.environ["PATH"]}, capture_output=True, text=True)
            self.assertIn("enable", (root / "calls").read_text())
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("安装完成", result.stdout)



class TLSCompatibilityTest(unittest.TestCase):
    def test_legacy_template_keeps_existing_behavior(self):
        self.assertIn("tls_skip_verify: true", (Path(__file__).parent / "sidecar.yml").read_text())


if __name__ == "__main__":
    unittest.main()
