import requests

from core.logger import monitor_logger as logger
from core.monitor import ApiMonitor


class OceanStorPacificaNasApiMonitor(ApiMonitor):
    code = "oceanstorpacificanas-api"

    # 指标和数据字段映射
    metrics_api_map = {
        # Pool Metrics IDs
        "api_pool_read_io": "25",
        "api_pool_write_io": "28",
        "api_pool_resp_t": "428",
        "api_pool_read": "123",
        "api_pool_write": "124",
        "api_pool_resp_t_r": "432",
        "api_pool_resp_t_w": "430",
        # Drive Metrics IDs
        "api_drive_read_io": "25",
        "api_drive_write_io": "28",
        "api_drive_resp_t": "428",
        "api_drive_read": "123",
        "api_drive_write": "124",
        "api_drive_resp_t_r": "432",
        "api_drive_resp_t_w": "430",
        # Volume Metrics IDs
        "api_volume_read_io": "25",
        "api_volume_write_io": "28",
        "api_volume_resp_t": "428",
        "api_volume_read": "123",
        "api_volume_write": "124",
        "api_volume_resp_t_r": "432",
        "api_volume_resp_t_w": "430",
    }
    reverse_metrics_api_map = {v: k for k, v in metrics_api_map.items()}

    endpoint_map = {
        "login": ("/api/v2/aa/sessions", "POST"),
        "logout": ("/api/v2/aa/sessions", "DELETE"),
        "drive_config": ("/dsware/service/cluster/diskpool/queryNodeDiskInfo", "GET"),
        "volume_config": ("/api/v2/block_service/volumes", "GET"),
        "pool_config": ("/api/v2/data_service/storagepool", "GET"),
        "performance_data": ("/api/v2/pms/performance_data", "POST"),
    }

    def __init__(self, input):
        super().__init__(input)
        self.token = None
        self.device_id = None

    @property
    def token_header(self):
        """动态生成请求头部"""
        return {
            "X-Auth-Token": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def login(self):
        """登录获取token"""
        payload = {
            "user_name": self.credentials.get("username"),
            "password": self.credentials.get("password"),
            "scope": "0",
            "isEncrypt": "false",
        }
        try:
            url = f"{self.base_url}{self.endpoint_map['login'][0]}"
            response = requests.post(url, json=payload, verify=False)
            response.raise_for_status()
            data = response.json().get("data", {})
            self.token = data.get("x_auth_token")
            self.device_id = data.get("system_esn")
        except Exception as e:
            logger.error(f"Failed to login: {e}")
            raise RuntimeError("Login failed, please check your credentials or API connectivity.")

    def logout(self):
        """注销会话"""
        try:
            url = f"{self.base_url}{self.endpoint_map['logout'][0]}"
            response = requests.delete(url, headers=self.token_header, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to logout: {e}")

    def fetch_config(self, endpoint_key):
        """获取配置信息的通用方法"""
        try:
            url = f"{self.base_url}{self.endpoint_map[endpoint_key][0]}"
            response = requests.get(url, headers=self.token_header, verify=False)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch config for {endpoint_key}: {e}")
            return {}

    def fetch_performance_data(self, object_type, object_id, metrics):
        """通用性能统计数据获取接口"""
        try:
            url = f"{self.base_url}{self.endpoint_map['performance_data'][0]}"
            payload = {
                "begin_time": self.now - 900,  # 开始时间（15分钟前）
                "end_time": self.now,  # 当前时间
                "objects": [
                    {
                        "object_type": object_type,
                        "ids": [object_id],
                        "indicators": metrics,
                    }
                ],
            }
            response = requests.post(url, json=payload, headers=self.token_header, verify=False)
            response.raise_for_status()
            return response.json().get("objects", [])
        except Exception as e:
            logger.error(f"Failed to fetch performance data for id {object_id}: {e}")
            return []

    def format_metrics(self, object_id, statistics):
        """格式化并映射指标"""
        metrics = {}
        for item in statistics:
            stat_values = item.get("indicator_values", [])
            indicator_id = item.get("indicator")
            metric_name = self.reverse_metrics_api_map.get(indicator_id)
            if metric_name:
                metrics[metric_name] = stat_values[-1]  # 取最后一个时间点的值
        return metrics

    def process_pool_data(self):
        """处理Pool数据"""
        pools = self.fetch_config("pool_config").get("storagePools", [])
        for pool in pools:
            pool_id = pool.get("storagePoolId")
            if not pool_id:
                continue

            # 获取性能统计数据
            statistics = self.fetch_performance_data(216, pool_id, list(self.metrics_api_map.values()))
            metrics = self.format_metrics(pool_id, statistics)

            # 保存转换后的数据
            for metric_name, value in metrics.items():
                dims = (("pool_id", pool_id),)
                self.data.setdefault(self.resource_id, {}).setdefault(metric_name, {}).setdefault(dims, []).append(
                    value
                )

    def process_drive_data(self):
        """处理Drive数据"""
        drives = self.fetch_config("drive_config").get("nodeInfo", [])
        for drive in drives:
            drive_sn = drive.get("diskSn")  # Drive ID
            if not drive_sn:
                continue

            # 获取性能统计数据
            statistics = self.fetch_performance_data(10, drive_sn, list(self.metrics_api_map.values()))
            metrics = self.format_metrics(drive_sn, statistics)

            # 保存转换后的数据
            for metric_name, value in metrics.items():
                dims = (("drive_id", drive_sn),)
                self.data.setdefault(self.resource_id, {}).setdefault(metric_name, {}).setdefault(dims, []).append(
                    value
                )

    def process_volume_data(self):
        """处理Volume数据"""
        volumes = self.fetch_config("volume_config").get("data", [])
        for volume in volumes:
            volume_id = volume.get("id")
            if not volume_id:
                continue

            # 获取性能统计数据
            statistics = self.fetch_performance_data(11, volume_id, list(self.metrics_api_map.values()))
            metrics = self.format_metrics(volume_id, statistics)

            # 保存转换后的数据
            for metric_name, value in metrics.items():
                dims = (("volume_id", volume_id),)
                self.data.setdefault(self.resource_id, {}).setdefault(metric_name, {}).setdefault(dims, []).append(
                    value
                )

    def run(self):
        """主流程，执行数据收集和处理"""
        self.data = {}
        self.login()

        # 处理Pool数据
        self.process_pool_data()

        # 处理Drive数据
        self.process_drive_data()

        # 处理Volume数据
        self.process_volume_data()

        # 退出登录
        self.logout()
