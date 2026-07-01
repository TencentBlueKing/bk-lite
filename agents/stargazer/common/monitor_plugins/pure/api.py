import logging

from core.monitor.base import ApiMonitor
from common.monitor_plugins.storage_utils import store_metric, store_metric_group

logger = logging.getLogger("monitor")

_SUPPORTED_API_VERSIONS = ("1.19", "1.18", "1.17", "1.16", "1.15", "1.11", "1.6")
_USEC_TO_MS = 1000.0


class PureApiMonitor(ApiMonitor):
    code = "pure-api"

    array_perf_map = {
        "pure_array_read_iops": "reads_per_sec",
        "pure_array_write_iops": "writes_per_sec",
        "pure_array_read_bandwidth": "output_per_sec",
        "pure_array_write_bandwidth": "input_per_sec",
        "pure_array_queue_depth": "queue_depth",
    }
    array_latency_map = {
        "pure_array_read_latency": "usec_per_read_op",
        "pure_array_write_latency": "usec_per_write_op",
    }
    array_space_map = {
        "pure_array_capacity_bytes": "capacity",
        "pure_array_used_bytes": "total",
        "pure_array_volumes_bytes": "volumes",
        "pure_array_snapshots_bytes": "snapshots",
        "pure_array_shared_space_bytes": "shared_space",
        "pure_array_data_reduction": "data_reduction",
        "pure_array_total_reduction": "total_reduction",
    }
    volume_perf_map = {
        "pure_volume_read_iops": "reads_per_sec",
        "pure_volume_write_iops": "writes_per_sec",
        "pure_volume_read_bandwidth": "output_per_sec",
        "pure_volume_write_bandwidth": "input_per_sec",
    }
    volume_latency_map = {
        "pure_volume_read_latency": "usec_per_read_op",
        "pure_volume_write_latency": "usec_per_write_op",
    }
    volume_space_map = {
        "pure_volume_size_bytes": "size",
        "pure_volume_used_bytes": "volumes",
    }

    def __init__(self, input_data):
        super().__init__(input_data)
        self.api_version = None

    def _negotiate_version(self):
        try:
            resp = self.api.request("GET", "/api/api_version", verify=False)
            versions = resp.get("version", []) if isinstance(resp, dict) else []
            for version in _SUPPORTED_API_VERSIONS:
                if version in versions:
                    return version
            if versions:
                return sorted(versions)[-1]
        except Exception as err:
            logger.warning("Pure api version negotiation failed: %s", err)
        return _SUPPORTED_API_VERSIONS[0]

    def login(self):
        self.api_version = self._negotiate_version()
        username = self.config.get("username")
        password = self.config.get("password")
        token_resp = self.api.request(
            "POST",
            f"/api/{self.api_version}/auth/apitoken",
            json={"username": username, "password": password},
            verify=False,
        )
        api_token = (token_resp or {}).get("api_token")
        if not api_token:
            raise RuntimeError("Pure login failed: no api token returned")
        self.api.request(
            "POST",
            f"/api/{self.api_version}/auth/session",
            json={"api_token": api_token},
            verify=False,
        )

    def logout(self):
        try:
            if self.api_version:
                self.api.request(
                    "DELETE", f"/api/{self.api_version}/auth/session", verify=False
                )
        except Exception as err:
            logger.warning("Pure logout failed and was ignored: %s", err)
        finally:
            self.api.logout()

    def _get_list(self, path, params=None):
        resp = self.api.request(
            "GET", f"/api/{self.api_version}/{path}", params=params, verify=False
        )
        return resp if isinstance(resp, list) else []

    def process_array(self):
        for item in self._get_list("array", params={"action": "monitor"}):
            store_metric_group(self.data, self.resource_id, item, self.array_perf_map)
            store_metric_group(
                self.data,
                self.resource_id,
                item,
                self.array_latency_map,
                divisor=_USEC_TO_MS,
            )
        for item in self._get_list("array", params={"space": "true"}):
            store_metric_group(self.data, self.resource_id, item, self.array_space_map)

    def process_volumes(self):
        volume_names = set()
        for item in self._get_list("volume", params={"action": "monitor"}):
            name = item.get("name")
            if not name:
                continue
            volume_names.add(name)
            dims = (("volume", str(name)),)
            store_metric_group(self.data, self.resource_id, item, self.volume_perf_map, dims=dims)
            store_metric_group(
                self.data,
                self.resource_id,
                item,
                self.volume_latency_map,
                dims=dims,
                divisor=_USEC_TO_MS,
            )
        for item in self._get_list("volume", params={"space": "true"}):
            name = item.get("name")
            if not name:
                continue
            volume_names.add(name)
            store_metric_group(
                self.data,
                self.resource_id,
                item,
                self.volume_space_map,
                dims=(("volume", str(name)),),
            )
        if volume_names:
            store_metric(self.data, self.resource_id, "pure_volume_count", len(volume_names))

    def run(self):
        self.data = {}
        self.login()
        try:
            self.process_array()
            self.process_volumes()
        finally:
            self.logout()
