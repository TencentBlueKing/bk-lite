import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
ALGORITHM_SERVICES = (
    "classify_anomaly_server",
    "classify_image_classification_server",
    "classify_log_server",
    "classify_object_detection_server",
    "classify_text_classification_server",
    "classify_timeseries_server",
)


class AlgorithmEntrypointContractTest(unittest.TestCase):
    def test_all_algorithm_health_endpoints_publish_instance_identity(self):
        for service in ALGORITHM_SERVICES:
            service_path = (
                REPO_ROOT
                / "algorithms"
                / service
                / service
                / "serving"
                / "service.py"
            )
            source = service_path.read_text(encoding="utf-8")
            self.assertIn(
                '"startup_instance_id": os.getenv("SERVING_INSTANCE_ID", "")',
                source,
                service,
            )

    def test_bentoml_exit_code_reaches_container_entrypoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_path = Path(temp_dir)
            fake_python = bin_path / "python3"
            fake_python.write_text("#!/bin/bash\nexit 42\n", encoding="utf-8")
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_path}:{env['PATH']}"

            for service in ALGORITHM_SERVICES:
                with self.subTest(service=service):
                    startup = (
                        REPO_ROOT
                        / "algorithms"
                        / service
                        / "support-files"
                        / "release"
                        / "startup.sh"
                    )
                    result = subprocess.run(
                        ["bash", str(startup)],
                        check=False,
                        capture_output=True,
                        text=True,
                        env=env,
                    )
                    self.assertEqual(result.returncode, 42)


if __name__ == "__main__":
    unittest.main()
