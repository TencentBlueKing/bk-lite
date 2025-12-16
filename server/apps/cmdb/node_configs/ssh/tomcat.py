# -- coding: utf-8 --
# @File: tomcat.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class TomcatNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "tomcat"
    plugin_name = "tomcat_info"
