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
        return {
            # "secret_id": self.credential.get("accessKey", ""),
            # "secret_key": self.credential.get("secretSecret", ""),
            "secret_id": "${PASSWORD_secret_id}",
            "secret_key": "${PASSWORD_secret_key}",
        }

    def get_instance_id(self, instance):
        """
        获取实例 ID
        """
        return f"{self.instance.id}_{instance['inst_name']}"

    @property
    def env_config(self, *args, **kwargs):
        env_config = {
            "$PASSWORD_secret_id": self.credential.get("accessKey", ""),
            "$PASSWORD_secret_key": self.credential.get("secretSecret", ""),
        }
        return env_config