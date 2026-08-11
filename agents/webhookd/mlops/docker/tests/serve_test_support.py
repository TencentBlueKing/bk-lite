import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "serve.sh"


class DockerServingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.bin_path = self.temp_path / "bin"
        self.bin_path.mkdir()
        self.docker_log = self.temp_path / "docker.log"
        self.curl_log = self.temp_path / "curl.log"
        self.container_state = self.temp_path / "container.state"
        self.label_query_count = self.temp_path / "label-query.count"
        self.remove_attempt_count = self.temp_path / "remove-attempt.count"
        self.real_jq_path = shutil.which("jq")
        if self.real_jq_path is None:
            self.fail("jq is required for serving contract tests")

        self._write_executable(
            "docker",
            """
            #!/bin/bash
            echo "$*" >> "$FAKE_DOCKER_LOG"
            case "$1" in
                ps)
                    if [[ " $* " == *" label=bk-lite.startup-id="* ]]; then
                        count=0
                        if [ -f "$FAKE_LABEL_QUERY_COUNT_FILE" ]; then
                            count=$(cat "$FAKE_LABEL_QUERY_COUNT_FILE")
                        fi
                        count=$((count + 1))
                        echo "$count" > "$FAKE_LABEL_QUERY_COUNT_FILE"
                        if [ -f "$FAKE_CONTAINER_STATE_FILE" ] \
                            && [ "$count" -ge "${FAKE_LABEL_VISIBLE_AFTER:-1}" ]; then
                            echo "fake-container-id"
                        fi
                    elif [ -f "$FAKE_CONTAINER_STATE_FILE" ]; then
                        echo "issue-3850-serving"
                    fi
                    exit 0
                    ;;
                images)
                    echo "test-serving:latest"
                    ;;
                image)
                    if [ "$2" = "inspect" ]; then
                        if [ "$3" = "nvidia/cuda:11.0-base" ] \
                            && [ "${FAKE_GPU_IMAGE_PRESENT:-1}" != "1" ]; then
                            exit 1
                        fi
                        exit 0
                    fi
                    exit 1
                    ;;
                pull)
                    if [ -n "${FAKE_GPU_PULL_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_GPU_PULL_DELAY_SECONDS"
                    fi
                    exit "${FAKE_GPU_PULL_STATUS:-0}"
                    ;;
                run)
                    if [[ " $* " == *" nvidia/cuda:11.0-base "* ]]; then
                        if [ -n "${FAKE_GPU_PROBE_DELAY_SECONDS:-}" ]; then
                            /bin/sleep "$FAKE_GPU_PROBE_DELAY_SECONDS"
                        fi
                        exit "${FAKE_GPU_AVAILABLE:-1}"
                    fi
                    if [ -f "$FAKE_CONTAINER_STATE_FILE" ]; then
                        echo "container name already exists" >&2
                        exit 125
                    fi
                    touch "$FAKE_CONTAINER_STATE_FILE"
                    while [ "$#" -gt 0 ]; do
                        if [ "$1" = "--cidfile" ]; then
                            if [ "${FAKE_SKIP_CIDFILE:-0}" != "1" ]; then
                                echo "fake-container-id" > "$2"
                            fi
                            break
                        fi
                        shift
                    done
                    if [ -n "${FAKE_DOCKER_RUN_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_DOCKER_RUN_DELAY_SECONDS"
                    fi
                    echo "fake-container-id"
                    ;;
                inspect)
                    case "$*" in
                        *State.Status*)
                            echo "${FAKE_DOCKER_STATE:-running}"
                            ;;
                        *State.ExitCode*)
                            echo "${FAKE_DOCKER_EXIT_CODE:-42}"
                            ;;
                        *HostPort*)
                            echo "39000"
                            ;;
                    esac
                    ;;
                logs)
                    if [ -n "${FAKE_DOCKER_LOGS_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_DOCKER_LOGS_DELAY_SECONDS"
                    fi
                    message="${FAKE_DOCKER_LOG_MESSAGE:-model load failed: dependency unavailable}"
                    echo "$message"
                    ;;
                update)
                    exit "${FAKE_DOCKER_UPDATE_STATUS:-0}"
                    ;;
                rm)
                    count=0
                    if [ -f "$FAKE_REMOVE_ATTEMPT_COUNT_FILE" ]; then
                        count=$(cat "$FAKE_REMOVE_ATTEMPT_COUNT_FILE")
                    fi
                    count=$((count + 1))
                    echo "$count" > "$FAKE_REMOVE_ATTEMPT_COUNT_FILE"
                    if [ -n "${FAKE_DOCKER_REMOVE_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_DOCKER_REMOVE_DELAY_SECONDS"
                    fi
                    if [ "${FAKE_DOCKER_REMOVE_FAIL:-0}" = "1" ] \
                        || [ "$count" -le "${FAKE_DOCKER_REMOVE_FAILS_BEFORE:-0}" ]; then
                        exit 1
                    fi
                    rm -f "$FAKE_CONTAINER_STATE_FILE"
                    ;;
            esac
            """,
        )
        self._write_executable(
            "curl",
            """
            #!/bin/bash
            if [ -n "${FAKE_CURL_DELAY_SECONDS:-}" ]; then
                /bin/sleep "$FAKE_CURL_DELAY_SECONDS"
            fi
            count=0
            if [ -f "$FAKE_CURL_LOG" ]; then
                count=$(wc -l < "$FAKE_CURL_LOG" | tr -d ' ')
            fi
            count=$((count + 1))
            echo "$*" >> "$FAKE_CURL_LOG"
            if [ "${FAKE_LEGACY_HEALTH:-0}" = "1" ]; then
                case "$*" in
                    */health*) exit 22 ;;
                    */readyz*) exit 0 ;;
                esac
            fi
            if [ "$count" -ge "${FAKE_CURL_SUCCEED_AFTER:-999}" ]; then
                instance_id="${FAKE_CURL_INSTANCE_ID:-$SERVING_INSTANCE_ID}"
                printf '{"status":"healthy","startup_instance_id":"%s"}\n' "$instance_id"
                exit 0
            fi
            exit 22
            """,
        )
        self._write_executable(
            "jq",
            """
            #!/bin/bash
            if [ -n "${FAKE_JQ_DELAY_SECONDS:-}" ]; then
                /bin/sleep "$FAKE_JQ_DELAY_SECONDS"
            fi
            exec "$REAL_JQ_PATH" "$@"
            """,
        )
        self._write_executable("sleep", "#!/bin/bash\nexit 0\n")

    def _write_executable(self, name, content):
        path = self.bin_path / name
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def _run_serve(
        self,
        startup_timeout_seconds=3,
        network_mode=None,
        port=None,
        device=None,
        **extra_env,
    ):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_path}:{env['PATH']}",
                "FAKE_DOCKER_LOG": str(self.docker_log),
                "FAKE_CURL_LOG": str(self.curl_log),
                "FAKE_CONTAINER_STATE_FILE": str(self.container_state),
                "FAKE_LABEL_QUERY_COUNT_FILE": str(self.label_query_count),
                "FAKE_REMOVE_ATTEMPT_COUNT_FILE": str(self.remove_attempt_count),
                "REAL_JQ_PATH": self.real_jq_path,
            }
        )
        env.update(extra_env)
        payload_data = {
            "id": "issue-3850-serving",
            "mlflow_tracking_uri": "http://mlflow:5000",
            "mlflow_model_uri": "models:/demo/1",
            "train_image": "test-serving:latest",
        }
        if startup_timeout_seconds is not None:
            payload_data["startup_timeout_seconds"] = startup_timeout_seconds
        if network_mode is not None:
            payload_data["network_mode"] = network_mode
        if port is not None:
            payload_data["port"] = port
        if device is not None:
            payload_data["device"] = device
        payload = json.dumps(payload_data)
        return subprocess.run(
            ["bash", str(SCRIPT_PATH), payload],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
