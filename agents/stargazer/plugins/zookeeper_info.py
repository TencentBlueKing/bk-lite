# -*- coding: utf-8 -*-
# @File：zookeeper_info.py
# @Time：2025/6/6 11:24
# @Author：bennie
import json
from sanic.log import logger
from core.nats import NATSClient
from plugins.base_utils import convert_to_prometheus_format


from plugins.base import BaseSSHPlugin


class ZookeeperInfo(BaseSSHPlugin):
    """Class for collecting zookeeper information."""
    default_script_path = "plugins/shell/zookeeper_default_discover.sh"

    plugin_type = "zookeeper"
