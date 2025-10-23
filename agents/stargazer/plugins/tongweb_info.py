# -*- coding: utf-8 -*-
# @File: tongweb_info.py
# @Time: 2025/8/04 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class TongWebInfo(BaseSSHPlugin):
    """Class for collecting tongweb information."""
    default_script_path = "plugins/shell/tongweb_default_discover.sh"
    plugin_type = "tongweb"