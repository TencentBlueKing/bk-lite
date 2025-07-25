# -*- coding: utf-8 -*-
# @File: keepalived_info.py
# @Time: 2025/7/22 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class KeepalivedInfo(BaseSSHPlugin):
    """Class for collecting keepalived information."""
    default_script_path = "plugins/shell/keepalived_default_discover.sh"
    plugin_type = "keepalived"