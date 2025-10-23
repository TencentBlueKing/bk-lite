# -*- coding: utf-8 -*-
# @File: dameng_info.py
# @Time: 2025/8/05 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class DaMengInfo(BaseSSHPlugin):
    """Class for collecting dameng information."""
    default_script_path = "plugins/shell/dameng_default_discover.sh"
    plugin_type = "dameng"