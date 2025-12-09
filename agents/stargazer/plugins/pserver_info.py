# -- coding: utf-8 --
# @File: host_info.py
# @Time: 2025/5/6 17:48
# @Author: windyzhao
# !/usr/bin/python
# -*- coding: utf-8 -*-

from plugins.base import BaseSSHPlugin


class HostInfo(BaseSSHPlugin):
    """Class for collecting server information."""
    default_script_path = "plugins/shell/server_default_disover.sh"
    plugin_type = "physcial_server"
