import base64
import re
import shlex
from dataclasses import dataclass

import toml
from django.core import signing

from apps.core.logger import node_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import ChildConfig, NodeOrganization, SidecarEnv
from apps.rpc.executor import Executor


class TelegrafOneShotError(RuntimeError):
    retryable = False


@dataclass(frozen=True)
class _Runtime:
    node_id: str
    operating_system: str
    executable_path: str
    env: dict[str, str]
    config_content: str


class TelegrafOneShotService:
    MAX_CONFIGS = 2
    MAX_CONFIG_BYTES = 64 * 1024
    MAX_ENV_VARS = 256
    MAX_ENV_BYTES = 128 * 1024
    MAX_STDOUT_BYTES = 256 * 1024
    PROCESS_TIMEOUT_SECONDS = 60
    CONFIG_ENV_KEY = "BK_LITE_TELEGRAF_ONESHOT_CONFIG_B64"
    AUTHORIZATION_SALT = "node-mgmt.telegraf-oneshot.v1"
    AUTHORIZATION_MAX_AGE_SECONDS = 120
    ACCEPTED_STATUSES = frozenset({"accepted", "duplicate_active"})
    LOCK_DIR = "/tmp/bklite-cmdb-telegraf-oneshot.lock"
    TEMP_DIR_TEMPLATE = "/tmp/bklite-cmdb-telegraf-oneshot.XXXXXX"
    WATCHDOG_SECONDS = 70
    _CONFIG_ID_PATTERN = re.compile(r"^cmdb_[1-9][0-9]*(?:_topology)?$")
    _ALLOWED_PROMETHEUS_KEYS = frozenset(
        {
            "urls",
            "interval",
            "collection_offset",
            "timeout",
            "response_timeout",
            "http_headers",
            "namedrop",
            "tags",
        }
    )

    @classmethod
    def run_telegraf_child_configs_once(
        cls,
        request_id: str,
        config_ids: list[str],
        expected_node_id: str,
        organization_ids: list[int],
    ) -> dict:
        normalized_ids = [str(item) for item in (config_ids or [])][: cls.MAX_CONFIGS]
        try:
            runtime = cls._build_runtime(
                config_ids=config_ids,
                expected_node_id=expected_node_id,
                organization_ids=organization_ids,
            )
        except TelegrafOneShotError as exc:
            return cls._failure_result(request_id, normalized_ids, retryable=exc.retryable, error_type=type(exc).__name__)
        command, shell = cls._build_command(
            operating_system=runtime.operating_system,
            executable_path=runtime.executable_path,
        )
        execution_env = dict(runtime.env)
        if cls.CONFIG_ENV_KEY in execution_env:
            return cls._failure_result(
                request_id,
                normalized_ids,
                retryable=False,
                error_type="ReservedEnvironmentVariable",
            )
        execution_env[cls.CONFIG_ENV_KEY] = base64.b64encode(runtime.config_content.encode("utf-8")).decode("ascii")
        if cls._env_bytes(execution_env) > cls.MAX_ENV_BYTES:
            return cls._failure_result(request_id, normalized_ids, retryable=False, error_type="EnvironmentTooLarge")
        try:
            raw_result = Executor(runtime.node_id).execute_local(
                command,
                timeout=cls.PROCESS_TIMEOUT_SECONDS,
                shell=shell,
                env=execution_env,
            )
        except Exception as exc:  # noqa: BLE001 - Executor RPC is an external boundary.
            logger.error(
                "event=telegraf_oneshot_execute_failed request_id=%s node_id=%s failed_stage=execute error_type=%s",
                safe_log_value(request_id),
                runtime.node_id,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return cls._failure_result(request_id, normalized_ids, retryable=True, error_type=type(exc).__name__)
        if cls._exit_code(raw_result) == 75:
            return cls._failure_result(
                request_id,
                normalized_ids,
                retryable=True,
                error_type="NodeBusy",
            )
        stdout = cls._stdout(raw_result)
        channels = cls._parse_channels(
            stdout,
            config_ids,
            missing_retryable=not cls._process_succeeded(raw_result),
        )
        accepted_count = sum(item["status"] in cls.ACCEPTED_STATUSES for item in channels.values())
        if accepted_count == len(channels):
            status = "accepted"
        elif accepted_count:
            status = "partial"
        else:
            status = "failed"
        return {
            "request_id": str(request_id)[:128],
            "status": status,
            "channels": channels,
        }

    @staticmethod
    def _failure_result(request_id: str, config_ids: list[str], *, retryable: bool, error_type: str) -> dict:
        return {
            "request_id": str(request_id)[:128],
            "status": "failed",
            "channels": {
                config_id: {
                    "status": "failed",
                    "task_id": "",
                    "retryable": retryable,
                    "error_type": error_type,
                }
                for config_id in config_ids
            },
        }

    @classmethod
    def _build_runtime(cls, config_ids: list[str], expected_node_id: str, organization_ids: list[int]) -> _Runtime:
        ids = [str(item) for item in (config_ids or [])]
        if not 1 <= len(ids) <= cls.MAX_CONFIGS or len(set(ids)) != len(ids):
            raise TelegrafOneShotError("Telegraf one-shot 配置数量无效")
        if any(not cls._CONFIG_ID_PATTERN.fullmatch(config_id) for config_id in ids):
            raise TelegrafOneShotError("Telegraf one-shot 配置 ID 无效")
        task_scopes = {config_id.removesuffix("_topology") for config_id in ids}
        if len(task_scopes) != 1:
            raise TelegrafOneShotError("Telegraf one-shot 子配置不属于同一 CMDB 任务")

        children = list(
            ChildConfig.objects.filter(id__in=ids).select_related("collector_config__collector", "collector_config__cloud_region").order_by("id")
        )
        if len(children) != len(ids):
            raise TelegrafOneShotError("Telegraf one-shot 子配置不存在")

        parents = {child.collector_config_id for child in children}
        if len(parents) != 1:
            raise TelegrafOneShotError("Telegraf one-shot 子配置不属于同一父配置")
        parent = children[0].collector_config
        collector = parent.collector
        if collector.name != "Telegraf":
            raise TelegrafOneShotError("Telegraf one-shot 仅支持 Telegraf 配置")

        nodes = list(parent.nodes.order_by("id"))
        if len(nodes) != 1 or nodes[0].id != str(expected_node_id):
            raise TelegrafOneShotError("Telegraf one-shot 执行节点不匹配")
        node = nodes[0]
        if not NodeOrganization.objects.filter(node_id=node.id, organization__in=organization_ids).exists():
            raise TelegrafOneShotError("Telegraf one-shot 执行节点不在授权组织范围")
        if collector.node_operating_system != node.operating_system:
            raise TelegrafOneShotError("Telegraf one-shot Collector 与节点操作系统不匹配")
        if node.operating_system != NodeConstants.LINUX_OS:
            raise TelegrafOneShotError("Telegraf one-shot 不支持该节点操作系统")

        rendered_inputs = []
        total_bytes = 0
        for child in children:
            if child.collect_type != "http":
                raise TelegrafOneShotError("Telegraf one-shot 子配置采集类型无效")
            encoded = child.content.encode("utf-8")
            total_bytes += len(encoded)
            if total_bytes > cls.MAX_CONFIG_BYTES:
                raise TelegrafOneShotError("Telegraf one-shot 配置超过大小限制")
            rendered_inputs.append(cls._convert_child_config(child.id, child.content))

        config = {
            "inputs": {"http": rendered_inputs},
            "outputs": {"file": [{"files": ["stdout"], "data_format": "influx"}]},
        }
        env = cls._merge_env(node.cloud_region_id, parent.env_config or {}, children)
        if len(env) > cls.MAX_ENV_VARS or cls._env_bytes(env) > cls.MAX_ENV_BYTES:
            raise TelegrafOneShotError("Telegraf one-shot 环境变量超过数量限制")
        return _Runtime(
            node_id=node.id,
            operating_system=node.operating_system,
            executable_path=collector.executable_path,
            env=env,
            config_content=toml.dumps(config),
        )

    @classmethod
    def build_authorization(
        cls,
        *,
        request_id: str,
        config_ids: list[str],
        expected_node_id: str,
        organization_ids: list[int],
    ) -> str:
        return signing.dumps(
            {
                "caller": "cmdb.first_collection",
                "request_id": request_id,
                "config_ids": config_ids,
                "expected_node_id": expected_node_id,
                "organization_ids": organization_ids,
            },
            salt=cls.AUTHORIZATION_SALT,
            compress=True,
        )

    @classmethod
    def verify_authorization(
        cls,
        authorization: str,
        *,
        request_id: str,
        config_ids: list[str],
        expected_node_id: str,
        organization_ids: list[int],
    ) -> bool:
        try:
            claims = signing.loads(
                authorization,
                salt=cls.AUTHORIZATION_SALT,
                max_age=cls.AUTHORIZATION_MAX_AGE_SECONDS,
            )
        except signing.BadSignature:
            return False
        return claims == {
            "caller": "cmdb.first_collection",
            "request_id": request_id,
            "config_ids": config_ids,
            "expected_node_id": expected_node_id,
            "organization_ids": organization_ids,
        }

    @classmethod
    def _convert_child_config(cls, config_id: str, content: str) -> dict:
        try:
            parsed = toml.loads(content)
        except (TypeError, toml.TomlDecodeError):
            raise TelegrafOneShotError("Telegraf one-shot 子配置不是合法 TOML") from None
        if not isinstance(parsed, dict) or set(parsed) != {"inputs"}:
            raise TelegrafOneShotError("Telegraf one-shot 子配置包含未知顶层结构")
        inputs = parsed.get("inputs")
        if not isinstance(inputs, dict) or set(inputs) != {"prometheus"}:
            raise TelegrafOneShotError("Telegraf one-shot 子配置 input 类型无效")
        prometheus_inputs = inputs.get("prometheus")
        if not isinstance(prometheus_inputs, list) or len(prometheus_inputs) != 1 or not isinstance(prometheus_inputs[0], dict):
            raise TelegrafOneShotError("Telegraf one-shot 子配置必须包含一个 prometheus input")
        source = prometheus_inputs[0]
        if set(source) - cls._ALLOWED_PROMETHEUS_KEYS:
            raise TelegrafOneShotError("Telegraf one-shot 子配置包含未知字段")
        urls = source.get("urls")
        if not isinstance(urls, list) or urls != ["${STARGAZER_URL}/api/collect/collect_info"]:
            raise TelegrafOneShotError("Telegraf one-shot Stargazer 地址无效")

        raw_tags = source.get("tags") or {}
        raw_headers = source.get("http_headers") or {}
        if not isinstance(raw_tags, dict) or not isinstance(raw_headers, dict):
            raise TelegrafOneShotError("Telegraf one-shot tags 或 headers 类型无效")
        tags = dict(raw_tags)
        tags["oneshot_channel_id"] = config_id
        converted = {
            "urls": [str(urls[0])],
            "timeout": cls._bounded_timeout(source.get("timeout")),
            "success_status_codes": [202],
            "data_format": "prometheus",
            "prometheus_metric_version": 2,
            "headers": dict(raw_headers),
            "tags": tags,
        }
        return converted

    @staticmethod
    def _bounded_timeout(value) -> str:
        match = re.fullmatch(r"\s*([0-9]+)s\s*", str(value or ""))
        seconds = int(match.group(1)) if match else 30
        return f"{min(max(seconds, 3), 30)}s"

    @staticmethod
    def _decode_env(env: dict) -> dict[str, str]:
        aes = AESCryptor()
        decoded = {}
        for key, value in (env or {}).items():
            if "password" in str(key).lower() and value not in (None, ""):
                try:
                    decoded[str(key)] = aes.decode(str(value))
                except Exception:  # noqa: BLE001 - Crypto backend failures share one safe error contract.
                    raise TelegrafOneShotError("Telegraf one-shot 环境变量解密失败") from None
            else:
                decoded[str(key)] = str(value)
        return decoded

    @classmethod
    def _merge_env(cls, cloud_region_id, parent_env: dict, children: list[ChildConfig]) -> dict[str, str]:
        merged = cls._strict_region_env(cloud_region_id)
        merged.update(cls._decode_env(parent_env))
        child_env = {}
        for child in children:
            decoded = cls._decode_env(child.env_config or {})
            for key, value in decoded.items():
                if key in child_env and child_env[key] != value:
                    raise TelegrafOneShotError("Telegraf one-shot 子配置环境变量冲突")
                child_env[key] = value
        merged.update(child_env)
        return merged

    @classmethod
    def _strict_region_env(cls, cloud_region_id) -> dict[str, str]:
        aes = AESCryptor()
        env = {}
        for row in SidecarEnv.objects.filter(cloud_region_id=cloud_region_id).values("key", "value", "type"):
            key = str(row["key"])
            value = row["value"]
            if row["type"] == "secret" and value not in (None, ""):
                try:
                    env[key] = aes.decode(str(value))
                except Exception:  # noqa: BLE001 - This path must fail closed instead of forwarding ciphertext.
                    raise TelegrafOneShotError("Telegraf one-shot 云区域环境变量解密失败") from None
            else:
                env[key] = str(value)
        return env

    @staticmethod
    def _env_bytes(env: dict[str, str]) -> int:
        total = 0
        for key, value in env.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or "\x00" in value:
                raise TelegrafOneShotError("Telegraf one-shot 环境变量格式无效")
            total += len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2
        return total

    @classmethod
    def _build_command(cls, operating_system: str, executable_path: str) -> tuple[str, str]:
        if operating_system == NodeConstants.LINUX_OS:
            command = (
                "umask 077\n"
                f"lock_dir={shlex.quote(cls.LOCK_DIR)}\n"
                'mkdir -- "$lock_dir" || exit 75\n'
                "work_dir=\n"
                "cleanup() {\n"
                '  if [ -n "$work_dir" ]; then rm -f -- "$work_dir/config.toml"; rmdir -- "$work_dir"; fi\n'
                '  rmdir -- "$lock_dir"\n'
                "}\n"
                "trap cleanup EXIT\n"
                f"work_dir=$(mktemp -d {shlex.quote(cls.TEMP_DIR_TEMPLATE)}) || exit 70\n"
                'config_path="$work_dir/config.toml"\n'
                f'printf %s "${{{cls.CONFIG_ENV_KEY}}}" | base64 -d > "$config_path" || exit 70\n'
                f"unset {cls.CONFIG_ENV_KEY}\n"
                "ulimit -t 60 || exit 70\n"
                "ulimit -v 8388608 || exit 70\n"
                "export GOMEMLIMIT=384MiB\n"
                "runner_pid=$$\n"
                'runner_stat=$(cat "/proc/$runner_pid/stat") || exit 70\n'
                "runner_tail=${runner_stat##*) }\n"
                "set -- $runner_tail\n"
                "runner_start=${20:-}\n"
                '[ -n "$runner_start" ] || exit 70\n'
                "runner_is_same() {\n"
                '  current_stat=$(cat "/proc/$runner_pid/stat" 2>/dev/null) || return 1\n'
                "  current_tail=${current_stat##*) }\n"
                "  set -- $current_tail\n"
                '  [ "${20:-}" = "$runner_start" ]\n'
                "}\n"
                "(\n"
                f"  remaining={cls.WATCHDOG_SECONDS}\n"
                '  while [ "$remaining" -gt 0 ] && runner_is_same; do\n'
                "    sleep 1\n"
                "    remaining=$((remaining - 1))\n"
                "  done\n"
                "  if runner_is_same; then\n"
                '    kill -TERM "$runner_pid" 2>/dev/null\n'
                "    sleep 2\n"
                '    if runner_is_same; then kill -KILL "$runner_pid" 2>/dev/null; fi\n'
                "  fi\n"
                "  cleanup\n"
                ") >/dev/null 2>&1 &\n"
                "trap - EXIT\n"
                f'exec {shlex.quote(executable_path)} --once --config "$config_path"'
            )
            return command, "sh"
        raise TelegrafOneShotError("Telegraf one-shot 不支持该节点操作系统")

    @staticmethod
    def _stdout(raw_result) -> str:
        if isinstance(raw_result, dict):
            value = str(raw_result.get("stdout", raw_result.get("result", "")) or "")
        else:
            value = str(raw_result or "")
        return value.encode("utf-8")[: TelegrafOneShotService.MAX_STDOUT_BYTES].decode("utf-8", errors="ignore")

    @classmethod
    def _parse_channels(cls, stdout: str, config_ids: list[str], *, missing_retryable: bool) -> dict:
        channels = {
            config_id: {
                "status": "failed",
                "task_id": "",
                "retryable": missing_retryable,
                **({} if missing_retryable else {"error_type": "AcceptanceMetricMissing"}),
            }
            for config_id in config_ids
        }
        for line in stdout.splitlines():
            head, separator, fields_and_time = line.partition(" ")
            if not separator:
                continue
            measurement = head.split(",", 1)[0]
            if measurement not in {"prometheus", "collection_request_accepted"}:
                continue
            tags = {}
            for item in head.split(",")[1:]:
                key, found, value = item.partition("=")
                if found:
                    tags[key] = value
            fields = fields_and_time.split(" ", 1)[0]
            accepted = any(
                item in {"collection_request_accepted=1", "collection_request_accepted=1i", "collection_request_accepted=1.0"}
                for item in fields.split(",")
            )
            channel_id = tags.get("oneshot_channel_id")
            status = tags.get("status")
            task_id = (tags.get("task_id") or "")[:128]
            if channel_id in channels and accepted and status in cls.ACCEPTED_STATUSES and task_id:
                channels[channel_id] = {
                    "status": status,
                    "task_id": task_id,
                    "retryable": False,
                }
        return channels

    @staticmethod
    def _process_succeeded(raw_result) -> bool:
        if not isinstance(raw_result, dict):
            return False
        if "success" in raw_result:
            return bool(raw_result["success"])
        if "exit_code" in raw_result:
            return raw_result["exit_code"] == 0
        return False

    @staticmethod
    def _exit_code(raw_result) -> int | None:
        if not isinstance(raw_result, dict) or "exit_code" not in raw_result:
            return None
        try:
            return int(raw_result["exit_code"])
        except (TypeError, ValueError):
            return None
