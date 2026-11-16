"""Business deployment passes credentials to the child, without env-file copies."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

import reconcile


class ReconcileCredentialsTest(unittest.TestCase):
    def run_reconcile(self, mode="--apply", fail_compose=False):
        self.calls = []
        self.output = io.StringIO()
        self.error = None
        self.secret = "unit-test-only-nats-password-sentinel"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "certs").mkdir()
            (root / "certs/ca.crt").write_text("public test certificate")
            permissions = {
                "publish": {"allow": ["existing.download"]},
                "subscribe": {"allow": ["_INBOX.>"]},
            }
            config = {
                "authorization": {
                    "users": [
                        {"user": "test-admin", "password": self.secret},
                        {
                            "user": "test-auto-region-executor",
                            "password": "unit-test-only-executor-password",
                            "permissions": permissions,
                        },
                    ]
                }
            }
            (root / "config/nats.conf").touch()
            config_text = json.dumps(config)
            read_text, write_text = Path.read_text, Path.write_text

            def read_fixture(path, *args, **kwargs):
                if path == root / "config/nats.conf":
                    return config_text
                return read_text(path, *args, **kwargs)

            def update_fixture(path, content, *args, **kwargs):
                nonlocal config_text
                if path == root / "config/nats.conf":
                    config_text = content
                    return len(content)
                return write_text(path, content, *args, **kwargs)
            original_files = {p for p in root.rglob("*") if p.is_file()}
            images = json.loads(Path(reconcile.__file__).with_name("images.json").read_text())

            def execute(args, **kwargs):
                args = list(args)
                self.calls.append((args, kwargs))
                output = ""
                if args[:2] == ["docker", "inspect"]:
                    self.assertEqual(args[2], reconcile.API)
                    output = json.dumps([{"NetworkSettings": {"Networks": {reconcile.NETWORK: {"IPAddress": "192.0.2.1"}}}}])
                elif args[:3] == ["docker", "image", "inspect"]:
                    output = json.dumps([{"Id": images[args[3]]}])
                elif args[:3] == ["docker", "exec", reconcile.API] and "-c" in args:
                    output = json.dumps(["node-c", "node-d"])
                elif args[:2] == ["docker", "compose"] and fail_compose:
                    raise subprocess.CalledProcessError(1, args, output=self.secret, stderr=self.secret)
                return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

            with patch.object(Path, "read_text", read_fixture), patch.object(Path, "write_text", update_fixture), patch.object(reconcile, "ROOT", root), patch.object(sys, "argv", ["reconcile.py", mode]), patch("subprocess.run", side_effect=execute), contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.output):
                try:
                    reconcile.main()
                except subprocess.CalledProcessError as error:
                    self.error = error
                    self.trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            self.generated = {
                str(p.relative_to(root)): p.read_text()
                for p in root.rglob("*")
                if p.is_file() and p not in original_files
            }
            self.current_config = json.loads(config_text)
            self.original_permissions = permissions

    def test_apply_has_no_credential_copy_and_compose_receives_environment(self):
        self.run_reconcile()
        self.assertIsNone(self.error)
        self.assertNotIn("business-20261115/pipeline.env", self.generated)
        self.assertTrue(all(self.secret not in content for content in self.generated.values()))
        self.assertNotIn(self.secret, self.output.getvalue())
        self.assertNotIn(self.secret, repr([args for args, _ in self.calls]))
        compose = [(args, kwargs) for args, kwargs in self.calls if args[:2] == ["docker", "compose"]]
        self.assertEqual(len(compose), 1)
        args, kwargs = compose[0]
        self.assertEqual(Path(args[args.index("-f") + 1]), Path(reconcile.__file__).with_name("compose.yaml"))
        self.assertEqual(args[-4:], ["up", "-d", "--pull", "never"])
        self.assertEqual(kwargs["env"]["NATS_ADMIN_PASSWORD"], self.secret)
        self.assertEqual(kwargs["env"]["APM_NATS_URL"], "tls://test-admin:" + self.secret + "@env-install-nats:4222")
        self.assertIn("name: env-business-20261115", Path(reconcile.__file__).with_name("compose.yaml").read_text())
        backup = json.loads(self.generated["config/nats.permissions-pre-business-20261115.json"])
        self.assertEqual(backup, {"account": "test-auto-region-executor", "permissions": self.original_permissions})
        self.assertEqual(self.current_config["authorization"]["users"][0]["password"], self.secret)

    def test_plan_does_not_write_or_start_compose(self):
        self.run_reconcile(mode="--plan")
        self.assertEqual(self.generated, {})
        self.assertFalse(any(args[:2] == ["docker", "compose"] for args, _ in self.calls))
        self.assertNotIn(self.secret, self.output.getvalue())
        self.assertNotIn(self.secret, repr([args for args, _ in self.calls]))

    def test_compose_failure_does_not_expose_credentials(self):
        self.run_reconcile(fail_compose=True)
        self.assertIsInstance(self.error, subprocess.CalledProcessError)
        self.assertNotIn(self.secret, self.output.getvalue())
        self.assertNotIn(self.secret, self.trace)
        self.assertNotIn(self.secret, repr(self.error.cmd))
        self.assertNotIn("__BUSINESS_DEPENDENCIES_RECONCILED__", self.output.getvalue())
        self.assertTrue(all(self.secret not in content for content in self.generated.values()))


if __name__ == "__main__":
    unittest.main()
