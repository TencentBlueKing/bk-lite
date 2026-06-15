import logging
import time
from typing import Any

from .base_collector import BaseCollector
from .host_wmi.client import WmiClient
from .host_wmi.errors import classify_wmi_error
from .host_wmi.metrics import wmi_results_to_prometheus
from .host_wmi.modules import MODULE_REGISTRY, resolve_modules

logger = logging.getLogger("stargazer.windows_wmi")


class WindowsWmiCollector(BaseCollector):
    def _context(self) -> dict[str, Any]:
        tags = self.params.get("tags") or {}
        return {
            "monitor_type": "windows_wmi",
            "host": self.params.get("host"),
            "instance_id": tags.get("instance_id") or self.params.get("host"),
            "modules": ",".join(resolve_modules(self.params.get("metrics_modules"))),
        }

    def _client(self) -> WmiClient:
        return WmiClient(
            host=self.params["host"],
            username=self.params["username"],
            password=self.params["password"],
            namespace=self.params.get("namespace") or "root\\cimv2",
            timeout=int(self.params.get("timeout") or 60),
        )

    async def collect(self) -> str:
        context = self._context()
        modules = resolve_modules(self.params.get("metrics_modules"))
        logger.info("event=wmi_collect_start %s", context)
        started = time.monotonic()
        client = self._client()

        try:
            logger.info("event=wmi_connect_start %s", context)
            client.connect()
            logger.info("event=wmi_connect_success %s", context)
        except Exception as error:
            error_type = classify_wmi_error(error)
            logger.error("event=wmi_connect_failed error_type=%s %s", error_type, context, exc_info=True)
            raise

        results: dict[str, Any] = {}
        try:
            for module_name in modules:
                module_started = time.monotonic()
                logger.info("event=wmi_module_start module=%s %s", module_name, context)
                module = MODULE_REGISTRY[module_name]()
                try:
                    results[module_name] = module.collect(client)
                    duration_ms = int((time.monotonic() - module_started) * 1000)
                    logger.info("event=wmi_module_success module=%s duration_ms=%s %s", module_name, duration_ms, context)
                except Exception as error:
                    duration_ms = int((time.monotonic() - module_started) * 1000)
                    error_type = classify_wmi_error(error)
                    logger.warning(
                        "event=wmi_module_failed module=%s error_type=%s duration_ms=%s %s",
                        module_name,
                        error_type,
                        duration_ms,
                        context,
                        exc_info=True,
                    )
        finally:
            client.close()

        if not results:
            raise RuntimeError("Windows WMI collection returned no module data")

        output = wmi_results_to_prometheus(
            results,
            self.params.get("tags") or {},
            host=self.params["host"],
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info("event=wmi_collect_success duration_ms=%s %s", duration_ms, context)
        return output
