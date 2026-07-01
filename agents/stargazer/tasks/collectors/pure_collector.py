import asyncio

from sanic.log import logger

from .base_collector import BaseCollector
from common.monitor_plugins.storage_utils import ensure_storage_metrics


class PureCollector(BaseCollector):
    async def collect(self) -> str:
        from common.monitor_plugins.pure.api import PureApiMonitor
        from utils.convert import convert_to_prometheus

        username = self.params["username"]
        password = self.params["password"]
        host = self.params.get("host") or self.params.get("base_url", "")
        instance_id = self.params.get("instance_id", host)
        base_url = f"https://{host}" if host and not host.startswith("http") else host

        logger.info("[Pure Collector] Host=%s, User=%s", host, username)

        monitor = PureApiMonitor(
            {
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
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, monitor.execute)
        ensure_storage_metrics(monitor.data)

        metric_dict = {
            (resource_id, "pure"): metrics
            for resource_id, metrics in monitor.data.items()
        }
        result = "\n".join(convert_to_prometheus(metric_dict)) + "\n"
        logger.info("[Pure Collector] Completed: %s bytes", len(result))
        return result
