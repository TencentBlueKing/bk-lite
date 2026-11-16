"""Image/config convergence must not create extra credential files."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

Path = type(Path())
SECRET = "test-only-minio-sentinel"


class DeployTest(unittest.TestCase):
    def deploy(self, requested_images=("sha256:new",), minio_exists=True, fail=False):
        self.calls = []
        self.environments = []
        self.files = {}
        self.output = io.StringIO()
        containers = {}
        network = "env-install-net-20261113"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "evidence").mkdir()
            (root / "config/ui-server.env").write_text("EXAMPLE=isolated\n")
            (root / "config/query-minio.json").write_text(json.dumps({"user": "isolatedqueryminio", "password": SECRET}))

            def execute(args, **kwargs):
                args = list(args)
                self.calls.append(args)
                self.environments.append(kwargs.get("env", {}))
                data = ""
                if args[:3] == ["docker", "image", "inspect"]:
                    if requested_image is None:
                        raise subprocess.CalledProcessError(1, args)
                    data = json.dumps([{"Id": requested_image}])
                elif args[:2] == ["docker", "inspect"]:
                    if args[2] == "env-query-minio-20261115" and not minio_exists:
                        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
                    data = json.dumps([{"Id": "old123", "State": {"Running": True},
                        "NetworkSettings": {"Networks": {network: {"IPAddress": "192.0.2.1"}}},
                        "Config": {"Labels": {"query-spec": containers.get(args[2], "old-spec")}}}])
                elif args[:2] == ["docker", "run"]:
                    if fail:
                        raise subprocess.CalledProcessError(1, args)
                    if "--label" in args:
                        containers[args[args.index("--name") + 1]] = args[args.index("--label") + 1].split("=", 1)[1]
                return subprocess.CompletedProcess(args, 0, stdout=data, stderr="")

            def remap(value):
                return root if str(value) == "/opt/bklite-environment-test-20261113" else Path(value)

            try:
                with patch("pathlib.Path", side_effect=remap), patch("subprocess.run", side_effect=execute), patch.dict("os.environ", {"ENV_QUERY_SERVER_IMAGE": "bklite/server:test-rebuilt"}), contextlib.redirect_stdout(self.output):
                    for requested_image in requested_images:
                        runpy.run_path(str(Path(__file__).with_name("deploy-query.py")))
            finally:
                self.files = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        return self.calls

    def test_rebuilt_tag_replaces_five_isolated_services(self):
        calls = self.deploy(("sha256:old", "sha256:new"))
        stops = [call[2] for call in calls if call[:2] == ["docker", "stop"]]
        self.assertEqual(len(stops), 10)
        self.assertTrue(all(name.startswith("env-") for name in stops))
        runs = [call for call in calls if call[:3] == ["docker", "run", "-d"]]
        self.assertEqual(sum("sha256:new" in call for call in runs), 5)

    def test_same_image_and_config_do_not_restart(self):
        calls = self.deploy(("sha256:new", "sha256:new"))
        self.assertEqual(sum(call[:2] == ["docker", "stop"] for call in calls), 5)

    def test_missing_image_fails_before_any_container_mutation(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.deploy((None,))
        self.assertFalse(any(call[:2] in (["docker", "run"], ["docker", "stop"], ["docker", "rename"]) for call in self.calls))

    def test_credentials_only_pass_in_child_environment(self):
        self.deploy(minio_exists=False)
        for filename in ("config/query-minio.env", "config/query-server.env"):
            self.assertNotIn(filename, self.files)
        self.assertNotIn(SECRET, str(self.calls) + self.output.getvalue())
        for filename, content in self.files.items():
            if filename != "config/query-minio.json":
                self.assertNotIn(SECRET.encode(), content)
        runs = [(args, env) for args, env in zip(self.calls, self.environments) if args[:2] == ["docker", "run"]]
        minio = next((args, env) for args, env in runs if "env-query-minio-20261115" in args)
        self.assertIn("MINIO_ROOT_PASSWORD", minio[0])
        self.assertEqual(minio[1]["MINIO_ROOT_PASSWORD"], SECRET)
        servers = [(args, env) for args, env in runs if "sha256:new" in args]
        self.assertEqual(len(servers), 7)
        for args, env in servers:
            self.assertIn("MINIO_SECRET_KEY", args)
            self.assertEqual(env["MINIO_SECRET_KEY"], SECRET)
            self.assertTrue(args[args.index("--env-file") + 1].endswith("/config/ui-server.env"))

    def test_failed_child_does_not_expose_credentials(self):
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.deploy(minio_exists=False, fail=True)
        self.assertNotIn(SECRET, str(error.exception) + self.output.getvalue())
        self.assertNotIn("config/query-minio.env", self.files)
        self.assertNotIn("config/query-server.env", self.files)


if __name__ == "__main__":
    unittest.main()
