#!/usr/bin/env python3
"""语言包同步工具

提供语言包与 Notion 数据库之间的双向同步功能：
- push_web_pack: 推送本地 Web 前端语言包到 Notion
- sync_web_pack: 从 Notion 同步 Web 前端语言包到本地
- push_server_pack: 推送本地 Server 后端语言包到 Notion
- sync_server_pack: 从 Notion 同步 Server 后端语言包到本地
"""

import os

import fire
from dotenv import load_dotenv
from loguru import logger

from web_syncer import WebLangSyncer
from server_syncer import ServerLangSyncer

# 加载环境变量
load_dotenv()


class LangSyncer:
    """语言包同步 CLI 工具"""

    def push_web_pack(self):
        """推送 Web 前端语言包到 Notion 数据库"""
        notion_token = os.getenv("NOTION_TOKEN")
        web_lang_config = os.getenv("WEB_LANG_CONFIG")

        if not notion_token or not web_lang_config:
            logger.error("缺少必要的环境变量: NOTION_TOKEN 或 WEB_LANG_CONFIG")
            return

        syncer = WebLangSyncer(notion_token, web_lang_config)
        syncer.push()

    def sync_web_pack(self):
        """从 Notion 数据库同步 Web 前端语言包到本地"""
        notion_token = os.getenv("NOTION_TOKEN")
        web_lang_config = os.getenv("WEB_LANG_CONFIG")

        if not notion_token or not web_lang_config:
            logger.error("缺少必要的环境变量: NOTION_TOKEN 或 WEB_LANG_CONFIG")
            return

        syncer = WebLangSyncer(notion_token, web_lang_config)
        syncer.sync()

    def push_server_pack(self):
        """推送 Server 后端语言包到 Notion 数据库"""
        notion_token = os.getenv("NOTION_TOKEN")
        server_lang_config = os.getenv("SERVER_LANG_CONFIG")

        if not notion_token or not server_lang_config:
            logger.error("缺少必要的环境变量: NOTION_TOKEN 或 SERVER_LANG_CONFIG")
            return

        syncer = ServerLangSyncer(notion_token, server_lang_config)
        syncer.push()

    def sync_server_pack(self):
        """从 Notion 数据库同步 Server 后端语言包到本地"""
        notion_token = os.getenv("NOTION_TOKEN")
        server_lang_config = os.getenv("SERVER_LANG_CONFIG")

        if not notion_token or not server_lang_config:
            logger.error("缺少必要的环境变量: NOTION_TOKEN 或 SERVER_LANG_CONFIG")
            return

        syncer = ServerLangSyncer(notion_token, server_lang_config)
        syncer.sync()


def main():
    """CLI 入口"""
    fire.Fire(LangSyncer)


if __name__ == "__main__":
    main()
