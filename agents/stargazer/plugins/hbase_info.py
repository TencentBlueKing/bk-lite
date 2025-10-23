# -*- coding: utf-8 -*-
# @File: hbase_info.py
# @Time: 2025/9/4 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class HBaseInfo(BaseSSHPlugin):
    """Class for collecting hbase information."""
    default_script_path = "plugins/shell/hbase_default_discover.sh"
    plugin_type = "hbase"