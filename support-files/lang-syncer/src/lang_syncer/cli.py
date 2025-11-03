#!/usr/bin/env python3
"""语言包同步工具 CLI 入口

提供语言包与 Notion 数据库之间的双向同步功能：
- push_web_pack: 推送本地 Web 前端语言包到 Notion
- sync_web_pack: 从 Notion 同步 Web 前端语言包到本地
- push_server_pack: 推送本地 Server 后端语言包到 Notion
- sync_server_pack: 从 Notion 同步 Server 后端语言包到本地
"""

import sys

import fire
from loguru import logger

from lang_syncer.config import Config
from lang_syncer.exceptions import ConfigError
from lang_syncer.server_syncer import ServerLangSyncer
from lang_syncer.web_syncer import WebLangSyncer


class LangSyncer:
    """语言包同步 CLI 工具"""

    def __init__(self):
        """初始化并验证配置"""
        if not Config.validate():
            raise ConfigError("缺少必要的环境变量 NOTION_TOKEN，请在 .env 文件中配置")

    def push_web_pack(self):
        """推送 Web 前端语言包到 Notion 数据库"""
        if not Config.WEB_LANG_CONFIG:
            logger.error("缺少环境变量 WEB_LANG_CONFIG")
            return

        app_configs = Config.parse_app_configs(Config.WEB_LANG_CONFIG)
        if not app_configs:
            logger.error("WEB_LANG_CONFIG 配置格式错误或为空")
            return

        syncer = WebLangSyncer(Config.NOTION_TOKEN,
                               Config.WEB_LANG_CONFIG, app_configs)
        syncer.push()

    def sync_web_pack(self):
        """从 Notion 数据库同步 Web 前端语言包到本地"""
        if not Config.WEB_LANG_CONFIG:
            logger.error("缺少环境变量 WEB_LANG_CONFIG")
            return

        app_configs = Config.parse_app_configs(Config.WEB_LANG_CONFIG)
        if not app_configs:
            logger.error("WEB_LANG_CONFIG 配置格式错误或为空")
            return

        syncer = WebLangSyncer(Config.NOTION_TOKEN,
                               Config.WEB_LANG_CONFIG, app_configs)
        syncer.sync()

    def push_server_pack(self):
        """推送 Server 后端语言包到 Notion 数据库"""
        if not Config.SERVER_LANG_CONFIG:
            logger.error("缺少环境变量 SERVER_LANG_CONFIG")
            return

        app_configs = Config.parse_app_configs(Config.SERVER_LANG_CONFIG)
        if not app_configs:
            logger.error("SERVER_LANG_CONFIG 配置格式错误或为空")
            return

        syncer = ServerLangSyncer(
            Config.NOTION_TOKEN, Config.SERVER_LANG_CONFIG, app_configs)
        syncer.push()

    def sync_server_pack(self):
        """从 Notion 数据库同步 Server 后端语言包到本地"""
        if not Config.SERVER_LANG_CONFIG:
            logger.error("缺少环境变量 SERVER_LANG_CONFIG")
            return

        app_configs = Config.parse_app_configs(Config.SERVER_LANG_CONFIG)
        if not app_configs:
            logger.error("SERVER_LANG_CONFIG 配置格式错误或为空")
            return

        syncer = ServerLangSyncer(
            Config.NOTION_TOKEN, Config.SERVER_LANG_CONFIG, app_configs)
        syncer.sync()


def main():
    """CLI 入口"""
    try:
        fire.Fire(LangSyncer)
    except ConfigError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"程序异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
