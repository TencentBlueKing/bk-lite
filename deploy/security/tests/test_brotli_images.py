"""验证实际发行层的补丁基线、失败传播及 Node 包清单一致性。"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PROFILES = {
    "server/support-files/release/Dockerfile.base": ("debian", "13", "1.1.0-2+deb13u1", "1.1.0-2+b7"),
    "server/support-files/release/Dockerfile": ("debian", "12", "1.0.9-2+deb12u1", "1.0.9-2+b6"),
    "agents/stargazer/support-files/docker/Dockerfile": ("debian", "13", "1.1.0-2+deb13u1", "1.1.0-2+b7"),
    "agents/webhookd/Dockerfile": ("debian", "13", "1.1.0-2+deb13u1", "1.1.0-2+b7"),
    "agents/fusion-collector/agent/Dockerfile": ("ubuntu", "24.04", "1.1.0-2ubuntu0.1", "1.1.0-2build2"),
    "agents/fusion-collector/telegraf/Dockerfile": ("ubuntu", "24.04", "1.1.0-2ubuntu0.1", "1.1.0-2build2"),
    "deploy/security/Dockerfile.system": ("ubuntu", "20.04", "1.0.7-6ubuntu0.1+esm1", "1.0.7-6ubuntu0.1"),
    "deploy/security/Dockerfile.falkordb": ("debian", "12", "1.0.9-2+deb12u1", "1.0.9-2+b6"),
}


def layers(path):
    return [line[4:] for line in (ROOT / path).read_text().replace("\\\n", " ").splitlines() if line.startswith("RUN ")]


def security_layer(path):
    found = [line for line in layers(path) if "dpkg --compare-versions" in line]
    if len(found) != 1:
        raise AssertionError(f"{path} 缺少唯一的 Brotli 补丁校验层")
    return found[0]


def fixture_command(directory, command, body):
    executable = directory / command
    executable.write_text("#!/bin/sh\n" + body + "\n")
    executable.chmod(0o755)


def run_layer(path, distribution, release, installed, *, comparison=0, apt_status=0, real_dpkg=False,
              node_package="24.22.1-1nodesource1", node_runtime="v24.22.1", node_status="ii "):
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        fixture_command(directory, "apt-get", 'exit "$APT_STATUS"')
        fixture_command(directory, "dpkg-query", '''case "$*" in
            *Status-Abbrev*) printf "%s" "$NODE_STATUS" ;;
            *nodejs*) printf "%s" "$NODE_PACKAGE" ;;
            *) printf "%s" "$INSTALLED" ;;
        esac''')
        fixture_command(directory, "node", 'printf "%s\\n" "$NODE_RUNTIME"')
        comparator = 'exec "$REAL_DPKG" "$@"' if real_dpkg else 'exit "$COMPARISON_STATUS"'
        fixture_command(directory, "dpkg", comparator)
        fixture_command(directory, "rm", 'touch "$CLEANUP_MARKER"')
        marker = directory / "cleaned"
        layer = security_layer(path).replace(
            ". /etc/os-release", f"{{ ID={distribution}; VERSION_ID={release}; }}"
        )
        result = subprocess.run(
            ["sh", "-c", layer],
            env={
                **os.environ,
                "PATH": str(directory) + os.pathsep + os.environ["PATH"],
                "COMPARISON_STATUS": str(comparison),
                "APT_STATUS": str(apt_status),
                "CLEANUP_MARKER": str(marker),
                "INSTALLED": installed,
                "REAL_DPKG": shutil.which("dpkg") or "",
                "NODE_PACKAGE": node_package,
                "NODE_RUNTIME": node_runtime,
                "NODE_STATUS": node_status,
            },
            capture_output=True, text=True, timeout=10,
        )
        return result, marker.exists()


class BrotliImageTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("dpkg"), "真实 Node 包版本比较需在 Linux/dpkg 环境运行")
    def test_node_package_inventory_and_runtime_must_agree(self):
        cases = (
            ("24.14.0-1nodesource1", "v24.22.1", "ii ", 1),
            ("24.22.1-1nodesource1", "v24.14.0", "ii ", 1),
            ("24.22.2-1nodesource1", "v24.22.1", "ii ", 1),
            ("24.22.1-1nodesource1", "v24.22.1", "ii ", 0),
            ("24.22.2-1nodesource1", "v24.22.2", "ii ", 0),
            ("25.0.0-1nodesource1", "v25.0.0", "ii ", 1),
            ("24.22.1-1nodesource1", "v24.22.1", "un ", 1),
        )
        for package, runtime, status, expected in cases:
            with self.subTest(package=package, runtime=runtime, status=status):
                result, cleaned = run_layer(
                    "deploy/security/Dockerfile.falkordb", "debian", "12", "1.0.9-2+deb12u1",
                    real_dpkg=True, node_package=package, node_runtime=runtime, node_status=status,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(cleaned, expected == 0)

    def test_all_images_upgrade_and_check_before_cleanup(self):
        for path, (_, _, minimum, _) in PROFILES.items():
            with self.subTest(image=path):
                layer = security_layer(path)
                self.assertIn(minimum, layer)
                self.assertRegex(layer, r"apt-get install[^&]*libbrotli1")
                self.assertLess(layer.index("apt-get update"), layer.index("apt-get install"))
                self.assertLess(layer.index("apt-get install"), layer.index("dpkg --compare-versions"))
                self.assertLess(layer.index("dpkg --compare-versions"), layer.index("rm -rf"))

    def test_repository_and_package_check_failures_stop_build(self):
        for path, (distribution, release, minimum, _) in PROFILES.items():
            for comparison, apt_status, expected in ((0, 0, 0), (1, 0, 1), (0, 100, 100)):
                with self.subTest(image=path, comparison=comparison, apt=apt_status):
                    result, cleaned = run_layer(
                        path, distribution, release, minimum, comparison=comparison, apt_status=apt_status
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual(cleaned, expected == 0)

    def test_unknown_distribution_is_rejected(self):
        for path in ("server/support-files/release/Dockerfile", "deploy/security/Dockerfile.system",
                     "deploy/security/Dockerfile.falkordb"):
            with self.subTest(image=path):
                result, cleaned = run_layer(path, "debian", "99", "99.0")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("未验证", result.stderr)
                self.assertFalse(cleaned)

    @unittest.skipUnless(shutil.which("dpkg"), "真实发行版版本比较需在 Linux/dpkg 环境运行")
    def test_real_dpkg_accepts_backports_and_rejects_unpatched_binary_rebuilds(self):
        for path, (distribution, release, minimum, old) in PROFILES.items():
            for installed, expected in ((old, 1), (minimum, 0), (minimum + "+b1", 0)):
                with self.subTest(image=path, installed=installed):
                    result, cleaned = run_layer(path, distribution, release, installed, real_dpkg=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual(cleaned, expected == 0)

    @unittest.skipUnless(shutil.which("dpkg"), "真实发行版版本比较需在 Linux/dpkg 环境运行")
    def test_external_image_distribution_matrix(self):
        profiles = (
            ("debian", "12", "1.0.9-2+deb12u1", "1.0.9-2+b6"),
            ("debian", "13", "1.1.0-2+deb13u1", "1.1.0-2+b7"),
            ("ubuntu", "20.04", "1.0.7-6ubuntu0.1+esm1", "1.0.7-6ubuntu0.1"),
            ("ubuntu", "22.04", "1.0.9-2ubuntu0.1", "1.0.9-2build6"),
            ("ubuntu", "24.04", "1.1.0-2ubuntu0.1", "1.1.0-2build2"),
        )
        for distribution, release, minimum, old in profiles:
            for installed, expected in ((old, 1), (minimum, 0)):
                with self.subTest(distribution=distribution, release=release, installed=installed):
                    result, _ = run_layer(
                        "deploy/security/Dockerfile.system", distribution, release, installed, real_dpkg=True
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)

    def test_external_images_require_explicit_runtime_user(self):
        for path in ("deploy/security/Dockerfile.system", "deploy/security/Dockerfile.falkordb"):
            with self.subTest(image=path):
                text = (ROOT / path).read_text()
                self.assertIn("USER ${RUNTIME_USER}", text)
                self.assertNotRegex(text, r"ARG RUNTIME_USER=")
                self.assertTrue(text.strip().endswith("USER ${RUNTIME_USER}"))
                self.assertNotRegex(text, r"(?m)^(ENTRYPOINT|CMD) ")

    def test_node_overlay_updates_the_managed_package(self):
        text = (ROOT / "deploy/security/Dockerfile.falkordb").read_text()
        self.assertRegex(security_layer("deploy/security/Dockerfile.falkordb"), r"apt-get install[^&]*\bnodejs\b")
        self.assertNotIn("COPY --from=", text)


if __name__ == "__main__":
    unittest.main()
