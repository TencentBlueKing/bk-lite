import asyncio
from typing import Dict, Any
from sanic.log import logger
from .base_collector import BaseCollector


class OceanStorCollector(BaseCollector):
    async def collect(self) -> str:
        from common.monitor_plugins.oceanstor.api import OceanStorApiMonitor
        from utils.convert import convert_to_prometheus

        username = self.params["username"]
        password = self.params["password"]
        host = self.params["host"]
        instance_id = self.params.get("instance_id", host)

        logger.info(f"[OceanStor Collector] Host={host}, User={username}")

        base_url = f"https://{host}" if not host.startswith("http") else host

        monitor_input = {
            "config": {
                "base_url": base_url,
                "username": username,
                "password": password,
            },
            "resource": {
                "bk_inst_id": instance_id,
                "metrics": [],
            },
            "interval": 300,
            "timeout": 60,
        }

        monitor = OceanStorApiMonitor(monitor_input)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, monitor.execute)

        if not monitor.data:
            logger.warning("[OceanStor Collector] No data collected")
            return ""

        metric_dict = {}
        for resource_id, metrics in monitor.data.items():
            metric_dict[(resource_id, "oceanstor")] = metrics

        metric_list = convert_to_prometheus(metric_dict)
        result = "\n".join(metric_list) + "\n"

        logger.info(f"[OceanStor Collector] Completed: {len(result)} bytes")

        return result
