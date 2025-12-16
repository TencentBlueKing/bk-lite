"""配置管理模块"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


@dataclass
class AppConfig:
    """单个应用配置"""

    name: str
    database_id: str

    @property
    def normalized_database_id(self) -> str:
        """返回标准化的数据库 ID（无连字符）"""
        return self.database_id.replace("-", "")


class Config:
    """全局配置管理"""

    # Notion API
    NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
    NOTION_API_VERSION = "2022-06-28"

    # 项目路径
    # __file__ 在 src/lang_syncer/config.py
    # parent -> src/lang_syncer/
    # parent.parent -> src/
    # parent.parent.parent -> lang-syncer/
    # parent.parent.parent.parent -> support-files/
    # parent.parent.parent.parent.parent -> bk-lite/
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
    WEB_ROOT = PROJECT_ROOT / "web" / "src" / "app"
    SERVER_ROOT = PROJECT_ROOT / "server" / "apps"

    # 语言包配置
    WEB_LANG_CONFIG = os.getenv("WEB_LANG_CONFIG", "")
    SERVER_LANG_CONFIG = os.getenv("SERVER_LANG_CONFIG", "")

    # 批量操作配置
    BATCH_SIZE = 100
    REQUEST_TIMEOUT = 30.0

    @classmethod
    def parse_app_configs(cls, config_string: str) -> list[AppConfig]:
        """解析应用配置字符串

        Args:
            config_string: 格式为 "app_name:database_id,app_name:database_id"

        Returns:
            AppConfig 对象列表
        """
        if not config_string:
            return []

        configs = []
        for item in config_string.split(","):
            item = item.strip()
            if ":" not in item:
                continue

            name, database_id = item.split(":", 1)
            configs.append(AppConfig(name=name.strip(),
                           database_id=database_id.strip()))

        return configs

    @classmethod
    def validate(cls) -> bool:
        """验证必要的配置是否存在"""
        return bool(cls.NOTION_TOKEN)
