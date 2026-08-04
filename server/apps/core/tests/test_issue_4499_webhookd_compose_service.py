import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_SCRIPTS = REPOSITORY_ROOT / "agents" / "webhookd" / "compose"


@pytest.fixture
def compose_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_file = tmp_path / "docker-compose.calls"
    fake_compose = bin_dir / "docker-compose"
    fake_compose.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_COMPOSE_CALLS"\n'
        'printf \'%s\\n\' "$PWD" >> "$DOCKER_COMPOSE_PWD"\n'
        'exit "${DOCKER_COMPOSE_EXIT:-0}"\n',
        encoding="utf-8",
    )
    fake_compose.chmod(0o755)

    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    env = os.environ | {
        "COMPOSE_DIR": str(compose_dir),
        "DOCKER_COMPOSE_CALLS": str(calls_file),
        "DOCKER_COMPOSE_PWD": str(calls_file.with_suffix(".pwd")),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }
    return env, compose_dir, calls_file


def run_compose_script(script_name, payload, env):
    return subprocess.run(
        ["bash", str(COMPOSE_SCRIPTS / script_name), json.dumps(payload)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_setup_rejects_traversal_without_creating_outside_file(compose_env):
    env, compose_dir, calls_file = compose_env
    outside_file = compose_dir.parent / "escaped" / "docker-compose.yml"

    result = run_compose_script(
        "setup.sh",
        {"id": "../escaped", "compose": "services: {}"},
        env,
    )

    assert result.returncode != 0
    assert not outside_file.exists()
    assert not calls_file.exists()


def test_setup_rejects_symlinked_service_directory(compose_env):
    env, compose_dir, calls_file = compose_env
    outside_dir = compose_dir.parent / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "docker-compose.yml"
    outside_file.write_text("known-good\n", encoding="utf-8")
    (compose_dir / "safe").symlink_to(outside_dir, target_is_directory=True)

    result = run_compose_script(
        "setup.sh",
        {"id": "safe", "compose": "services: {}"},
        env,
    )

    assert result.returncode != 0
    assert outside_file.read_text(encoding="utf-8") == "known-good\n"
    assert not calls_file.exists()


def test_setup_rejects_compose_file_symlinked_to_directory(compose_env):
    env, compose_dir, calls_file = compose_env
    service_dir = compose_dir / "safe"
    service_dir.mkdir()
    outside_dir = compose_dir.parent / "outside"
    outside_dir.mkdir()
    (service_dir / "docker-compose.yml").symlink_to(
        outside_dir,
        target_is_directory=True,
    )

    result = run_compose_script(
        "setup.sh",
        {"id": "safe", "compose": "services: {}"},
        env,
    )

    assert result.returncode != 0
    assert not list(outside_dir.iterdir())
    assert not calls_file.exists()


def test_setup_invalid_config_preserves_existing_file(compose_env):
    env, compose_dir, calls_file = compose_env
    service_dir = compose_dir / "safe"
    service_dir.mkdir()
    compose_file = service_dir / "docker-compose.yml"
    compose_file.write_text("known-good\n", encoding="utf-8")
    env["DOCKER_COMPOSE_EXIT"] = "1"

    result = run_compose_script(
        "setup.sh",
        {"id": "safe", "compose": "invalid: ["},
        env,
    )

    assert result.returncode != 0
    assert compose_file.read_text(encoding="utf-8") == "known-good\n"
    assert calls_file.read_text(encoding="utf-8").startswith("-f ")
    assert not list(service_dir.glob(".docker-compose.yml.*"))


def test_setup_valid_config_atomically_replaces_existing_file(compose_env):
    env, compose_dir, calls_file = compose_env
    service_dir = compose_dir / "safe"
    service_dir.mkdir()
    compose_file = service_dir / "docker-compose.yml"
    compose_file.write_text("old\n", encoding="utf-8")

    result = run_compose_script(
        "setup.sh",
        {"id": "safe", "compose": "services: {}"},
        env,
    )

    assert result.returncode == 0
    assert compose_file.read_text(encoding="utf-8") == "services: {}\n"
    response = json.loads(result.stdout)
    assert response == {
        "status": "success",
        "id": "safe",
        "message": "Configuration is valid",
        "file": str(compose_file),
    }
    compose_args = calls_file.read_text(encoding="utf-8").strip().split()
    assert compose_args[0] == "-f"
    assert compose_args[-1] == "config"
    assert calls_file.with_suffix(".pwd").read_text(encoding="utf-8").strip() == str(service_dir)
    assert not list(service_dir.glob(".docker-compose.yml.*"))


@pytest.mark.parametrize("script_name", ["start.sh", "stop.sh", "status.sh"])
def test_single_service_actions_reject_traversal_before_compose_call(
    compose_env,
    script_name,
):
    env, compose_dir, calls_file = compose_env
    outside_dir = compose_dir.parent / "escaped"
    outside_dir.mkdir()
    (outside_dir / "docker-compose.yml").write_text(
        "services: {}\n",
        encoding="utf-8",
    )

    result = run_compose_script(script_name, {"id": "../escaped"}, env)

    assert result.returncode != 0
    assert not calls_file.exists()


@pytest.mark.parametrize(
    ("script_name", "expected_args", "expected_message"),
    [
        ("start.sh", "up -d", "Successfully started"),
        ("stop.sh", "down", "Successfully stopped"),
    ],
)
def test_existing_single_service_actions_keep_success_contract(
    compose_env,
    script_name,
    expected_args,
    expected_message,
):
    env, compose_dir, calls_file = compose_env
    service_dir = compose_dir / "legacy_service-1"
    service_dir.mkdir()
    (service_dir / "docker-compose.yml").write_text(
        "services: {}\n",
        encoding="utf-8",
    )

    result = run_compose_script(script_name, {"id": "legacy_service-1"}, env)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "status": "success",
        "id": "legacy_service-1",
        "message": expected_message,
    }
    assert calls_file.read_text(encoding="utf-8").strip() == expected_args


def test_existing_status_call_keeps_empty_container_success_contract(compose_env):
    env, compose_dir, calls_file = compose_env
    service_dir = compose_dir / "legacy_service-1"
    service_dir.mkdir()
    (service_dir / "docker-compose.yml").write_text(
        "services: {}\n",
        encoding="utf-8",
    )

    result = run_compose_script(
        "status.sh",
        {"id": "legacy_service-1"},
        env,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "id": "legacy_service-1",
        "status": "success",
        "containers": [],
    }
    assert calls_file.read_text(encoding="utf-8").strip() == "ps --format json"


def test_status_rejects_invalid_batch_before_any_compose_call(compose_env):
    env, compose_dir, calls_file = compose_env
    for service_id in ("safe", "escaped"):
        service_dir = compose_dir.parent / service_id if service_id == "escaped" else compose_dir / service_id
        service_dir.mkdir()
        (service_dir / "docker-compose.yml").write_text(
            "services: {}\n",
            encoding="utf-8",
        )

    result = run_compose_script(
        "status.sh",
        {"ids": ["safe", "../escaped"]},
        env,
    )

    assert result.returncode != 0
    assert not calls_file.exists()
