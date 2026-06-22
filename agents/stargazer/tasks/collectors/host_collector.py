# -- coding: utf-8 --
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import unquote

from .base_collector import BaseCollector

logger = logging.getLogger("stargazer.host_collector")


def _url_decode_secret(value: Any) -> str:
    """还原前端对 encrypted 字段做的 encodeURIComponent。

    Web 端在提交时对标记为 encrypted 的字段（密码、SSH 私钥、passphrase）统一做了
    encodeURIComponent。这些值对于"拼进 URL"的插件是正确的，但主机远程采集是把它们
    直接当作 SSH/WinRM 凭据使用，必须先解码还原，否则像 ``CW@roger1117!@#`` 会以
    ``CW%40roger1117!%40%23`` 的形式送达，导致认证失败。

    解码是 encodeURIComponent 的逆运算，且 round-trip 安全：原文里的 ``%`` 会被前端
    编码成 ``%25``，因此 unquote 不会误伤含字面 ``%`` 的口令。
    """
    if not value:
        return value
    return unquote(str(value))

SCRIPTS_DIR = Path(__file__).parent / "scripts"

VALID_MODULES = {"cpu", "mem", "disk", "net", "diskio", "processes", "system"}
HOST_REMOTE_CALLBACK_REQUEST_TIMEOUT = 60
LINUX_SCRIPT_WRAPPER_EOF = "STARGAZER_HOST_COLLECT_EOF"


def build_script(os_type: str, modules: List[str]) -> str:
    base_dir = SCRIPTS_DIR / ("linux" if os_type == "linux" else "windows")
    ext = ".sh" if os_type == "linux" else ".ps1"

    parts = [_read_script(base_dir / f"header{ext}")]
    for mod in modules:
        script_file = base_dir / f"{mod}{ext}"
        if script_file.exists():
            parts.append(_read_script(script_file))
    parts.append(_read_script(base_dir / f"footer{ext}"))
    body = "\n".join(parts)

    if os_type == "linux":
        body = (
            f"bash <<'{LINUX_SCRIPT_WRAPPER_EOF}'\n"
            f"{body}\n"
            f"{LINUX_SCRIPT_WRAPPER_EOF}\n"
        )

    return body


