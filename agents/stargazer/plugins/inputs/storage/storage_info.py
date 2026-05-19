from sanic.log import logger

from plugins.inputs.storage.brands import get_brand_collector


class StorageCollector:
    def __init__(self, params: dict):
        self.params = params
        self.brand = params.get("brand", "").lower()
        self.host = params.get("host")
        self.username = params.get("username")
        self.password = params.get("password")

    def collect(self) -> dict:
        logger.info(f"[Storage] brand={self.brand}, host={self.host}")

        collector_cls = get_brand_collector(self.brand)
        if not collector_cls:
            raise ValueError(f"Unsupported storage brand: {self.brand}")

        collector = collector_cls(self.params)
        return collector.collect()
