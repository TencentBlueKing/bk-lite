# -*- coding: utf-8 -*-
# @File: jetty_info.py
# @Time: 2025/9/03 12:00
# @Author: lyj

from plugins.base import BaseSSHPlugin


class JettyInfo(BaseSSHPlugin):
    """Class for collecting jetty information."""
    default_script_path = "plugins/shell/jetty_default_discover.sh"
    plugin_type = "jetty"