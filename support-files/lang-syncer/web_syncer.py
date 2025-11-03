"""Web 前端语言包同步模块"""

from pathlib import Path

import pandas as pd
from loguru import logger
from notion_client import Client
from tqdm import tqdm

from notion_helper import fetch_database_to_dataframe, batch_create_pages, batch_delete_pages
from utils import load_lang_packs_to_dataframe, write_lang_json_file


class WebLangSyncer:
    """Web 前端语言包同步器"""

    def __init__(self, notion_token: str, web_lang_config: str):
        """初始化

        Args:
            notion_token: Notion API Token
            web_lang_config: Web 语言包配置，格式: app_name:database_id,app_name:database_id
        """
        self.client = Client(auth=notion_token)
        self.web_lang_config = web_lang_config

    def push(self):
        """推送前端语言包到 Notion 数据库

        功能：
        1. 读取本地语言包 JSON 文件
        2. 扁平化为 key-value 格式
        3. 与 Notion 数据库比对，删除冗余数据
        4. 批量写入新增数据到 Notion
        """
        # 解析配置：app_name:database_id,app_name:database_id
        config_items = self.web_lang_config.split(',')

        for config_item in config_items:
            config_item = config_item.strip()
            if ':' not in config_item:
                logger.warning(f"配置格式错误，跳过: {config_item}")
                continue

            app_name, database_id = config_item.split(':', 1)
            app_name = app_name.strip()
            database_id = database_id.strip().replace("-", "")

            self._push_single_app(app_name, database_id)

        logger.info(f"\n{'='*60}")
        logger.success("所有应用处理完成!")
        logger.info(f"{'='*60}")

    def _push_single_app(self, app_name: str, database_id: str):
        """推送单个应用的语言包"""
        logger.info(f"\n{'='*60}")
        logger.info(f"处理应用: {app_name}")
        logger.info(f"Database ID: {database_id}")
        logger.info(f"{'='*60}")

        # 拼接语言包路径
        lang_pack_path = self._get_lang_pack_path(app_name)
        logger.info(f"语言包路径: {lang_pack_path}")

        # 加载语言包到 DataFrame
        df = load_lang_packs_to_dataframe(lang_pack_path)
        if df.empty:
            logger.error(f"应用 {app_name} 加载语言包失败，跳过")
            return

        logger.info(f"DataFrame 形状: {df.shape}")
        logger.info(f"列: {df.columns.tolist()}")

        # 获取 Notion 中已存在的数据
        existing_records = fetch_database_to_dataframe(
            self.client, database_id)

        # 获取已存在的 key 集合
        if not existing_records.empty and '名称' in existing_records.columns:
            existing_keys = set(existing_records['名称'].tolist())
            logger.info(f"Notion 中已存在 {len(existing_keys)} 个 key")
        else:
            existing_keys = set()
            logger.info("Notion 中暂无数据")

        # 清理 Notion 中本地不存在的 key
        self._cleanup_deleted_keys(df, existing_records, existing_keys)

        # 添加新增的数据
        self._add_new_keys(app_name, df, existing_keys, database_id)

    def _cleanup_deleted_keys(
        self,
        df: pd.DataFrame,
        existing_records: pd.DataFrame,
        existing_keys: set
    ):
        """清理 Notion 中本地已删除的 key"""
        local_keys = set(df['key'].tolist())
        keys_to_delete = existing_keys - local_keys

        if not keys_to_delete:
            logger.info("没有需要删除的数据")
            return

        logger.warning(f"发现 {len(keys_to_delete)} 个本地不存在的 key，准备删除")

        # 找到需要删除的 page_id
        page_ids_to_delete = [
            record['page_id']
            for _, record in existing_records.iterrows()
            if record['名称'] in keys_to_delete
        ]

        if page_ids_to_delete:
            logger.info(f"开始删除 {len(page_ids_to_delete)} 个页面...")
            delete_result = batch_delete_pages(self.client, page_ids_to_delete)

            if isinstance(delete_result, dict):
                logger.success(
                    f"删除完成! 成功: {delete_result['success']}, "
                    f"失败: {delete_result['failed']}"
                )
            else:
                logger.success("删除完成!")

    def _add_new_keys(
        self,
        app_name: str,
        df: pd.DataFrame,
        existing_keys: set,
        database_id: str
    ):
        """添加新增的 key 到 Notion"""
        new_rows = df[~df['key'].isin(existing_keys)]

        if new_rows.empty:
            logger.info(f"应用 {app_name} 没有需要新增的数据")
            return

        logger.info(f"需要新增 {len(new_rows)} 条数据")

        # 构建 Notion properties 列表
        properties_list = []
        for _, row in tqdm(new_rows.iterrows(), total=len(new_rows), desc=f"构建 {app_name} 数据"):
            properties = {
                "名称": {
                    "title": [{"text": {"content": row['key']}}]
                },
                "zh": {
                    "rich_text": [{"text": {"content": str(row.get('zh', ''))}}]
                },
                "en": {
                    "rich_text": [{"text": {"content": str(row.get('en', ''))}}]
                }
            }
            properties_list.append(properties)

        # 批量写入 Notion
        logger.info(f"开始写入 {app_name} 到 Notion...")
        result = batch_create_pages(self.client, database_id, properties_list)

        if isinstance(result, dict):
            logger.success(
                f"{app_name} 写入完成! 成功: {result['success']}, "
                f"失败: {result['failed']}, 总计: {result['total']}"
            )
            if result['failed'] > 0:
                logger.warning(f"失败的条目数: {len(result['failed_items'])}")
        else:
            logger.success(f"{app_name} 写入完成!")

    def sync(self):
        """从 Notion 数据库同步前端语言包到本地

        功能：
        1. 从 Notion 获取所有语言包数据
        2. 按语言分组，构建扁平化字典
        3. 还原为嵌套 JSON 结构
        4. 写入本地 JSON 文件（覆盖）
        """
        # 解析配置：app_name:database_id,app_name:database_id
        config_items = self.web_lang_config.split(',')

        for config_item in config_items:
            config_item = config_item.strip()
            if ':' not in config_item:
                logger.warning(f"配置格式错误，跳过: {config_item}")
                continue

            app_name, database_id = config_item.split(':', 1)
            app_name = app_name.strip()
            database_id = database_id.strip().replace("-", "")

            self._sync_single_app(app_name, database_id)

        logger.info(f"\n{'='*60}")
        logger.success("所有应用同步完成!")
        logger.info(f"{'='*60}")

    def _sync_single_app(self, app_name: str, database_id: str):
        """同步单个应用的语言包"""
        logger.info(f"\n{'='*60}")
        logger.info(f"处理应用: {app_name}")
        logger.info(f"Database ID: {database_id}")
        logger.info(f"{'='*60}")

        # 拼接语言包路径
        lang_pack_path = self._get_lang_pack_path(app_name)
        logger.info(f"语言包路径: {lang_pack_path}")

        # 确保目录存在
        lang_pack_path.mkdir(parents=True, exist_ok=True)

        # 从 Notion 获取所有数据
        logger.info("正在从 Notion 获取数据...")
        df = fetch_database_to_dataframe(self.client, database_id)

        if df.empty:
            logger.warning(f"应用 {app_name} 从 Notion 获取的数据为空")
            return

        logger.info(f"获取到 {len(df)} 条数据")
        logger.info(f"列: {df.columns.tolist()}")

        # 检查必要的列是否存在
        if '名称' not in df.columns:
            logger.error(f"应用 {app_name} 数据中缺少 '名称' 列")
            return

        # 处理每种语言
        lang_columns = [
            col for col in df.columns if col not in ['名称', 'page_id']]

        if not lang_columns:
            logger.warning(f"应用 {app_name} 没有找到语言列")
            return

        logger.info(f"找到语言列: {lang_columns}")

        for lang_code in lang_columns:
            write_lang_json_file(df, lang_code, lang_pack_path)

    def _get_lang_pack_path(self, app_name: str) -> Path:
        """获取语言包路径"""
        lang_pack_path = Path(__file__).parent / \
            f"../../web/src/app/{app_name}/locales/"
        return lang_pack_path.resolve()
