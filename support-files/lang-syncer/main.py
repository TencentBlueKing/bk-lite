#!/usr/bin/env python3
"""语言包同步工具"""

import fire
import os
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv
import json
import pandas as pd
from tqdm import tqdm
from notion_client import query_datasource, create_page, fetch_datasource, delete_page

# 加载环境变量
load_dotenv()


def flatten_json(data: dict, parent_key: str = "", sep: str = ".") -> dict:
    """
    将嵌套的 JSON 对象扁平化为 key path 格式
    
    Args:
        data: JSON 数据
        parent_key: 父级 key
        sep: 分隔符
        
    Returns:
        扁平化的字典，key 为 json path，value 为对应的值
        
    Example:
        {"common": {"actions": "操作"}} -> {"common.actions": "操作"}
    """
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def load_lang_packs_to_dataframe(lang_pack_path: Path) -> pd.DataFrame:
    """
    加载语言包目录下的所有 JSON 文件到 DataFrame
    
    Args:
        lang_pack_path: 语言包目录路径
        
    Returns:
        DataFrame，列为 key, en, zh 等
    """
    if not lang_pack_path.exists():
        logger.error(f"语言包路径不存在: {lang_pack_path}")
        return pd.DataFrame()
    
    # 收集所有 JSON 文件
    json_files = list(lang_pack_path.glob("*.json"))
    if not json_files:
        logger.warning(f"未找到 JSON 文件: {lang_pack_path}")
        return pd.DataFrame()
    
    logger.info(f"找到 {len(json_files)} 个语言包文件")
    
    # 存储每个语言的扁平化数据
    lang_data = {}
    
    for json_file in json_files:
        lang_code = json_file.stem  # 获取文件名（不含扩展名），如 'zh', 'en'
        logger.info(f"加载语言包: {lang_code}.json")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                flattened = flatten_json(data)
                lang_data[lang_code] = flattened
        except Exception as e:
            logger.error(f"加载 {json_file} 失败: {e}")
            continue
    
    # 收集所有唯一的 key
    all_keys = set()
    for flattened in lang_data.values():
        all_keys.update(flattened.keys())
    
    all_keys = sorted(all_keys)
    logger.info(f"共有 {len(all_keys)} 个翻译 key")
    
    # 构建 DataFrame
    df_data = {"key": all_keys}
    
    for lang_code, flattened in lang_data.items():
        df_data[lang_code] = [flattened.get(key, "") for key in all_keys]
    
    df = pd.DataFrame(df_data)
    return df


class LangSyncer:
    """语言包同步CLI工具"""

    def push_web_pack(self):
        """推送前端语言包到数据库"""
        notion_token = os.getenv("NOTION_TOKEN")
        web_lang_config = os.getenv("WEB_LANG_CONFIG")
        
        if not notion_token or not web_lang_config:
            logger.error("缺少必要的环境变量: NOTION_TOKEN 或 WEB_LANG_CONFIG")
            return
        
        # 解析配置：app_name:database_id,app_name:database_id
        config_items = web_lang_config.split(',')
        
        for config_item in config_items:
            config_item = config_item.strip()
            if ':' not in config_item:
                logger.warning(f"配置格式错误，跳过: {config_item}")
                continue
            
            app_name, database_id = config_item.split(':', 1)
            app_name = app_name.strip()
            database_id = database_id.strip().replace("-", "")
            
            logger.info(f"\n{'='*60}")
            logger.info(f"处理应用: {app_name}")
            logger.info(f"Database ID: {database_id}")
            logger.info(f"{'='*60}")
            
            # 拼接语言包路径
            lang_pack_path = Path(__file__).parent / f"../../web/src/app/{app_name}/locales/"
            lang_pack_path = lang_pack_path.resolve()
            
            logger.info(f"语言包路径: {lang_pack_path}")
            
            # 加载语言包到 DataFrame
            df = load_lang_packs_to_dataframe(lang_pack_path)
            
            if df.empty:
                logger.error(f"应用 {app_name} 加载语言包失败，跳过")
                continue
            
            logger.info(f"DataFrame 形状: {df.shape}")
            logger.info(f"列: {df.columns.tolist()}")
            
            # 获取 Notion 中所有已存在的 key
            logger.info("正在获取 Notion 中已存在的 key...")
            
            existing_records = fetch_datasource(
                database_id,
                notion_token,
                return_type='dataframe'
            )
            
            # 获取已存在的 key 集合
            if not existing_records.empty and '名称' in existing_records.columns:
                existing_keys = set(existing_records['名称'].tolist())
                logger.info(f"Notion 中已存在 {len(existing_keys)} 个 key")
            else:
                existing_keys = set()
                logger.info("Notion 中暂无数据")
            
            # 检查并删除本地不存在的 key
            local_keys = set(df['key'].tolist())
            keys_to_delete = existing_keys - local_keys
            
            if keys_to_delete:
                logger.warning(f"发现 {len(keys_to_delete)} 个本地不存在的 key，准备删除")
                
                # 找到需要删除的 page_id
                page_ids_to_delete = []
                for _, record in existing_records.iterrows():
                    if record['名称'] in keys_to_delete:
                        page_ids_to_delete.append(record['page_id'])
                
                if page_ids_to_delete:
                    logger.info(f"开始删除 {len(page_ids_to_delete)} 个页面...")
                    delete_result = delete_page(page_ids_to_delete, notion_token)
                    
                    if isinstance(delete_result, dict):
                        logger.success(f"删除完成! 成功: {delete_result['success']}, 失败: {delete_result['failed']}")
                    else:
                        logger.success("删除完成!")
            else:
                logger.info("没有需要删除的数据")
            
            # 过滤出需要新增的数据
            new_rows = df[~df['key'].isin(existing_keys)]
            
            if new_rows.empty:
                logger.info(f"应用 {app_name} 没有需要新增的数据")
                continue
            
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
            result = create_page(database_id, notion_token, properties_list)
            
            if isinstance(result, dict):
                logger.success(f"{app_name} 写入完成! 成功: {result['success']}, 失败: {result['failed']}, 总计: {result['total']}")
                if result['failed'] > 0:
                    logger.warning(f"失败的条目数: {len(result['failed_items'])}")
            else:
                logger.success(f"{app_name} 写入完成!")
        
        logger.info(f"\n{'='*60}")
        logger.success("所有应用处理完成!")
        logger.info(f"{'='*60}")


    def sync_web_pack(self):
        """从数据库同步节点管理前端语言包"""
        # 从环境变量读取配置
        database_id = os.getenv("NODE_MANAGER_WEB_DATABASE_ID")
        notion_token = os.getenv("NOTION_TOKEN")
        
        if not database_id or not notion_token:
            logger.error("缺少必要的环境变量: NODE_MANAGER_WEB_DATABASE_ID 或 NOTION_TOKEN")
            return
        
        # 拼接语言包路径
        app_name = "node-manager"
        lang_pack_path = Path(__file__).parent / f"../../web/src/app/{app_name}/locales/"
        lang_pack_path = lang_pack_path.resolve()
        
        logger.info(f"Database ID: {database_id}")
        logger.info(f"语言包路径: {lang_pack_path}")
        
        pass


def main():
    """CLI入口"""
    fire.Fire(LangSyncer)


if __name__ == "__main__":
    main()
