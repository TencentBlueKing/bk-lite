"""执行真实 CI 阶段，验证默认用户与显式 UID 0 等价、非 root 和入口不得变化。"""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Log4jWorkflowTests(unittest.TestCase):
    def test_build_preserves_effective_user_and_startup(self):
        workflow = (ROOT / ".github/workflows/brotli-images.yml").read_text()
        section = workflow.split("  log4j-images:\n", 1)[1]
        command = textwrap.dedent(section.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as tmp:
            docker = Path(tmp) / "docker"
            docker.write_text('''#!/bin/sh
case "$1" in
    pull|build) exit 0 ;;
    image)
        case "$4" in
            *Config.User*)
                case "$5" in
                    base-image) printf '%s' "$BEFORE_USER" ;;
                    *) printf '%s' "$AFTER_USER" ;;
                esac ;;
            *)
                case "$5" in
                    base-image) printf '%s' "$BEFORE_STARTUP" ;;
                    *) printf '%s' "$AFTER_STARTUP" ;;
                esac ;;
        esac ;;
    *) exit 99 ;;
esac
''')
            docker.chmod(0o755)
            startup = '["/entrypoint"] ["run"]'
            cases = (("", "0", startup, 0), ("", "", startup, 0),
                     ("1000", "1000", startup, 0), ("1000", "0", startup, 1),
                     ("", "1000", startup, 1), ("1000", "1000", '["changed"] []', 1))
            for before, after, final_startup, expected in cases:
                with self.subTest(before=before, after=after, startup=final_startup):
                    result = subprocess.run(
                        ["sh", "-eu", "-c", command], capture_output=True, text=True, timeout=10,
                        env={"PATH": tmp + os.pathsep + os.environ["PATH"],
                             "PRODUCT": "elasticsearch", "BASE_IMAGE": "base-image",
                             "BEFORE_USER": before, "AFTER_USER": after,
                             "BEFORE_STARTUP": startup, "AFTER_STARTUP": final_startup},
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
