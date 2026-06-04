# -- coding: utf-8 --
# @File: mysql.py
# @Time: 2025/11/13 14:23
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.databases.direct_password import DirectPasswordNodeParamsMixin


class MysqlNodeParams(DirectPasswordNodeParamsMixin, BaseNodeParams):
    supported_model_id = "mysql"  # 通过此属性自动注册
    plugin_name = "mysql_info"
    default_port = 3306

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"
