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


def _get_value(data: dict, *path: str, default=None):
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _pick_value(data: dict, keys: list[tuple[str, ...]], fallback):
    for key_path in keys:
        value = _get_value(data, *key_path, default=None)
        if value is not None:
            return value
    return fallback


def _as_string(value) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [
        item.strip() for item in _render_env_vars(str(value)).split(",") if item.strip()
    ]


def _parse_int_list(value) -> list[int]:
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    result: list[int] = []
    for item in items:
        piece = str(item).strip()
        if not piece:
            continue
        try:
            result.append(int(piece))
        except ValueError:
            continue
    return result


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

    nats_servers_raw = _pick_value(
        data,
        [("nats_servers",), ("nats_urls",), ("nats", "servers")],
        nats_servers_fallback,
    )
    nats_servers = _parse_string_list(nats_servers_raw)
    nats_username = _render_env_vars(
        _as_string(
            _pick_value(
                data,
                [("nats_username",), ("nats", "username")],
                nats_username_fallback,
            )
        )
    )
    nats_password = _render_env_vars(
        _as_string(
            _pick_value(
                data,
                [("nats_password",), ("nats", "password")],
                nats_password_fallback,
            )
        )
    )
    nats_protocol = _render_env_vars(
        _as_string(
            _pick_value(
                data,
                [("nats_protocol",), ("nats", "protocol")],
                nats_protocol_fallback,
            )
        )
    ).lower()
    nats_tls_ca_file = _render_env_vars(
        _as_string(
            _pick_value(
                data,
                [("nats_tls_ca_file",), ("nats", "tls_ca_file")],
                nats_tls_ca_file_fallback,
            )
        )
    )
    nats_instance_id = _render_env_vars(
        _as_string(
            _pick_value(
                data,
                [("nats_instance_id",), ("nats", "instance_id")],
                nats_instance_id_fallback,
            )
        )
    )

    if not nats_servers:
        raise ValueError("nats_servers is required")

    raw_timeout = _as_string(
        _pick_value(
            data,
            [("nats_conn_timeout",), ("nats", "connect_timeout")],
            nats_conn_timeout_fallback,
        )
    ).strip()
    try:
        nats_conn_timeout = int(raw_timeout)
    except ValueError:
        nats_conn_timeout = int(nats_conn_timeout_fallback)

    raw_max_workers = _as_string(
        _pick_value(
            data,
            [("max_workers",), ("runtime", "max_workers")],
            max_workers_fallback,
        )
    ).strip()
    try:
        max_workers = int(raw_max_workers)
    except ValueError:
        max_workers = int(max_workers_fallback)

    raw_callback_timeout = _as_string(
        _pick_value(
            data,
            [("callback_timeout",), ("runtime", "callback_timeout")],
            callback_timeout_fallback,
        )
    ).strip()
    try:
        callback_timeout = int(raw_callback_timeout)
    except ValueError:
        callback_timeout = int(callback_timeout_fallback)

    raw_js_max_deliver = _as_string(
        _pick_value(
            data,
            [("js_max_deliver",), ("jetstream", "max_deliver")],
            js_max_deliver_fallback,
        )
    ).strip()
    try:
        js_max_deliver = int(raw_js_max_deliver)
    except ValueError:
        js_max_deliver = int(js_max_deliver_fallback)

    raw_js_ack_wait = _as_string(
        _pick_value(
            data,
            [("js_ack_wait",), ("jetstream", "ack_wait")],
            js_ack_wait_fallback,
        )
    ).strip()
    try:
        js_ack_wait = int(raw_js_ack_wait)
    except ValueError:
        js_ack_wait = int(js_ack_wait_fallback)

    raw_backoff = _pick_value(
        data,
        [("js_backoff",), ("jetstream", "backoff")],
        js_backoff_fallback,
    )
    js_backoff = _parse_int_list(raw_backoff)
    if not js_backoff:
        js_backoff = [5, 15, 30, 60]

    js_namespace = (
        _as_string(
            _pick_value(
                data,
                [("js_namespace",), ("jetstream", "namespace")],
                js_namespace_fallback,
            )
        ).strip()
        or "bk.ans_exec"
    )
    default_subject_prefix = f"{js_namespace}.tasks"
    default_stream = f"{js_namespace}.tasks.{nats_instance_id}".replace(
        ".", "_"
    ).upper()
    default_durable = f"ansible-executor-{nats_instance_id}"

    js_subject_prefix = (
        _as_string(
            _pick_value(
                data,
                [("js_subject_prefix",), ("jetstream", "subject_prefix")],
                js_subject_prefix_fallback,
            )
        ).strip()
        or default_subject_prefix
    )
    js_stream = (
        _as_string(
            _pick_value(
                data,
                [("js_stream",), ("jetstream", "stream")],
                js_stream_fallback,
            )
        ).strip()
        or default_stream
    )
    js_durable = (
        _as_string(
            _pick_value(
                data,
                [("js_durable",), ("jetstream", "durable")],
                js_durable_fallback,
            )
        ).strip()
        or default_durable
    )

    ansible_work_dir = (
        _as_string(
            _pick_value(
                data,
                [("ansible_work_dir",), ("runtime", "work_dir")],
                ansible_work_dir_fallback,
            )
        ).strip()
        or ansible_work_dir_fallback
    )
    dlq_subject = (
        _as_string(
            _pick_value(
                data,
                [("dlq_subject",), ("jetstream", "dlq_subject")],
                dlq_subject_fallback,
            )
        ).strip()
        or dlq_subject_fallback
    )
    state_db_path = (
        _as_string(
            _pick_value(
                data,
                [("state_db_path",), ("runtime", "state_db_path")],
                state_db_path_fallback,
            )
        ).strip()
        or state_db_path_fallback
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
        ansible_work_dir=ansible_work_dir,
        js_stream=js_stream,
        js_subject_prefix=js_subject_prefix,
        js_durable=js_durable,
        js_max_deliver=max(1, js_max_deliver),
        js_ack_wait=max(5, js_ack_wait),
        js_backoff=js_backoff,
        dlq_subject=dlq_subject,
        state_db_path=state_db_path,
    )
