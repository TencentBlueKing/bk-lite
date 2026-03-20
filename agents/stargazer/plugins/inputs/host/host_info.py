# -*- coding: utf-8 -*-
import json
from typing import Any, Dict, List

from sanic.log import logger

from plugins.script_executor import SSHPlugin


class HostInfo(SSHPlugin):

    async def list_all_resources(self, need_raw=False) -> Dict[str, Any]:
        try:
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

            return {"success": True, "result": result}
        except Exception as err:
            import traceback
            logger.error(f"{self.__class__.__name__} main error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