def _read_script(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_json_payload(stdout: str) -> str:
    start = None
    depth = 0
    in_string = False
    escape = False

    for idx, char in enumerate(stdout):
        if start is None:
            if char == "{":
                start = idx
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = stdout[start : idx + 1]
                try:
                    json.loads(candidate)
                except json.JSONDecodeError:
                    start = None
                    continue
                return candidate

    return stdout


def _escape_prometheus_label_value(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_prometheus_labels(**labels: Any) -> str:
    return ",".join(
        f'{key}="{_escape_prometheus_label_value(value)}"'
        for key, value in labels.items()
    )


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _metric_value(data: Dict[str, Any], *keys: str, default: Any = 0) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _append_gauge(lines: List[str], name: str, labels: str, value: Any, timestamp: int, help_text: str = "") -> None:
    lines.append(f"# HELP {name} {help_text or name}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name}{{{labels}}} {value} {timestamp}")


def parse_metrics_to_prometheus(
    data: Dict[str, Any], instance_id: str, os_type: str, timestamp: int | None = None
) -> str:
    lines = []
    timestamp = int(timestamp) if timestamp is not None else int(time.time() * 1000)
    base_labels = _format_prometheus_labels(instance_id=instance_id, os_type=os_type)

    if "cpu" in data:
        cpu = data["cpu"]
        _append_gauge(lines, "host_cpu_usage_percent", base_labels, cpu.get("usage_percent", 0), timestamp, "CPU usage percentage")
        _append_gauge(lines, "cpu_usage_total", base_labels, cpu.get("usage_percent", 0), timestamp, "CPU usage percentage")
        _append_gauge(lines, "cpu_usage_user_total", base_labels, cpu.get("usage_user_percent", 0), timestamp, "CPU user usage percentage")
        _append_gauge(lines, "cpu_usage_system_total", base_labels, cpu.get("usage_system_percent", 0), timestamp, "CPU system usage percentage")
        _append_gauge(lines, "cpu_usage_iowait_total", base_labels, cpu.get("usage_iowait_percent", 0), timestamp, "CPU iowait usage percentage")
        _append_gauge(lines, "cpu_usage_irq_total", base_labels, cpu.get("usage_irq_percent", 0), timestamp, "CPU irq usage percentage")
        _append_gauge(lines, "cpu_usage_steal_total", base_labels, cpu.get("usage_steal_percent", 0), timestamp, "CPU steal usage percentage")
        _append_gauge(lines, "host_cpu_core_count", base_labels, cpu.get("core_count", 0), timestamp, "CPU core count")
        _append_gauge(lines, "host_cpu_load_1m", base_labels, cpu.get("load_1m", 0), timestamp, "CPU load 1 minute")
        _append_gauge(lines, "host_cpu_load_5m", base_labels, cpu.get("load_5m", 0), timestamp, "CPU load 5 minutes")
        _append_gauge(lines, "host_cpu_load_15m", base_labels, cpu.get("load_15m", 0), timestamp, "CPU load 15 minutes")
        _append_gauge(lines, "system_load1", base_labels, cpu.get("load_1m", 0), timestamp, "System load 1 minute")
        _append_gauge(lines, "system_load5", base_labels, cpu.get("load_5m", 0), timestamp, "System load 5 minutes")
        _append_gauge(lines, "system_load15", base_labels, cpu.get("load_15m", 0), timestamp, "System load 15 minutes")

    if "mem" in data:
        mem = data["mem"]
        for key in ["total_bytes", "used_bytes", "available_bytes", "swap_total_bytes", "swap_used_bytes"]:
            metric_name = f"host_mem_{key}"
            _append_gauge(lines, metric_name, base_labels, mem.get(key, 0), timestamp, f"Memory {key}")
        total_bytes = float(mem.get("total_bytes", 0) or 0)
        used_bytes = float(mem.get("used_bytes", 0) or 0)
        used_percent = round((used_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0
        swap_total = float(mem.get("swap_total_bytes", 0) or 0)
        swap_used = float(mem.get("swap_used_bytes", 0) or 0)
        swap_free = mem.get("swap_free_bytes", max(swap_total - swap_used, 0))
        _append_gauge(lines, "host_mem_used_percent", base_labels, used_percent, timestamp, "Memory used percent")
        _append_gauge(lines, "mem_total", base_labels, mem.get("total_bytes", 0), timestamp, "Memory total bytes")
        _append_gauge(lines, "mem_available", base_labels, mem.get("available_bytes", 0), timestamp, "Memory available bytes")
        _append_gauge(lines, "mem_used_percent", base_labels, used_percent, timestamp, "Memory used percent")
        _append_gauge(lines, "mem_swap_free", base_labels, swap_free, timestamp, "Swap free bytes")
        _append_gauge(lines, "mem_cached", base_labels, mem.get("cached_bytes", 0), timestamp, "Cached memory bytes")
        _append_gauge(lines, "mem_shared", base_labels, mem.get("shared_bytes", 0), timestamp, "Shared memory bytes")
        _append_gauge(lines, "mem_buffered", base_labels, mem.get("buffered_bytes", 0), timestamp, "Buffered memory bytes")

    if "disk" in data:
        disks = data["disk"]
        if isinstance(disks, list):
            for disk in disks:
                mount = disk.get("mount", "unknown")
                disk_labels = f"{base_labels},{_format_prometheus_labels(mount=mount)}"
                total = disk.get("total_bytes", 0)
                used = disk.get("used_bytes", 0)
                free = _metric_value(disk, "free_bytes", "available_bytes", default=max(float(total or 0) - float(used or 0), 0))
                used_percent = disk.get("used_percent", 0)
                _append_gauge(lines, "host_disk_total_bytes", disk_labels, total, timestamp, "Disk total bytes")
                _append_gauge(lines, "host_disk_used_bytes", disk_labels, used, timestamp, "Disk used bytes")
                _append_gauge(lines, "host_disk_used_percent", disk_labels, used_percent, timestamp, "Disk used percent")
                _append_gauge(lines, "disk_total", disk_labels, total, timestamp, "Disk total bytes")
                _append_gauge(lines, "disk_free", disk_labels, free, timestamp, "Disk free bytes")
                _append_gauge(lines, "disk_used_percent", disk_labels, used_percent, timestamp, "Disk used percent")
                _append_gauge(lines, "disk_inodes_used_percent", disk_labels, disk.get("inodes_used_percent", 0), timestamp, "Disk inode used percent")

    if "net" in data:
        nets = data["net"]
        if isinstance(nets, list):
            for net in nets:
                iface = net.get("interface", "unknown")
                net_labels = f"{base_labels},{_format_prometheus_labels(interface=iface)}"
                _append_gauge(lines, "host_net_rx_bytes", net_labels, net.get("rx_bytes", 0), timestamp, "Network received bytes")
                _append_gauge(lines, "host_net_tx_bytes", net_labels, net.get("tx_bytes", 0), timestamp, "Network transmitted bytes")
                _append_gauge(lines, "host_net_rx_errors", net_labels, net.get("rx_errors", 0), timestamp, "Network receive errors")
                _append_gauge(lines, "host_net_tx_errors", net_labels, net.get("tx_errors", 0), timestamp, "Network transmit errors")
                _append_gauge(lines, "net_bytes_recv", net_labels, net.get("rx_bytes", 0), timestamp, "Network received bytes counter")
                _append_gauge(lines, "net_bytes_sent", net_labels, net.get("tx_bytes", 0), timestamp, "Network transmitted bytes counter")
                _append_gauge(lines, "net_packets_recv", net_labels, net.get("rx_packets", 0), timestamp, "Network received packets counter")
                _append_gauge(lines, "net_packets_sent", net_labels, net.get("tx_packets", 0), timestamp, "Network transmitted packets counter")
                _append_gauge(lines, "net_err_in", net_labels, net.get("rx_errors", 0), timestamp, "Network receive errors counter")
                _append_gauge(lines, "net_err_out", net_labels, net.get("tx_errors", 0), timestamp, "Network transmit errors counter")
                _append_gauge(lines, "net_drop_in", net_labels, net.get("rx_drops", 0), timestamp, "Network receive drops counter")
                _append_gauge(lines, "net_drop_out", net_labels, net.get("tx_drops", 0), timestamp, "Network transmit drops counter")
                _append_gauge(lines, "net_bytes_recv_total", net_labels, net.get("rx_bytes", 0), timestamp, "Network received bytes counter")
                _append_gauge(lines, "net_bytes_sent_total", net_labels, net.get("tx_bytes", 0), timestamp, "Network transmitted bytes counter")
                _append_gauge(lines, "net_packets_recv_total", net_labels, net.get("rx_packets", 0), timestamp, "Network received packets counter")
                _append_gauge(lines, "net_packets_sent_total", net_labels, net.get("tx_packets", 0), timestamp, "Network transmitted packets counter")
                _append_gauge(lines, "net_err_in_total", net_labels, net.get("rx_errors", 0), timestamp, "Network receive errors counter")
                _append_gauge(lines, "net_err_out_total", net_labels, net.get("tx_errors", 0), timestamp, "Network transmit errors counter")
                _append_gauge(lines, "net_drop_in_total", net_labels, net.get("rx_drops", 0), timestamp, "Network receive drops counter")
                _append_gauge(lines, "net_drop_out_total", net_labels, net.get("tx_drops", 0), timestamp, "Network transmit drops counter")

    if "diskio" in data and isinstance(data["diskio"], list):
        for diskio in data["diskio"]:
            device = diskio.get("device", "unknown")
            diskio_labels = f"{base_labels},{_format_prometheus_labels(device=device)}"
            _append_gauge(lines, "diskio_reads_total", diskio_labels, diskio.get("reads", 0), timestamp, "Disk reads counter")
            _append_gauge(lines, "diskio_writes_total", diskio_labels, diskio.get("writes", 0), timestamp, "Disk writes counter")
            _append_gauge(lines, "diskio_read_bytes_total", diskio_labels, diskio.get("read_bytes", 0), timestamp, "Disk read bytes counter")
            _append_gauge(lines, "diskio_write_bytes_total", diskio_labels, diskio.get("write_bytes", 0), timestamp, "Disk write bytes counter")
            _append_gauge(lines, "diskio_io_time_ms", diskio_labels, diskio.get("io_time_ms", 0), timestamp, "Disk IO time ms")
            _append_gauge(lines, "disk_read_latency", diskio_labels, diskio.get("read_time_ms", 0), timestamp, "Disk read time ms")
            _append_gauge(lines, "disk_write_latency", diskio_labels, diskio.get("write_time_ms", 0), timestamp, "Disk write time ms")

    if "processes" in data and isinstance(data["processes"], dict):
        processes = data["processes"]
        for key in ("running", "blocked", "zombies", "sleeping"):
            _append_gauge(lines, f"processes_{key}", base_labels, processes.get(key, 0), timestamp, f"Processes {key}")

    if "system" in data and isinstance(data["system"], dict):
        system = data["system"]
        _append_gauge(lines, "system_uptime", base_labels, system.get("uptime_seconds", 0), timestamp, "System uptime seconds")
        _append_gauge(lines, "system_load1", base_labels, system.get("load1", system.get("load_1m", 0)), timestamp, "System load 1 minute")
        _append_gauge(lines, "system_load5", base_labels, system.get("load5", system.get("load_5m", 0)), timestamp, "System load 5 minutes")
        _append_gauge(lines, "system_load15", base_labels, system.get("load15", system.get("load_15m", 0)), timestamp, "System load 15 minutes")

    return "\n".join(lines) + "\n"


class HostCollector(BaseCollector):

    def _resolve_modules(self) -> List[str]:
        raw_modules = self.params.get("metrics_modules", "cpu,mem,disk,net")
        if isinstance(raw_modules, (list, tuple)):
            module_items = raw_modules
        else:
            module_items = str(raw_modules).split(",")
        modules = [str(m).strip() for m in module_items if str(m).strip() in VALID_MODULES]
        if not modules:
            modules = ["cpu", "mem", "disk", "net"]
        return modules

    def _resolve_execution_config(self) -> Dict[str, Any]:
        host = self.params["host"]
        os_type = self.params.get("os_type", "linux")
        username = self.params["username"]
        raw_port = self.params.get("port")
        port = int(raw_port) if raw_port not in (None, "") else (22 if os_type == "linux" else 5986)
        ansible_node_id = self.params["ansible_node_id"]
        execute_timeout = int(self.params.get("execute_timeout", 60))

        modules = self._resolve_modules()

        logger.info(f"[Host Collector] host={host}, os={os_type}, modules={modules}")

        script = build_script(os_type, modules)

        connection = "ssh" if os_type == "linux" else "winrm"
        module = "shell" if os_type == "linux" else "win_shell"

        host_credential = {
            "host": host,
            "user": username,
            "connection": connection,
            "port": port,
        }
        if os_type == "linux":
            auth_type = self.params.get("auth_type", "password") or "password"
            if auth_type == "private_key":
                private_key_content = self.params.get("private_key_content")
                if private_key_content:
                    host_credential["private_key_content"] = _url_decode_secret(private_key_content)
                private_key_passphrase = self.params.get("private_key_passphrase")
                if private_key_passphrase:
                    host_credential["private_key_passphrase"] = _url_decode_secret(private_key_passphrase)
            else:
                host_credential["password"] = _url_decode_secret(self.params.get("password", ""))
        else:
            host_credential["password"] = _url_decode_secret(self.params.get("password", ""))
            host_credential["winrm_scheme"] = self.params.get("winrm_scheme") or "https"
            host_credential["winrm_transport"] = self.params.get("winrm_transport") or "ntlm"
            host_credential["winrm_cert_validation"] = _as_bool(
                self.params.get("winrm_cert_validation"),
                default=False,
            )

        host_credentials = [host_credential]

        return {
            "host": host,
            "os_type": os_type,
            "ansible_node_id": ansible_node_id,
            "host_credentials": host_credentials,
            "module": module,
            "module_args": script,
            "execute_timeout": execute_timeout,
        }

    def _resolve_callback_timeout(self) -> int:
        return int(
            self.params.get(
                "host_remote_callback_timeout",
                HOST_REMOTE_CALLBACK_REQUEST_TIMEOUT,
            )
        )

    async def submit_collection(
        self, task_id: str, callback_subject: str, callback_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        callback = dict(callback_payload or {})
        callback.update(
            {
                "subject": callback_subject,
                "timeout": self._resolve_callback_timeout(),
            }
        )
        return await self._execute_collection(
            callback=callback,
            task_id=task_id,
        )

    async def _execute_collection(
        self, callback: Dict[str, Any] | None = None, task_id: str | None = None
    ) -> Dict[str, Any]:
        from core.ansible_rpc import ansible_adhoc

        config = self._resolve_execution_config()
        return await ansible_adhoc(
            ansible_node_id=config["ansible_node_id"],
            host_credentials=config["host_credentials"],
            module=config["module"],
            module_args=config["module_args"],
            execute_timeout=config["execute_timeout"],
            callback=callback,
            task_id=task_id,
        )

    def process_adhoc_result(self, result: Dict[str, Any]) -> str:
        host = self.params["host"]
        os_type = self.params.get("os_type", "linux")

        if not result.get("success"):
            error_msg = result.get("error") or result.get("message") or "Ansible adhoc failed"
            logger.error(f"[Host Collector] Ansible adhoc failed for {host}: {error_msg}")
            raise RuntimeError(f"Host collection failed: {error_msg}")

        stdout = self._extract_stdout(result)
        if not stdout or not stdout.strip():
            logger.error(f"[Host Collector] Empty stdout from {host}, result keys: {list(result.keys())}")
            raise RuntimeError(f"Host collection returned empty stdout for {host}")

        cleaned_stdout = stdout.strip()

        try:
            metrics_data = json.loads(cleaned_stdout)
        except json.JSONDecodeError as e:
            extracted_payload = _extract_json_payload(cleaned_stdout)
            if extracted_payload != cleaned_stdout:
                try:
                    metrics_data = json.loads(extracted_payload)
                except json.JSONDecodeError:
                    logger.error(
                        f"[Host Collector] JSON parse failed for {host}: {e}. "
                        f"stdout preview: {stdout[:500]}"
                    )
                    raise RuntimeError(f"Failed to parse metrics JSON from {host}: {e}") from e
            else:
                logger.error(
                    f"[Host Collector] JSON parse failed for {host}: {e}. "
                    f"stdout preview: {stdout[:500]}"
                )
                raise RuntimeError(f"Failed to parse metrics JSON from {host}: {e}") from e

        instance_id = self.params.get("tags", {}).get("instance_id", host)
        callback_timestamp = self.params.get("callback_timestamp")
        prometheus_metrics = parse_metrics_to_prometheus(
            metrics_data,
            instance_id,
            os_type,
            timestamp=callback_timestamp,
        )

        logger.info(f"[Host Collector] Completed: host={host}, metrics_size={len(prometheus_metrics)}")
        return prometheus_metrics

    async def collect(self) -> str:
        result = await self._execute_collection()
        return self.process_adhoc_result(result)

    def _extract_stdout(self, result: Dict[str, Any]) -> str:
        task_result = result.get("result", {})
        if isinstance(task_result, str):
            return task_result
        if isinstance(task_result, list):
            expected_host = self.params.get("host")
            fallback_stdout = ""
            for host_data in task_result:
                if not isinstance(host_data, dict):
                    continue
                stdout = host_data.get("stdout", "")
                host_key = host_data.get("host", "")
                if stdout and host_key == expected_host:
                    return stdout
                if stdout and not fallback_stdout:
                    fallback_stdout = stdout
                if not stdout:
                    logger.warning(
                        f"[Host Collector] No stdout for host_key={host_key}, "
                        f"status={host_data.get('status')}, stderr={host_data.get('stderr', '')[:200]}"
                    )
            return fallback_stdout
        if isinstance(task_result, dict):
            hosts_result = task_result.get("contacted", task_result)
            for host_key, host_data in hosts_result.items():
                if isinstance(host_data, dict):
                    stdout = host_data.get("stdout", "")
                    if not stdout:
                        logger.warning(
                            f"[Host Collector] No stdout for host_key={host_key}, "
                            f"rc={host_data.get('rc')}, stderr={host_data.get('stderr', '')[:200]}"
                        )
                    return stdout
            logger.warning(f"[Host Collector] No contacted hosts in result, keys: {list(hosts_result.keys())}")
            return json.dumps(task_result)
        return str(task_result)
