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

            for item in parsed_payload:
                if not isinstance(item, dict):
                    continue

                host_item = dict(item)
                if self.host and not host_item.get("ip_addr"):
                    host_item["ip_addr"] = self.host
                proc_items = host_item.pop("proc", [])

                host_items.append(host_item)

                if isinstance(proc_items, list):
                    host_inst_name = host_item.get("host") or host_item.get("ip_addr") or self.host or ""
                    ip_addr = host_item.get("ip_addr") or self.host or ""
                    for proc in proc_items:
                        if not isinstance(proc, dict):
                            continue
                        proc_item = dict(proc)
                        proc_item["self_device"] = host_inst_name
                        proc_item["ip_addr"] = ip_addr
                        host_proc_items.append(proc_item)

            result = {self.model_id: host_items}
            if host_proc_items:
                result["host_proc_usage"] = host_proc_items
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
