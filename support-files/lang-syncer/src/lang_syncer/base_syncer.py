"""语言包同步基类"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

import pandas as pd
from loguru import logger
from notion_client import Client

from lang_syncer.config import AppConfig
from lang_syncer.exceptions import FileOperationError
from lang_syncer.notion_helper import batch_create_pages, batch_delete_pages, fetch_database_to_dataframe


class BaseLangSyncer(ABC):
    """语言包同步器基类"""

    def __init__(self, notion_token: str, config_string: str, app_configs: list[AppConfig]):
        """初始化

        Args:
            notion_token: Notion API Token
            config_string: 配置字符串（用于日志）
            app_configs: 应用配置列表
        """
        self.client = Client(auth=notion_token)
        self.config_string = config_string
        self.app_configs = app_configs

    def push(self):
        """推送语言包到 Notion 数据库"""
        logger.info("=" * 60)
        logger.info(f"开始推送 {self.__class__.__name__}")
        logger.info("=" * 60)

        for app_config in self.app_configs:
            try:
                self._push_single_app(app_config)
            except Exception as e:
                logger.error(f"应用 {app_config.name} 推送失败: {e}")
                continue

        logger.info("=" * 60)
        logger.success("所有应用处理完成!")
        logger.info("=" * 60)

    def sync(self):
        """从 Notion 数据库同步语言包到本地"""
        logger.info("=" * 60)
        logger.info(f"开始同步 {self.__class__.__name__}")
        logger.info("=" * 60)

        for app_config in self.app_configs:
            try:
                self._sync_single_app(app_config)
            except Exception as e:
                logger.error(f"应用 {app_config.name} 同步失败: {e}")
                continue

        logger.info("=" * 60)
        logger.success("所有应用同步完成!")
        logger.info("=" * 60)

    def _push_single_app(self, app_config: AppConfig):
        """推送单个应用的语言包"""
        logger.info("=" * 60)
        logger.info(f"处理应用: {app_config.name}")
        logger.info(f"Database ID: {app_config.database_id}")
        logger.info("=" * 60)

        # 获取语言包路径
        lang_pack_path = self._get_lang_pack_path(app_config.name)
        if not lang_pack_path.exists():
            raise FileOperationError(f"语言包路径不存在: {lang_pack_path}")

        logger.info(f"语言包路径: {lang_pack_path}")

        # 加载语言包
        df = self._load_lang_packs(lang_pack_path)
        if df.empty:
            logger.warning(f"应用 {app_config.name} 加载的语言包为空")
            return

        logger.info(f"加载 {len(df)} 条翻译数据")

        # 获取 Notion 中已存在的数据
        existing_records = fetch_database_to_dataframe(
            self.client, app_config.normalized_database_id)
        existing_keys = set(existing_records["名称"].tolist(
        )) if not existing_records.empty and "名称" in existing_records.columns else set()

        if existing_keys:
            logger.info(f"Notion 中已存在 {len(existing_keys)} 个 key")

        # 清理 Notion 中本地不存在的 key
        self._cleanup_deleted_keys(df, existing_records, existing_keys)

        # 添加新增的数据
        self._add_new_keys(app_config, df, existing_keys)

    def _sync_single_app(self, app_config: AppConfig):
        """同步单个应用的语言包"""
        logger.info("=" * 60)
        logger.info(f"处理应用: {app_config.name}")
        logger.info(f"Database ID: {app_config.database_id}")
        logger.info("=" * 60)

        # 获取语言包路径
        lang_pack_path = self._get_lang_pack_path(app_config.name)
        lang_pack_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"语言包路径: {lang_pack_path}")

        # 从 Notion 获取数据
        logger.info("正在从 Notion 获取数据...")
        df = fetch_database_to_dataframe(
            self.client, app_config.normalized_database_id)

        if df.empty:
            logger.warning(f"应用 {app_config.name} 从 Notion 获取的数据为空")
            return

        logger.info(f"获取到 {len(df)} 条数据")

        # 检查必要的列
        if "名称" not in df.columns:
            raise ValueError(f"数据中缺少 '名称' 列")

        # 提取语言列
        lang_columns = [
            col for col in df.columns if col not in ["名称", "page_id"]]
        if not lang_columns:
            logger.warning(f"未找到语言列")
            return

        logger.info(f"找到语言列: {lang_columns}")

        # 写入每种语言的文件
        for lang_code in lang_columns:
            self._write_lang_file(df, lang_code, lang_pack_path)

    def _cleanup_deleted_keys(self, df: pd.DataFrame, existing_records: pd.DataFrame, existing_keys: set):
        """清理 Notion 中本地已删除的 key"""
        if existing_records.empty or not existing_keys:
            return

        local_keys = set(df["key"].tolist())
        keys_to_delete = existing_keys - local_keys

        if not keys_to_delete:
            logger.info("没有需要删除的数据")
            return

        logger.warning(f"发现 {len(keys_to_delete)} 个本地不存在的 key，准备删除")

        # 找到需要删除的 page_id
        page_ids_to_delete = [record["page_id"] for _, record in existing_records.iterrows(
        ) if record["名称"] in keys_to_delete]

        if page_ids_to_delete:
            logger.info(f"开始删除 {len(page_ids_to_delete)} 个页面...")
            result = batch_delete_pages(self.client, page_ids_to_delete)
            logger.success(
                f"删除完成! 成功: {result['success']}, 失败: {result['failed']}")

    def _add_new_keys(self, app_config: AppConfig, df: pd.DataFrame, existing_keys: set):
        """添加新增的 key 到 Notion"""
        new_rows = df[~df["key"].isin(existing_keys)]

        if new_rows.empty:
            logger.info(f"应用 {app_config.name} 没有需要新增的数据")
            return

        logger.info(f"需要新增 {len(new_rows)} 条数据")

        # 构建 Notion properties 列表
        properties_list = self._build_properties_list(new_rows)

        # 批量写入
        logger.info(f"开始写入 {app_config.name} 到 Notion...")
        result = batch_create_pages(
            self.client, app_config.normalized_database_id, properties_list)

        logger.success(
            f"{app_config.name} 写入完成! 成功: {result['success']}, 失败: {result['failed']}, 总计: {result['total']}")

        if result["failed"] > 0:
            logger.warning(f"失败的条目数: {len(result['failed_items'])}")

    @abstractmethod
    def _get_lang_pack_path(self, app_name: str) -> Path:
        """获取语言包路径（由子类实现）"""
        pass

    @abstractmethod
    def _load_lang_packs(self, lang_pack_path: Path) -> pd.DataFrame:
        """加载语言包（由子类实现）"""
        pass

    @abstractmethod
    def _write_lang_file(self, df: pd.DataFrame, lang_code: str, lang_pack_path: Path):
        """写入语言文件（由子类实现）"""
        pass

    @abstractmethod
    def _build_properties_list(self, df: pd.DataFrame) -> list[dict]:
        """构建 Notion properties 列表（由子类实现）"""
        pass
