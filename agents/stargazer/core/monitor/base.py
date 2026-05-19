import time
import logging
from collections import OrderedDict
from datetime import datetime, timedelta

from core.monitor.drivers.restconf_client import (
    RestApiClient,
    get_token_from_response,
    set_headers_by_token,
)

logger = logging.getLogger("monitor")


class MonitorError(Exception):
    pass


def retry(retry_times=3, interval=5, catch_exp=False):
    def wrapper(func):
        def inner(*args, **kwargs):
            error = None
            for i in range(retry_times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Retry {i + 1} failed: {e}")
                    time.sleep(interval)
                    error = e
            if not catch_exp:
                raise error

        return inner

    return wrapper


def parse_value(value):
    try:
        if isinstance(value, str):
            return float(value)
        return value
    except Exception:
        return None


def get_push_msg(
    metric,
    metric_value,
    timestamp,
    resource_id,
    resource_mapping,
    dims=None,
    agreement="",
    protocol="",
):
    dims = dims or []
    metric_value = parse_value(metric_value)
    if metric_value is None:
        return
    if resource_id not in resource_mapping:
        logger.error(f"resource_id not in resource_mapping, resource_id:{resource_id}")
        return
    template = (
        timestamp,
        metric,
        {
            "bk_obj_id": resource_mapping[resource_id]["bk_obj_id"],
            "bk_inst_id": str(resource_mapping[resource_id]["bk_inst_id"]),
            "bk_inst_name": resource_mapping[resource_id]["bk_inst_name"],
            "bk_biz_id": str(resource_mapping[resource_id]["bk_biz_id"]),
            "instanceId": str(resource_id),
            "agreement": agreement,
            "source": "automate",
            "protocol": "automate",
        },
        metric_value,
    )

    for dim_key, dim_value in dims:
        if dim_value is None:
            dim_value = ""
        template[2].update({dim_key: dim_value})
    return template


def parse_monitor_data(monitor_data, resource_mapping, agreement=""):
    msg_list = []
    for resource_id, metric_data in monitor_data.items():
        for metric, metric_list in metric_data.items():
            if isinstance(metric_list, dict):
                for dims, _metric_list in metric_list.items():
                    if not _metric_list:
                        continue
                    try:
                        timestamp, metric_value = _metric_list[-1]
                        if len(str(timestamp)) == 10:
                            timestamp = timestamp * 1000
                        if metric_value is None:
                            continue
                    except Exception:
                        logger.error(
                            f"[monitor] parse error resource_id:{resource_id},metric:{metric},metric_list:{_metric_list}"
                        )
                        continue
                    msg = get_push_msg(
                        metric,
                        metric_value,
                        timestamp,
                        resource_id,
                        resource_mapping,
                        dims=dims,
                        agreement=agreement,
                        protocol=agreement,
                    )
                    if msg is not None:
                        msg_list.append(msg)
            else:
                if not metric_list:
                    continue
                try:
                    timestamp, metric_value = metric_list[-1]
                    if len(str(timestamp)) == 10:
                        timestamp = timestamp * 1000
                except Exception:
                    logger.error(
                        f"[monitor] parse error resource_id:{resource_id},metric:{metric},metric_list:{metric_list}"
                    )
                    continue
                if metric_value is None:
                    continue
                msg = get_push_msg(
                    metric,
                    metric_value,
                    timestamp,
                    resource_id,
                    resource_mapping,
                    agreement=agreement,
                )
                if msg is not None:
                    msg_list.append(msg)
    return msg_list


class MonitorFactory:
    monitors = {}

    @classmethod
    def register_monitor(cls, agreement, monitor_cls):
        cls.monitors[agreement] = monitor_cls

    @classmethod
    def create_monitor(cls, config):
        agreement = config.get("agreement", "")
        brand = config.get("brand", "")
        code = f"{brand}-{agreement}"
        monitor_cls = cls.monitors.get(code)
        if not monitor_cls:
            code_lower = code.lower()
            for registered_code, registered_cls in cls.monitors.items():
                if registered_code.lower() == code_lower:
                    monitor_cls = registered_cls
                    break
        if not monitor_cls:
            monitor_cls = cls.monitors.get(agreement)
            if not monitor_cls:
                raise Exception(f"[monitor] not found agreement:{agreement}")
        return monitor_cls(config)


class MonitorMeta(type):
    def __new__(cls, name, bases, attrs):
        super_new = super(MonitorMeta, cls).__new__
        parents = [b for b in bases if isinstance(b, MonitorMeta)]
        if not parents:
            return super_new(cls, name, bases, attrs)
        new_class = super_new(cls, name, bases, attrs)
        if not new_class.code:
            raise MonitorError(
                f"Monitor Error : {new_class.__name__} code can't be empty."
            )
        MonitorFactory.register_monitor(new_class.code, new_class)
        return new_class


class Monitor(metaclass=MonitorMeta):
    code = "base"

    def __init__(self, input, *args, **kwargs):
        self._data = None
        self.input = input
        self.config = input.get("config", {})
        self.task_id = input.get("task", "")
        self.interval = input.get("interval", 60 * 5)
        self.timeout = input.get("timeout", 60)
        self.retry_count = input.get("retry", 0)
        self.retry_interval = input.get("retry_interval", 5)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_time_ago = (datetime.now() - timedelta(seconds=self.interval)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.start_time = kwargs.get("start_time", current_time_ago)
        self.end_time = kwargs.get("end_time", current_time)
        self.resource = input.get("resource", {})
        self.metrics = self.resource.get("metrics", [])
        self.bk_obj_id = input.get("bk_obj_id", "")
        self.error_msg = []

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    def run(self):
        self.data = {}

    def execute(self):
        run = self.run
        if self.retry_count:
            run = retry(self.retry_count, self.retry_interval)(run)
        run()


class ApiMonitor(Monitor):
    code = "api"
    endpoint_map = {
        "login": ("/login", "POST"),
    }
    metrics_api_map = {}

    def __init__(self, input):
        super(ApiMonitor, self).__init__(input)
        self.base_url = self.config.get("base_url", "")
        self.api = RestApiClient(base_url=self.base_url, save_session=True)
        self.credentials = self.config.get("credentials", {})
        self.resource_id = self.resource.get("bk_inst_id", "")

    @property
    def now(self):
        return int(time.time() * 1000)

    @property
    def token_header_func(self):
        return set_headers_by_token

    def run(self):
        pass

    def login(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


SnmpMonitor = Monitor
