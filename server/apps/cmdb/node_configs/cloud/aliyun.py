# -- coding: utf-8 --
# @File: aliyun.py
# @Time: 2025/11/13 14:24
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class AliyunNodeParams(BaseNodeParams):
    supported_model_id = "aliyun"
    plugin_name = "aliyun_info"
    interval = 300  # 阿里云采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})

    def set_credential(self, *args, **kwargs):
        _access_key = f"PASSWORD_access_key_{self._instance_id}"
        _access_secret = f"PASSWORD_access_secret_{self._instance_id}"
        regions_id = self.credential["regions"]["resource_id"]
        credential_data = {
            "access_key": "${" + _access_key + "}",
            "access_secret": "${" + _access_secret + "}",
            "region_id": regions_id
        }
        return credential_data

    def env_config(self, *args, **kwargs):
        env_config = {
            f"PASSWORD_access_key_{self._instance_id}": self.credential.get("accessKey", ""),
            f"PASSWORD_access_secret_{self._instance_id}": self.credential.get("accessSecret", ""),
        }
        return env_config
