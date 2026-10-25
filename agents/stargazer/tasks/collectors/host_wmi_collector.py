import asyncio
import logging
import time
from typing import Any

from .base_collector import BaseCollector
from .host_wmi.client import WmiClient
from .host_wmi.errors import classify_wmi_error
from .host_wmi.metrics import wmi_results_to_prometheus
from .host_wmi.modules import MODULE_REGISTRY, ServiceModule, resolve_modules
from .windows_service import should_collect_windows_service

logger = logging.getLogger("stargazer.windows_wmi")


class WindowsWmiCollector(BaseCollector):
    def _context(self) -> dict[str, Any]:
        tags = self.params.get("tags") or {}
        return {
            "monitor_type": "windows_wmi",
            "host": self.params.get("host"),
            "instance_id": tags.get("instance_id") or self.params.get("host"),
            "modules": ",".join(self._resolve_collect_modules()),
        }

    def _resolve_collect_modules(self) -> list[str]:
        modules = resolve_modules(self.params.get("metrics_modules"))
        if should_collect_windows_service(self.params.get("service_scope"), self.params.get("service_names")):
            if "service" not in modules:
                modules = [*modules, "service"]
        else:
            modules = [name for name in modules if name != "service"]
        return modules

    def _client(self) -> WmiClient:
        return WmiClient(
            host=self.params["host"],
            username=self.params["username"],
            password=self.params["password"],
            namespace=self.params.get("namespace") or "root\\cimv2",
            timeout=int(self.params.get("timeout") or 60),
        )

    async def collect(self) -> str:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> str:
        context = self._context()
        modules = self._resolve_collect_modules()
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
                if module_name == "service":
                    module = ServiceModule(
                        service_scope=self.params.get("service_scope"),
                        service_names=self.params.get("service_names"),
                    )
                else:
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
            disk_include_fstypes=self.params.get("disk_include_fstypes"),
            disk_exclude_fstypes=self.params.get("disk_exclude_fstypes"),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info("event=wmi_collect_success duration_ms=%s %s", duration_ms, context)
        return output
