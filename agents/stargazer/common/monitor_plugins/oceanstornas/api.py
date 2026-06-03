import requests

from core.logger import monitor_logger as logger
from core.monitor import ApiMonitor


class OceanStorPacificNasMonitor(ApiMonitor):
    code = "oceanstorpacificnas-api"

    # 指标和数据字段映射
    metrics_api_map = {
        "api_pool_read": "123",
        "api_pool_write": "124",
        "api_pool_read_io": "25",
        "api_pool_write_io": "28",
        "api_pool_io_rate": "22",
        "api_pool_resp_t": "428",
        "api_pool_resp_t_w": "430",
        "api_pool_resp_t_r": "432",
        "api_pool_block_size_r": "24",
        "api_pool_block_size_w": "27",
        "api_cpu_usage": "68",
        "api_cache_usage": "69",
    }

    reverse_metrics_api_map = {v: k for k, v in metrics_api_map.items()}

    endpoint_map = {
        "login": ("/api/v2/aa/sessions", "POST"),
        "logout": ("/api/v2/aa/sessions", "DELETE"),
        "pool_config": ("/api/v2/data_service/storagepool", "GET"),
        "disk_pool_info": ("/dsware/service/cluster/diskpool/queryNodeDiskInfo", "GET"),
        "performance_data": ("/api/v2/pms/performance_data", "POST"),
    }

    def __init__(self, input):
        super().__init__(input)
        self.token = None
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def login(self):
        """
        登录以获取 token
        """
        payload = {
            "user_name": self.credentials.get("username"),
            "password": self.credentials.get("password"),
            "scope": "0",
            "isEncrypt": "false",
        }
        try:
            endpoint, method = self.endpoint_map["login"]
            url = f"{self.base_url}{endpoint}"
            response = requests.post(url, json=payload, verify=False)
            response.raise_for_status()
            data = response.json().get("data")
            self.token = data.get("x_auth_token")
            self.headers["X-Auth-Token"] = self.token
        except Exception as e:
            logger.error(f"Failed to login: {e}")
            raise RuntimeError("Login failed, please check your credentials or API connectivity.")

    def logout(self):
        """
        注销会话
        """
        try:
            endpoint, method = self.endpoint_map["logout"]
            url = f"{self.base_url}{endpoint}"
            response = requests.delete(url, headers=self.headers, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to logout: {e}")

    def fetch_pool_config(self):
        """
        获取所有存储池的配置
        """
        try:
            endpoint, method = self.endpoint_map["pool_config"]
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()
            return response.json().get("storagePools", [])
        except Exception as e:
            logger.error(f"Failed to fetch pool config: {e}")
            return []

    def fetch_disk_pool_info(self, pool_ids):
        """
        根据存储池 ID 获取磁盘池信息
        """
        try:
            endpoint, method = self.endpoint_map["disk_pool_info"]
            url = f"{self.base_url}{endpoint}?diskPoolId={','.join(pool_ids)}"
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()
            return response.json().get("nodeInfo", [])
        except Exception as e:
            logger.error(f"Failed to fetch disk pool info: {e}")
            return []

    def fetch_performance_data(self, object_type, object_id, indicators):
        """
        获取性能数据
        """
        try:
            endpoint, method = self.endpoint_map["performance_data"]
            url = f"{self.base_url}{endpoint}"
            payload = {
                "begin_time": self.now - 600,  # 取最近 10 分钟的数据
                "end_time": self.now,
                "objects": [{"object_type": object_type, "ids": [object_id], "indicators": indicators}],
            }
            response = requests.post(url, json=payload, headers=self.headers, verify=False)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch performance data for object_id {object_id}: {e}")
            return []

    def format_metrics(self, statistics):
        """
        格式化性能数据
        """
        metrics = {}
        for stat in statistics:
            indicator_id = stat.get("indicator")
            stat_values = stat.get("indicator_values", [])
            metric_name = self.reverse_metrics_api_map.get(indicator_id)
            if metric_name:
                metrics[metric_name] = stat_values[-1]  # 取最近的一个时间点的值
        return metrics

    def run(self):
        """
        主流程：收集存储池和磁盘性能数据
        """
        self.data = {}
        self.login()

        # 获取存储池配置
        pools = self.fetch_pool_config()
        pool_ids = [pool.get("storagePoolId") for pool in pools if pool.get("storagePoolId")]

        # 获取磁盘信息
        disk_pool_info = self.fetch_disk_pool_info(pool_ids)

        for node in disk_pool_info:
            media_info = node.get("mediaInfo", [])
            for disk in media_info:
                disk_sn = disk.get("diskSn")
                if not disk_sn:
                    continue

                # 获取磁盘性能数据
                performance_data = self.fetch_performance_data(
                    object_type=10, object_id=disk_sn, indicators=list(self.metrics_api_map.values())
                )
                metrics = self.format_metrics(performance_data)

                # 保存数据
                for metric_name, value in metrics.items():
                    dims = (("pool", disk_sn),)
                    self.data.setdefault(self.resource_id, {}).setdefault(metric_name, {}).setdefault(dims, []).append(
                        value
                    )

        # 退出登录
        self.logout()
