# -*- coding: utf-8 -*-
# @File: weblogic_info.py
# @Time: 2025/7/22 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class WebLogicInfo(BaseSSHPlugin):
    """Class for collecting weblogic information."""
    default_script_path = "plugins/shell/weblogic_default_discover.sh"
    plugin_type = "weblogic"