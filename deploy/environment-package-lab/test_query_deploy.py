"""Rebuilding an isolated image must replace old containers, then converge."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

Path = type(Path())


class DeployTest(unittest.TestCase):
    def deploy(self, previous_image, requested_image="sha256:new"):
        calls = []
        self.last_calls = calls
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "evidence").mkdir()
            (root / "config/ui-server.env").write_text("EXAMPLE=isolated\n")
            network = "env-install-net-20261113"
            def execute(args, **kwargs):
                args = list(args)
                calls.append(args)
                data = ""
                if args[:3] == ["docker", "image", "inspect"]:
                    if requested_image is None:
                        raise subprocess.CalledProcessError(1, args)
                    data = json.dumps([{"Id": requested_image}])
                elif args[:2] == ["docker", "inspect"]:
                    content_path = root / "config/query-server.env"
                    content = content_path.read_text() if content_path.exists() else ""
                    data = json.dumps([{"Id": "old123", "Image": previous_image,
                        "State": {"Running": True}, "NetworkSettings": {"Networks": {network: {"IPAddress": "192.0.2.1"}}},
                        "Config": {"Labels": {"query-spec": hashlib.sha256((content + previous_image).encode()).hexdigest()}}}])
                return subprocess.CompletedProcess(args, 0, stdout=data, stderr="")
            def remap(value):
                return root if str(value) == "/opt/bklite-environment-test-20261113" else Path(value)
            with patch("pathlib.Path", side_effect=remap), patch("subprocess.run", side_effect=execute), patch.dict("os.environ", {"ENV_QUERY_SERVER_IMAGE": "bklite/server:test-rebuilt"}):
                runpy.run_path(str(Path(__file__).with_name("deploy-query.py")))
        return calls

    def test_rebuilt_tag_replaces_five_isolated_services(self):
        calls = self.deploy("sha256:old")
        stops = [call[2] for call in calls if call[:2] == ["docker", "stop"]]
        self.assertEqual(len(stops), 5)
        self.assertTrue(all(name.startswith("env-") for name in stops))
        runs = [call for call in calls if call[:3] == ["docker", "run", "-d"]]
        self.assertEqual(len(runs), 5)
        self.assertTrue(all("sha256:new" in call for call in runs))

    def test_same_image_and_config_do_not_restart(self):
        calls = self.deploy("sha256:new")
        self.assertFalse(any(call[:2] == ["docker", "stop"] for call in calls))

    def test_missing_image_fails_before_any_container_mutation(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.deploy("sha256:old", None)
        self.assertFalse(any(call[:2] in (["docker", "run"], ["docker", "stop"], ["docker", "rename"]) for call in self.last_calls))


if __name__ == "__main__":
    unittest.main()
