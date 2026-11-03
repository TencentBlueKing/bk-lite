"""覆盖漏部署、旧副本、候选门禁失败与清单保留行为。"""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("brotli_release", Path(__file__).parents[1] / "brotli_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
DIGEST = "registry.example/falkordb@sha256:" + "a" * 64
SERVICES = {"falkordb": {"image": DIGEST, "profile": "node-system"}}


class ReleaseTests(unittest.TestCase):
    def test_manifest_rejects_tags_empty_and_invalid_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            for services in ({}, {"falkordb": {"image": "image:latest", "profile": "node"}},
                             {"falkordb": {"image": DIGEST, "profile": "skip"}}):
                path.write_text(json.dumps({"services": services}))
                with self.assertRaises(ValueError):
                    release.load_manifest(path)
            path.write_text(json.dumps({"services": SERVICES}))
            self.assertEqual(release.load_manifest(path), SERVICES)

    def test_failed_gate_writes_nothing_and_existing_lock_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "override.json"
            with patch.object(release, "check", side_effect=ValueError("旧 Node")):
                with self.assertRaises(ValueError):
                    release.prepare(SERVICES, path)
            self.assertFalse(path.exists())
            with patch.object(release, "check"):
                release.prepare(SERVICES, path)
                with self.assertRaises(ValueError):
                    release.prepare(SERVICES, path)
            self.assertEqual(json.loads(path.read_text()), {"services": {"falkordb": {"image": DIGEST}}})

    def test_verify_all_replicas_rejects_old_stopped_or_missing_container(self):
        for ids, states, success in (("one\ntwo", ["sha256:new true"] * 2, True),
                                    ("one\ntwo", ["sha256:new true", "sha256:old true"], False),
                                    ("one", ["sha256:new false"], False), ("", [], False)):
            with self.subTest(ids=ids, states=states):
                with patch.object(release, "run", side_effect=["sha256:new", ids, *states]) as run:
                    with patch.object(release, "check") as check:
                        if success:
                            release.verify(SERVICES, "compose", ["base.yaml", "patch.json"], ["release.env"], ["full"])
                            self.assertEqual(check.call_count, 2)
                        else:
                            with self.assertRaises(ValueError):
                                release.verify(SERVICES, "compose", ["base.yaml", "patch.json"], ["release.env"], ["full"])
                        self.assertIn("--all", run.call_args_list[1].args[0])
                        self.assertIn("--project-name", run.call_args_list[1].args[0])
                        self.assertIn("--env-file", run.call_args_list[1].args[0])
                        self.assertIn("--profile", run.call_args_list[1].args[0])

    def test_image_checks_are_isolated_and_do_not_call_application_startup(self):
        with patch.object(release, "run", return_value="ok") as run:
            release.check("node-system", image=DIGEST)
            self.assertEqual(run.call_count, 4)
            for call in run.call_args_list[::2]:
                command = call.args[0]
                self.assertIn("--interactive", command)
                self.assertIn("--network=none", command)
                self.assertIn("--pull=never", command)
                self.assertIn("--read-only", command)
                self.assertIn("--entrypoint", command)
                self.assertNotIn("--privileged", command)


    def test_timeout_cleans_only_its_own_candidate_container(self):
        with patch.object(release, "run", side_effect=[subprocess.TimeoutExpired("docker", 60), ""]) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                release.check("system", image=DIGEST)
            start = run.call_args_list[0].args[0]
            name = start[start.index("--name") + 1]
            self.assertTrue(name.startswith("bklite-brotli-check-"))
            self.assertEqual(run.call_args_list[1].args[0], ["docker", "rm", "--force", name])

    def test_build_rejects_implicit_latest_before_docker(self):
        script = Path(__file__).parents[1] / "build_falkordb.sh"
        for candidate in ("registry/falkordb", "registry:5000/falkordb", "registry/falkordb:latest"):
            with self.subTest(candidate=candidate):
                result = subprocess.run(["sh", str(script)], capture_output=True, text=True, timeout=5,
                                        env={"PATH": os.environ["PATH"], "BASE_IMAGE": DIGEST,
                                             "CANDIDATE_IMAGE": candidate})
                self.assertEqual(result.returncode, 1)
                if ":latest" not in candidate:
                    self.assertIn("标签", result.stderr)


if __name__ == "__main__":
    unittest.main()
