from core.config import ServiceConfig, load_config


def test_service_config_uses_default_subject_allowlists():
    config = ServiceConfig(nats_servers=["nats://127.0.0.1:4222"], nats_instance_id="default")

    assert config.allowed_callback_subjects == [
        "job.ansible_task_callback",
        "default_stargazer.host_remote.callback",
    ]
    assert config.allowed_stream_subjects == ["job.stream.>", "executor.stream.>", "bk.ans_exec.stream.>"]


def test_load_config_reads_subject_allowlists_from_yaml(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
nats:
  servers:
    - nats://127.0.0.1:4222
  instance_id: default
security:
  allowed_callback_subjects:
    - job.ansible_task_callback
    - bklite.safe_callback.>
  allowed_stream_subjects:
    - job.stream.>
    - executor.stream.>
""",
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert config.allowed_callback_subjects == ["job.ansible_task_callback", "bklite.safe_callback.>"]
    assert config.allowed_stream_subjects == ["job.stream.>", "executor.stream.>"]


def test_load_config_reads_subject_allowlists_from_env(monkeypatch):
    monkeypatch.setenv("NATS_SERVERS", "nats://127.0.0.1:4222")
    monkeypatch.setenv("ANSIBLE_ALLOWED_CALLBACK_SUBJECTS", "job.ansible_task_callback,bklite.safe_callback.>")
    monkeypatch.setenv("ANSIBLE_ALLOWED_STREAM_SUBJECTS", "job.stream.>,executor.stream.>")

    config = load_config()

    assert config.allowed_callback_subjects == ["job.ansible_task_callback", "bklite.safe_callback.>"]
    assert config.allowed_stream_subjects == ["job.stream.>", "executor.stream.>"]
