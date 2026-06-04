# -- coding: utf-8 --
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List

from .base_collector import BaseCollector

logger = logging.getLogger("stargazer.host_collector")

SCRIPTS_DIR = Path(__file__).parent / "scripts"

VALID_MODULES = {"cpu", "mem", "disk", "net"}


def build_script(os_type: str, modules: List[str]) -> str:
    base_dir = SCRIPTS_DIR / ("linux" if os_type == "linux" else "windows")
    ext = ".sh" if os_type == "linux" else ".ps1"

    parts = [_read_script(base_dir / f"header{ext}")]
    for mod in modules:
        script_file = base_dir / f"{mod}{ext}"
        if script_file.exists():
            parts.append(_read_script(script_file))
    parts.append(_read_script(base_dir / f"footer{ext}"))

    return "\n".join(parts)


def _read_script(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_metrics_to_prometheus(
    data: Dict[str, Any], instance_id: str, os_type: str
) -> str:
    lines = []
    timestamp = int(time.time() * 1000)
    base_labels = f'instance_id="{instance_id}",os_type="{os_type}"'

    if "cpu" in data:
        cpu = data["cpu"]
        lines.append(f"# HELP host_cpu_usage_percent CPU usage percentage")
        lines.append(f"# TYPE host_cpu_usage_percent gauge")
        lines.append(f"host_cpu_usage_percent{{{base_labels}}} {cpu.get('usage_percent', 0)} {timestamp}")
        lines.append(f"# HELP host_cpu_core_count CPU core count")
        lines.append(f"# TYPE host_cpu_core_count gauge")
        lines.append(f"host_cpu_core_count{{{base_labels}}} {cpu.get('core_count', 0)} {timestamp}")
        lines.append(f"# HELP host_cpu_load_1m CPU load 1 minute")
        lines.append(f"# TYPE host_cpu_load_1m gauge")
        lines.append(f"host_cpu_load_1m{{{base_labels}}} {cpu.get('load_1m', 0)} {timestamp}")
        lines.append(f"# HELP host_cpu_load_5m CPU load 5 minutes")
        lines.append(f"# TYPE host_cpu_load_5m gauge")
        lines.append(f"host_cpu_load_5m{{{base_labels}}} {cpu.get('load_5m', 0)} {timestamp}")
        lines.append(f"# HELP host_cpu_load_15m CPU load 15 minutes")
        lines.append(f"# TYPE host_cpu_load_15m gauge")
        lines.append(f"host_cpu_load_15m{{{base_labels}}} {cpu.get('load_15m', 0)} {timestamp}")

    if "mem" in data:
        mem = data["mem"]
        for key in ["total_bytes", "used_bytes", "available_bytes", "swap_total_bytes", "swap_used_bytes"]:
            metric_name = f"host_mem_{key}"
            lines.append(f"# HELP {metric_name} Memory {key}")
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name}{{{base_labels}}} {mem.get(key, 0)} {timestamp}")
        total_bytes = float(mem.get("total_bytes", 0) or 0)
        used_bytes = float(mem.get("used_bytes", 0) or 0)
        used_percent = round((used_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0
        lines.append(f"# HELP host_mem_used_percent Memory used percent")
        lines.append(f"# TYPE host_mem_used_percent gauge")
        lines.append(f"host_mem_used_percent{{{base_labels}}} {used_percent} {timestamp}")

    if "disk" in data:
        disks = data["disk"]
        if isinstance(disks, list):
            lines.append(f"# HELP host_disk_total_bytes Disk total bytes")
            lines.append(f"# TYPE host_disk_total_bytes gauge")
            lines.append(f"# HELP host_disk_used_bytes Disk used bytes")
            lines.append(f"# TYPE host_disk_used_bytes gauge")
            lines.append(f"# HELP host_disk_used_percent Disk used percent")
            lines.append(f"# TYPE host_disk_used_percent gauge")
            for disk in disks:
                mount = disk.get("mount", "unknown")
                disk_labels = f'{base_labels},mount="{mount}"'
                lines.append(f"host_disk_total_bytes{{{disk_labels}}} {disk.get('total_bytes', 0)} {timestamp}")
                lines.append(f"host_disk_used_bytes{{{disk_labels}}} {disk.get('used_bytes', 0)} {timestamp}")
                lines.append(f"host_disk_used_percent{{{disk_labels}}} {disk.get('used_percent', 0)} {timestamp}")

    if "net" in data:
        nets = data["net"]
        if isinstance(nets, list):
            lines.append(f"# HELP host_net_rx_bytes Network received bytes")
            lines.append(f"# TYPE host_net_rx_bytes gauge")
            lines.append(f"# HELP host_net_tx_bytes Network transmitted bytes")
            lines.append(f"# TYPE host_net_tx_bytes gauge")
            lines.append(f"# HELP host_net_rx_errors Network receive errors")
            lines.append(f"# TYPE host_net_rx_errors gauge")
            lines.append(f"# HELP host_net_tx_errors Network transmit errors")
            lines.append(f"# TYPE host_net_tx_errors gauge")
            for net in nets:
                iface = net.get("interface", "unknown")
                net_labels = f'{base_labels},interface="{iface}"'
                lines.append(f"host_net_rx_bytes{{{net_labels}}} {net.get('rx_bytes', 0)} {timestamp}")
                lines.append(f"host_net_tx_bytes{{{net_labels}}} {net.get('tx_bytes', 0)} {timestamp}")
                lines.append(f"host_net_rx_errors{{{net_labels}}} {net.get('rx_errors', 0)} {timestamp}")
                lines.append(f"host_net_tx_errors{{{net_labels}}} {net.get('tx_errors', 0)} {timestamp}")

    return "\n".join(lines) + "\n"


class HostCollector(BaseCollector):

    def _resolve_modules(self) -> List[str]:
        modules_str = self.params.get("metrics_modules", "cpu,mem,disk,net")
        modules = [m.strip() for m in modules_str.split(",") if m.strip() in VALID_MODULES]
        if not modules:
            modules = list(VALID_MODULES)
        return modules

    def _resolve_execution_config(self) -> Dict[str, Any]:
        host = self.params["host"]
        os_type = self.params.get("os_type", "linux")
        username = self.params["username"]
        password = self.params["password"]
        port = int(self.params.get("port", 22 if os_type == "linux" else 5986))
        ansible_node_id = self.params["ansible_node_id"]
        execute_timeout = int(self.params.get("execute_timeout", 60))

        modules = self._resolve_modules()

        logger.info(f"[Host Collector] host={host}, os={os_type}, modules={modules}")

        script = build_script(os_type, modules)

        connection = "ssh" if os_type == "linux" else "winrm"
        module = "shell" if os_type == "linux" else "win_shell"

        host_credentials = [{
            "host": host,
            "user": username,
            "password": password,
            "connection": connection,
            "port": port,
        }]

        return {
            "host": host,
            "os_type": os_type,
            "ansible_node_id": ansible_node_id,
            "host_credentials": host_credentials,
            "module": module,
            "module_args": script,
            "execute_timeout": execute_timeout,
        }

    async def submit_collection(
        self, task_id: str, callback_subject: str, callback_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        callback = dict(callback_payload or {})
        callback.update({"subject": callback_subject, "timeout": 10})
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

        try:
            metrics_data = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error(
                f"[Host Collector] JSON parse failed for {host}: {e}. "
                f"stdout preview: {stdout[:500]}"
            )
            raise RuntimeError(f"Failed to parse metrics JSON from {host}: {e}") from e

        instance_id = self.params.get("tags", {}).get("instance_id", host)
        prometheus_metrics = parse_metrics_to_prometheus(metrics_data, instance_id, os_type)

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
