# -*- coding: utf-8 -*-
# @File: db2_info.py
# @Time: 2025/8/11 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class DB2Info(BaseSSHPlugin):
    """Class for collecting db2 information."""
    default_script_path = "plugins/shell/db2_default_discover.sh"
    plugin_type = "db2"