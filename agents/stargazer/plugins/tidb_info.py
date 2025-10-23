# -*- coding: utf-8 -*-
# @File: tidb_info.py
# @Time: 2025/8/12 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class TiDBInfo(BaseSSHPlugin):
    """Class for collecting tidb information."""
    default_script_path = "plugins/shell/tidb_default_discover.sh"
    plugin_type = "tidb"