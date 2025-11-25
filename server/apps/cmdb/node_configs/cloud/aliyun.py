# -- coding: utf-8 --
# @File: aliyun.py
# @Time: 2025/11/13 14:24
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class AliyunNodeParams(BaseNodeParams):
    supported_model_id = "aliyun_account"
    plugin_name = "aliyun_info"
    interval = 300  # 阿里云采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})

    def set_credential(self, *args, **kwargs):
        regions_id = self.credential["regions"]["resource_id"]
        credential_data = {
            "access_key": self.credential.get("accessKey", ""),
            "access_secret": self.credential.get("accessSecret", ""),
            "region_id": regions_id
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['inst_name']}"
        else:
            return f"{self.instance.id}_{instance}"
