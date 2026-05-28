# -*- coding: utf-8 -*-
import logging

from core.monitor.base import ApiMonitor

logger = logging.getLogger("monitor")


class OceanStorApiMonitor(ApiMonitor):
    code = "oceanstor-api"
    config_page_size = 100

    @staticmethod
    def normalize_timestamp(raw_timestamp):
        """Normalize OceanStor timestamps to millisecond integers."""
        if raw_timestamp in (None, ""):
            return None

        try:
            timestamp = int(str(raw_timestamp).strip())
        except (TypeError, ValueError):
            logger.warning("OceanStor timestamp is invalid: %s", raw_timestamp)
            return None

        # OceanStor responses typically use second-level epoch values.
        if timestamp < 10**12:
            return timestamp * 1000
        return timestamp

    # 指标和数据字段映射
    metrics_api_map = {
        # Pool Metrics IDs
        "api_pool_io_rate": "22",
        "api_pool_read_io": "25",
        "api_pool_write_io": "28",
        "api_pool_resp_t": "370",
        "api_pool_read": "23",
        "api_pool_write": "26",
        "api_pool_resp_t_r": "384",
        "api_pool_resp_t_w": "385",
        # Drive Metrics IDs
        "api_drive_io_rate": "22",
        "api_drive_read_io": "25",
        "api_drive_write_io": "28",
        "api_drive_resp_t": "370",
        "api_drive_read": "23",
        "api_drive_write": "26",
        "api_drive_resp_t_r": "384",
        "api_drive_resp_t_w": "385",
        # Volume Metrics IDs
        "api_volume_io_rate": "22",
        "api_volume_read_io": "25",
        "api_volume_write_io": "28",
        "api_volume_resp_t": "370",
        "api_volume_read": "23",
        "api_volume_write": "26",
        "api_volume_resp_t_r": "384",
        "api_volume_resp_t_w": "385",
    }
    reverse_metrics_api_map = {v: k for k, v in metrics_api_map.items()}

    endpoint_map = {
        "login": ("/deviceManager/rest/xxxxx/sessions", "POST"),
        "logout": ("/deviceManager/rest/{device_id}/sessions", "DELETE"),
        "drive_config": ("/deviceManager/rest/{device_id}/disk", "GET"),
        "volume_config": ("/deviceManager/rest/{device_id}/lun", "GET"),
        "pool_config": ("/deviceManager/rest/{device_id}/storagepool", "GET"),
        "performance_data": (
            "/deviceManager/rest/{device_id}/performace_statistic/cur_statistic_data",
            "GET",
        ),
    }

    def __init__(self, input):
        super().__init__(input)
        self.token = None
        self.device_id = None

    @property
    def token_header_func(self):
        """生成动态请求头部配置"""

        def set_header(headers, token):
            return headers.update(
                {"iBaseToken": token, "Content-Type": "application/json"}
            )

        return set_header

    def login(self):
        """登录以获取 token 和 device_id"""
        payload = {
            "username": self.config.get("username"),
            "password": self.config.get("password"),
            "scope": "0",
        }
        try:
            endpoint, method = self.endpoint_map["login"]
            response = self.api.request(method, endpoint, json=payload, verify=False)
            data = response.get("data", {})
            if not data:
                raise RuntimeError("Login failed: No data returned.")
            self.token = data.get("iBaseToken")
            self.device_id = data.get("deviceid")
            # Persist the session token on the underlying REST client so
            # subsequent requests can attach iBaseToken via token_header_func.
            self.api.set_token(self.token)
            logger.info(
                "OceanStor login succeeded: device_id=%s, token_present=%s",
                self.device_id,
                bool(self.token),
            )
        except Exception as e:
            logger.error(f"Failed to login: {e}")
            raise RuntimeError(
                "Login failed: Ensure credentials and API connectivity are correct."
            )

    def logout(self):
        """注销会话"""
        try:
            endpoint, method = self.endpoint_map["logout"]
            formatted_endpoint = endpoint.format(device_id=self.device_id)
            self.api.request(
                method,
                formatted_endpoint,
                verify=False,
                token_header_func=self.token_header_func,
            )
        except Exception as e:
            logger.error(f"Failed to logout: {e}")
        finally:
            self.api.logout()

    def fetch_config(self, endpoint_key):
        """获取配置信息的通用方法"""
        try:
            endpoint, method = self.endpoint_map[endpoint_key]
            formatted_endpoint = endpoint.format(device_id=self.device_id)
            all_items = []
            start = 0

            while True:
                response = self.api.request(
                    method,
                    formatted_endpoint,
                    params={"range": f"[{start}-{start + self.config_page_size - 1}]"},
                    verify=False,
                    token_header_func=self.token_header_func,
                )
                error_code = (response.get("error") or {}).get("code", 0)
                if error_code != 0:
                    logger.warning(
                        "OceanStor fetch_config returned error: endpoint=%s, code=%s, response=%s",
                        endpoint_key,
                        error_code,
                        response,
                    )
                    break

                data = response.get("data", [])
                if not isinstance(data, list) or not data:
                    break

                all_items.extend(data)
                if len(data) < self.config_page_size:
                    break
                start += self.config_page_size

            logger.info(
                "OceanStor fetch_config succeeded: endpoint=%s, item_count=%s",
                endpoint_key,
                len(all_items),
            )
            return all_items
        except Exception as e:
            logger.error(f"Failed to fetch config for {endpoint_key}: {e}")
            return []

    def fetch_performance_data(self, object_type, object_id, metrics):
        """获取性能统计数据的通用方法"""
        try:
            endpoint, method = self.endpoint_map["performance_data"]
            formatted_endpoint = endpoint.format(device_id=self.device_id)
            payload = {
                "CMO_STATISTIC_UUID": f"{object_type}:{object_id}",
                "CMO_STATISTIC_DATA_ID_LIST": ",".join(metrics),
            }
            response = self.api.request(
                method,
                formatted_endpoint,
                params=payload,
                verify=False,
                token_header_func=self.token_header_func,
            )
            error_code = (response.get("error") or {}).get("code", 0)
            if error_code != 0:
                logger.warning(
                    "OceanStor performance request returned error: object_type=%s, object_id=%s, code=%s, response=%s",
                    object_type,
                    object_id,
                    error_code,
                    response,
                )
                return []
            data = response.get("data", [])
            logger.info(
                "OceanStor performance response: object_type=%s, object_id=%s, point_count=%s",
                object_type,
                object_id,
                len(data) if isinstance(data, list) else "non-list",
            )
            return data
        except Exception as e:
            logger.error(f"Failed to fetch performance data for {object_id}: {e}")
            return []

    def process_metrics(self, object_id, object_type, metrics_key, dims_key):
        """处理通用的对象指标数据"""
        metrics = {v: k for k, v in self.metrics_api_map.items()}
        statistics = self.fetch_performance_data(
            object_type, object_id, list(metrics.keys())
        )
        for item in statistics:
            processed_metrics = {}
            for key, value in zip(
                item.get("CMO_STATISTIC_DATA_ID_LIST", "").split(","),
                item.get("CMO_STATISTIC_DATA_LIST", "").split(","),
            ):
                metric_name = metrics.get(key)
                if metric_name:
                    processed_metrics[metric_name] = value
            _timestamp = self.normalize_timestamp(item.get("CMO_STATISTIC_TIMESTAMP"))

            # 保存数据
            for metric_name, value in processed_metrics.items():
                dims = ((dims_key, object_id),)
                self.data.setdefault(self.resource_id, {}).setdefault(
                    metric_name, {}
                ).setdefault(dims, []).append((_timestamp, value))

    def process_drive_data(self):
        """处理磁盘（Drive）数据"""
        drives = self.fetch_config("drive_config")
        for drive in drives:
            drive_sn = drive.get("ID")
            if drive_sn in (None, ""):
                continue
            self.process_metrics(drive_sn, 10, "drive", "drive_id")

    def process_volume_data(self):
        """处理卷（Volume）数据"""
        volumes = self.fetch_config("volume_config")
        for volume in volumes:
            volume_id = volume.get("ID")
            if volume_id in (None, ""):
                continue
            self.process_metrics(volume_id, 11, "volume", "volume_id")

    def process_pool_data(self):
        """处理存储池（Pool）数据"""
        pools = self.fetch_config("pool_config")
        for pool in pools:
            pool_id = pool.get("ID")
            if pool_id in (None, ""):
                continue
            self.process_metrics(pool_id, 216, "pool", "pool_id")

    def run(self):
        """主流程，执行数据收集和处理"""
        self.data = {}
        self.login()

        # 依次处理不同的数据类型
        self.process_pool_data()
        self.process_drive_data()
        self.process_volume_data()

        # 注销会话
        self.logout()
