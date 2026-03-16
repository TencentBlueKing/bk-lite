import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ServiceConfig:
    nats_servers: list[str]
    nats_instance_id: str
    nats_username: str = ""
    nats_password: str = ""
    nats_protocol: str = "nats"
    nats_tls_ca_file: str = ""
    nats_conn_timeout: int = 5
    max_workers: int = 4
    callback_timeout: int = 10
    ansible_work_dir: str = "/tmp/ansible-executor"
    js_stream: str = ""
    js_subject_prefix: str = ""
    js_durable: str = ""
    js_max_deliver: int = 5
    js_ack_wait: int = 300
    js_backoff: list[int] | None = None
    dlq_subject: str = "ansible.tasks.dlq"
    state_db_path: str = "/tmp/ansible-executor/task_state.db"


def _render_env_vars(value: str) -> str:
    if not value:
        return value
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)}")

    def replace(match: re.Match) -> str:
        key = match.group(1)
        return os.getenv(key, match.group(0))

    return pattern.sub(replace, value)


def load_config(path: str | None = None) -> ServiceConfig:
    data = {}
    if path:
        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}

    nats_servers_fallback = os.getenv("NATS_SERVERS", "")
    nats_username_fallback = os.getenv("NATS_USERNAME", "")
    nats_password_fallback = os.getenv("NATS_PASSWORD", "")
    nats_protocol_fallback = os.getenv("NATS_PROTOCOL", "nats")
    nats_tls_ca_file_fallback = os.getenv("NATS_TLS_CA_FILE", "")
    nats_instance_id_fallback = os.getenv("NATS_INSTANCE_ID", "default")
    nats_conn_timeout_fallback = os.getenv("NATS_CONNECT_TIMEOUT", "5")
    max_workers_fallback = os.getenv("ANSIBLE_MAX_WORKERS", "4")
    js_namespace_fallback = os.getenv("ANSIBLE_JS_NAMESPACE", "bk.ans_exec")
    js_stream_fallback = os.getenv("ANSIBLE_JS_STREAM", "")
    js_subject_prefix_fallback = os.getenv("ANSIBLE_JS_SUBJECT_PREFIX", "")
    js_durable_fallback = os.getenv("ANSIBLE_JS_DURABLE", "")
    js_max_deliver_fallback = os.getenv("ANSIBLE_JS_MAX_DELIVER", "5")
    js_ack_wait_fallback = os.getenv("ANSIBLE_JS_ACK_WAIT", "300")
    js_backoff_fallback = os.getenv("ANSIBLE_JS_BACKOFF", "5,15,30,60")
    dlq_subject_fallback = os.getenv("ANSIBLE_DLQ_SUBJECT", "ansible.tasks.dlq")
    state_db_path_fallback = os.getenv(
        "ANSIBLE_STATE_DB_PATH", "/tmp/ansible-executor/task_state.db"
    )
    callback_timeout_fallback = os.getenv("ANSIBLE_CALLBACK_TIMEOUT", "10")
    ansible_work_dir_fallback = os.getenv("ANSIBLE_WORK_DIR", "/tmp/ansible-executor")

    nats_servers_raw = _render_env_vars(
        str(
            data.get(
                "nats_servers",
                data.get("nats_urls", nats_servers_fallback),
            )
        )
    )
    nats_servers = [
        item.strip() for item in nats_servers_raw.split(",") if item.strip()
    ]
    nats_username = _render_env_vars(
        str(data.get("nats_username", nats_username_fallback))
    )
    nats_password = _render_env_vars(
        str(data.get("nats_password", nats_password_fallback))
    )
    nats_protocol = _render_env_vars(
        str(data.get("nats_protocol", nats_protocol_fallback))
    ).lower()
    nats_tls_ca_file = _render_env_vars(
        str(data.get("nats_tls_ca_file", nats_tls_ca_file_fallback))
    )
    nats_instance_id = _render_env_vars(
        str(data.get("nats_instance_id", nats_instance_id_fallback))
    )

    if not nats_servers:
        raise ValueError("nats_servers is required")

    raw_timeout = str(data.get("nats_conn_timeout", nats_conn_timeout_fallback)).strip()
    try:
        nats_conn_timeout = int(raw_timeout)
    except ValueError:
        nats_conn_timeout = int(nats_conn_timeout_fallback)

    raw_max_workers = str(data.get("max_workers", max_workers_fallback)).strip()
    try:
        max_workers = int(raw_max_workers)
    except ValueError:
        max_workers = int(max_workers_fallback)

    raw_callback_timeout = str(
        data.get("callback_timeout", callback_timeout_fallback)
    ).strip()
    try:
        callback_timeout = int(raw_callback_timeout)
    except ValueError:
        callback_timeout = int(callback_timeout_fallback)

    raw_js_max_deliver = str(
        data.get("js_max_deliver", js_max_deliver_fallback)
    ).strip()
    try:
        js_max_deliver = int(raw_js_max_deliver)
    except ValueError:
        js_max_deliver = int(js_max_deliver_fallback)

    raw_js_ack_wait = str(data.get("js_ack_wait", js_ack_wait_fallback)).strip()
    try:
        js_ack_wait = int(raw_js_ack_wait)
    except ValueError:
        js_ack_wait = int(js_ack_wait_fallback)

    raw_backoff = str(data.get("js_backoff", js_backoff_fallback)).strip()
    js_backoff = []
    for item in raw_backoff.split(","):
        piece = item.strip()
        if not piece:
            continue
        try:
            js_backoff.append(int(piece))
        except ValueError:
            continue
    if not js_backoff:
        js_backoff = [5, 15, 30, 60]

    js_namespace = (
        str(data.get("js_namespace", js_namespace_fallback)).strip() or "bk.ans_exec"
    )
    default_subject_prefix = f"{js_namespace}.tasks"
    default_stream = f"{js_namespace}.tasks.{nats_instance_id}".replace(
        ".", "_"
    ).upper()
    default_durable = f"ansible-executor-{nats_instance_id}"

    js_subject_prefix = (
        str(data.get("js_subject_prefix", js_subject_prefix_fallback)).strip()
        or default_subject_prefix
    )
    js_stream = str(data.get("js_stream", js_stream_fallback)).strip() or default_stream
    js_durable = (
        str(data.get("js_durable", js_durable_fallback)).strip() or default_durable
    )

    return ServiceConfig(
        nats_servers=nats_servers,
        nats_username=nats_username,
        nats_password=nats_password,
        nats_protocol=nats_protocol,
        nats_tls_ca_file=nats_tls_ca_file,
        nats_instance_id=nats_instance_id,
        nats_conn_timeout=nats_conn_timeout,
        max_workers=max_workers,
        callback_timeout=callback_timeout,
        ansible_work_dir=str(
            data.get("ansible_work_dir", ansible_work_dir_fallback)
        ).strip()
        or ansible_work_dir_fallback,
        js_stream=js_stream,
        js_subject_prefix=js_subject_prefix,
        js_durable=js_durable,
        js_max_deliver=max(1, js_max_deliver),
        js_ack_wait=max(5, js_ack_wait),
        js_backoff=js_backoff,
        dlq_subject=str(data.get("dlq_subject", dlq_subject_fallback)).strip()
        or dlq_subject_fallback,
        state_db_path=str(data.get("state_db_path", state_db_path_fallback)).strip()
        or state_db_path_fallback,
    )
