# -- coding: utf-8 --
# @File: qcloud.py
# @Time: 2025/11/13 14:29
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class QCloudNodeParams(BaseNodeParams):
    supported_model_id = "qcloud"
    plugin_name = "qcloud_info"
    interval = 300  # 腾讯云采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: "qcloud_info"})

    def set_credential(self, *args, **kwargs):
        """
        生成 Tencent Cloud 的凭据
        """
        _secret_id = f"PASSWORD_secret_id_{self._instance_id}"
        _secret_key = f"PASSWORD_secret_key_{self._instance_id}"
        return {
            "secret_id": "${" + _secret_id + "}",
            "secret_key": "${" + _secret_key + "}",
        }

    def env_config(self, *args, **kwargs):
        env_config = {
            f"PASSWORD_secret_id_{self._instance_id}": self.credential.get("accessKey", ""),
            f"PASSWORD_secret_key_{self._instance_id}": self.credential.get("secretSecret", ""),
        }
        return env_config

    @property
    def password(self):
        # 返回腾讯云的密码数据
        password_data = {
            "secret_id": self.credential.get("accessKey", ""),
            "secret_key": self.credential.get("secretSecret", ""),
        }
        return password_data
