# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from core.logger import logger
from plugins.script_executor import SSHPlugin


class HostInfo(SSHPlugin):
    async def list_all_resources(self, need_raw=False) -> Dict[str, Any]:
        try:
            logger.debug(
                "event=host_collect_started host=%s model_id=%s task_id=%s",
                self.host,
                self.model_id,
                self.collection_task_id,
            )
            data = await super().list_all_resources(need_raw=True)

            if need_raw:
                return data

            if not data.get("success"):
                return data

            collect_output = data.get("result", "")
            parsed_payload = self._parse_collect_output(collect_output)
            if not parsed_payload:
                return {"success": True, "result": {}}

            host_items: List[Dict[str, Any]] = []
            host_proc_items: List[Dict[str, Any]] = []
            host_mount_items: List[Dict[str, Any]] = []
            host_nic_items: List[Dict[str, Any]] = []

            for item in parsed_payload:
                if not isinstance(item, dict):
                    continue

                host_item = dict(item)
                if self.host and not host_item.get("ip_addr"):
                    host_item["ip_addr"] = self.host
                proc_items = host_item.pop("proc", [])
                mount_items = host_item.pop("mounts", [])
                nic_items = host_item.pop("nics", [])

                host_items.append(host_item)

                host_inst_name = host_item.get("host") or host_item.get("ip_addr") or self.host or ""
                ip_addr = host_item.get("ip_addr") or self.host or ""
                host_proc_items.extend(self._child_rows(proc_items, host_inst_name, ip_addr))
                host_mount_items.extend(self._child_rows(mount_items, host_inst_name, ip_addr))
                host_nic_items.extend(self._child_rows(nic_items, host_inst_name, ip_addr))

            result = {self.model_id: host_items}
            if host_proc_items:
                result["host_proc_usage"] = host_proc_items
            if host_mount_items:
                result["host_mount"] = host_mount_items
            if host_nic_items:
                result["host_nic"] = host_nic_items
            logger.info(
                "event=host_collect_completed success=%s host=%s model_id=%s task_id=%s host_count=%s proc_count=%s",
                True,
                self.host,
                self.model_id,
                self.collection_task_id,
                len(host_items),
                len(host_proc_items),
            )
            return {"success": True, "result": result}
        except Exception as err:
            logger.exception(
                "event=host_collect_failed host=%s model_id=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.model_id,
                self.collection_task_id,
                "host_parse",
                type(err).__name__,
            )
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}

    @staticmethod
    def _child_rows(raw_items, host_inst_name: str, ip_addr: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not isinstance(raw_items, list):
            return rows
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            row["self_device"] = host_inst_name
            row["ip_addr"] = ip_addr
            rows.append(row)
        return rows
