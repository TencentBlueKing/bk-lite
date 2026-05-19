from sanic.log import logger

from common.monitor_plugins.oceanstor.api import OceanStorApiMonitor


class OceanStorBrandCollector:
    def __init__(self, params: dict):
        self.params = params
        self.host = params.get("host")
        self.username = params.get("username")
        self.password = params.get("password")
        self.instance_id = params.get("instance_id", self.host)

    def collect(self) -> dict:
        base_url = (
            f"https://{self.host}" if not self.host.startswith("http") else self.host
        )

        monitor_input = {
            "config": {
                "base_url": base_url,
                "username": self.username,
                "password": self.password,
            },
            "resource": {
                "bk_inst_id": self.instance_id,
                "metrics": [],
            },
            "interval": 300,
            "timeout": 60,
        }

        monitor = OceanStorApiMonitor(monitor_input)
        monitor.execute()

        if not monitor.data:
            logger.warning("[OceanStor Brand] No data collected")
            return {}

        return self._format_result(monitor.data)

    def _format_result(self, data: dict) -> dict:
        result = {}
        for resource_id, metrics in data.items():
            records = []
            for metric_name, metric_data in metrics.items():
                if isinstance(metric_data, dict):
                    for dims, values in metric_data.items():
                        if not values:
                            continue
                        timestamp, value = values[-1]
                        record = {
                            "metric": metric_name,
                            "value": value,
                            "timestamp": timestamp,
                        }
                        for dim_key, dim_value in dims:
                            record[dim_key] = dim_value
                        records.append(record)
                elif isinstance(metric_data, list) and metric_data:
                    timestamp, value = metric_data[-1]
                    records.append(
                        {
                            "metric": metric_name,
                            "value": value,
                            "timestamp": timestamp,
                        }
                    )
            result["storage"] = records
        return result
