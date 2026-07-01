import logging
import time

from core.monitor.base import ApiMonitor
from common.monitor_plugins.storage_utils import (
    store_metric,
    store_metric_group,
    to_float,
)

logger = logging.getLogger("monitor")

_PAGE_SIZE = 1000
_MAX_VOLUME_COUNTERS = 500


def _rate(previous, current, field, elapsed_seconds):
    previous_value = to_float(previous.get(field))
    current_value = to_float(current.get(field))
    if previous_value is None or current_value is None or elapsed_seconds <= 0:
        return None
    delta = current_value - previous_value
    if delta < 0:
        return None
    return round(delta / elapsed_seconds, 3)


def _average_latency_ms(previous, current, latency_field, ops_field):
    previous_latency = to_float(previous.get(latency_field))
    current_latency = to_float(current.get(latency_field))
    previous_ops = to_float(previous.get(ops_field))
    current_ops = to_float(current.get(ops_field))
    if None in (previous_latency, current_latency, previous_ops, current_ops):
        return None
    latency_delta = current_latency - previous_latency
    ops_delta = current_ops - previous_ops
    if latency_delta < 0 or ops_delta <= 0:
        return None
    return round((latency_delta / ops_delta) / 1000.0, 3)


def calculate_counter_rates(previous, current, elapsed_seconds):
    rates = {}
    field_map = {
        "infinibox_volume_read_iops": ("read_ops", elapsed_seconds),
        "infinibox_volume_write_iops": ("write_ops", elapsed_seconds),
        "infinibox_volume_read_bandwidth": ("read_bytes", elapsed_seconds),
        "infinibox_volume_write_bandwidth": ("write_bytes", elapsed_seconds),
    }
    for metric_name, (field, seconds) in field_map.items():
        value = _rate(previous, current, field, seconds)
        if value is not None:
            rates[metric_name] = value

    read_latency = _average_latency_ms(previous, current, "read_latency", "read_ops")
    if read_latency is not None:
        rates["infinibox_volume_read_latency"] = read_latency

    write_latency = _average_latency_ms(previous, current, "write_latency", "write_ops")
    if write_latency is not None:
        rates["infinibox_volume_write_latency"] = write_latency

    total_latency = _average_latency_ms(previous, current, "latency", "ops")
    if total_latency is not None:
        rates["infinibox_volume_latency"] = total_latency

    return rates


class InfiniBoxApiMonitor(ApiMonitor):
    code = "infinibox-api"

    volume_space_map = {
        "infinibox_volume_size_bytes": "size",
        "infinibox_volume_used_bytes": "allocated",
    }
    pool_space_map = {
        "infinibox_pool_physical_capacity_bytes": "physical_capacity",
        "infinibox_pool_allocated_physical_bytes": "allocated_physical_space",
        "infinibox_pool_free_physical_bytes": "free_physical_space",
        "infinibox_pool_virtual_capacity_bytes": "virtual_capacity",
        "infinibox_pool_allocated_virtual_bytes": "allocated_virtual_space",
    }

    def __init__(self, input_data):
        super().__init__(input_data)
        self.sample_seconds = max(
            1, int(self.config.get("sample_seconds") or input_data.get("sample_seconds", 5))
        )
        self.max_volume_counters = int(
            self.config.get("max_volume_counters") or _MAX_VOLUME_COUNTERS
        )

    def login(self):
        self.api.request(
            "POST",
            "/api/rest/users/login",
            json={
                "username": self.config.get("username"),
                "password": self.config.get("password"),
            },
            verify=False,
        )

    def logout(self):
        try:
            self.api.request("POST", "/api/rest/users/logout", verify=False)
        except Exception as err:
            logger.warning("InfiniBox logout failed and was ignored: %s", err)
        finally:
            self.api.logout()

    def _get_result(self, path, params=None):
        resp = self.api.request("GET", f"/api/rest/{path}", params=params, verify=False)
        if isinstance(resp, dict):
            error = resp.get("error")
            if error:
                raise RuntimeError(f"InfiniBox API error on {path}: {error}")
            return resp.get("result")
        return None

    def _list(self, path):
        items = []
        page = 1
        while True:
            result = self._get_result(
                path, params={"page_size": _PAGE_SIZE, "page": page}
            )
            if not isinstance(result, list) or not result:
                break
            items.extend(result)
            if len(result) < _PAGE_SIZE:
                break
            page += 1
        return items

    def process_pools(self):
        pools = self._list("pools")
        for pool in pools:
            name = pool.get("name") or pool.get("id")
            if name in (None, ""):
                continue
            store_metric_group(
                self.data,
                self.resource_id,
                pool,
                self.pool_space_map,
                dims=(("pool", str(name)),),
            )
        if pools:
            store_metric(self.data, self.resource_id, "infinibox_pool_count", len(pools))

    def _volume_counter_snapshot(self, volumes):
        snapshot = {}
        for volume in volumes[: self.max_volume_counters]:
            vol_id = volume.get("id")
            name = volume.get("name") or vol_id
            if vol_id in (None, "") or name in (None, ""):
                continue
            counters = self._get_result(f"counters/volumes/{vol_id}/total")
            if isinstance(counters, dict):
                snapshot[str(name)] = counters
        return snapshot

    def process_volumes(self):
        volumes = self._list("volumes")
        if volumes:
            store_metric(self.data, self.resource_id, "infinibox_volume_count", len(volumes))

        for volume in volumes[: self.max_volume_counters]:
            name = volume.get("name") or volume.get("id")
            if name in (None, ""):
                continue
            store_metric_group(
                self.data,
                self.resource_id,
                volume,
                self.volume_space_map,
                dims=(("volume", str(name)),),
            )

        first = self._volume_counter_snapshot(volumes)
        if not first:
            return
        time.sleep(self.sample_seconds)
        second = self._volume_counter_snapshot(volumes)
        for volume_name, current in second.items():
            previous = first.get(volume_name)
            if not previous:
                continue
            dims = (("volume", volume_name),)
            for metric_name, value in calculate_counter_rates(
                previous, current, self.sample_seconds
            ).items():
                store_metric(self.data, self.resource_id, metric_name, value, dims=dims)

        if len(volumes) > self.max_volume_counters:
            logger.warning(
                "InfiniBox volume count %s exceeds cap %s; counters truncated",
                len(volumes),
                self.max_volume_counters,
            )

    def run(self):
        self.data = {}
        self.login()
        try:
            self.process_pools()
            self.process_volumes()
        finally:
            self.logout()
