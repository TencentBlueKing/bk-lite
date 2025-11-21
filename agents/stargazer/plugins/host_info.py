# -- coding: utf-8 --
# @File: host_info.py
# @Time: 2025/5/6 17:48
# @Author: windyzhao
# !/usr/bin/python
# -*- coding: utf-8 -*-

from plugins.base import BaseSSHPlugin
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class HostInfo(BaseSSHPlugin):
    """Class for collecting host information."""
    default_script_path = "plugins/shell/host_default_discover.sh"
    plugin_type = "host"
