"""Stargazer 统一日志入口。

采集运行时与插件适配层统一从本模块导入 logger，
底层使用 Sanic 框架 logger，避免各文件自行 getLogger。
"""

from __future__ import annotations

from sanic.log import logger

__all__ = ["logger"]
