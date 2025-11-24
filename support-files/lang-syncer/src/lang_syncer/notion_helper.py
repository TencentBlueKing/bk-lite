"""Notion API 辅助函数"""

import httpx
import pandas as pd
from loguru import logger
from notion_client import Client
from tqdm import tqdm

from lang_syncer.config import Config
from lang_syncer.exceptions import NotionAPIError


def normalize_database_id(database_id: str) -> str:
    """标准化数据库 ID 为 UUID 格式（带连字符）

    Args:
        database_id: 原始数据库 ID

    Returns:
        标准 UUID 格式的数据库 ID
    """
    database_id = database_id.replace("-", "")
    if len(database_id) != 32:
        raise ValueError(f"无效的数据库 ID: {database_id}")

    return f"{database_id[:8]}-{database_id[8:12]}-{database_id[12:16]}-{database_id[16:20]}-{database_id[20:]}"


def _query_database(client: Client, database_id: str, **kwargs) -> dict:
    """查询 Notion 数据库

    直接使用 httpx 查询，因为 SDK 的 request 方法有问题

    Args:
        client: Notion 客户端
        database_id: 数据库 ID
        **kwargs: 查询参数

    Returns:
        查询结果

    Raises:
        NotionAPIError: 查询失败
    """
    database_id = normalize_database_id(database_id)

    try:
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            headers={
                "Authorization": f"Bearer {client.options.auth}",
                "Notion-Version": Config.NOTION_API_VERSION,
                "Content-Type": "application/json",
            },
            json=kwargs,
            timeout=Config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise NotionAPIError(f"查询数据库失败: {e}")


def fetch_database_to_dataframe(client: Client, database_id: str) -> pd.DataFrame:
    """从 Notion 数据库获取所有数据并转换为 DataFrame

    Args:
        client: Notion 客户端
        database_id: 数据库 ID

    Returns:
        DataFrame，包含 page_id 和所有属性列

    Raises:
        NotionAPIError: 获取数据失败
    """
    database_id = normalize_database_id(database_id)
    all_results = []
    has_more = True
    start_cursor = None

    try:
        while has_more:
            payload = {"page_size": Config.BATCH_SIZE}
            if start_cursor:
                payload["start_cursor"] = start_cursor

            response = _query_database(client, database_id, **payload)
            all_results.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

    except Exception as e:
        raise NotionAPIError(f"获取数据库数据失败: {e}")

    # 解析为 DataFrame
    return _parse_pages_to_dataframe(all_results)


def _parse_pages_to_dataframe(pages: list[dict]) -> pd.DataFrame:
    """将 Notion 页面列表解析为 DataFrame

    Args:
        pages: Notion 页面列表

    Returns:
        DataFrame
    """
    parsed_data = []

    for page in pages:
        row = {"page_id": page["id"]}

        for prop_name, prop_value in page["properties"].items():
            row[prop_name] = _extract_property_value(prop_value)

        parsed_data.append(row)

    return pd.DataFrame(parsed_data)


def _extract_property_value(prop_value: dict):
    """提取 Notion 属性值

    Args:
        prop_value: Notion 属性值字典

    Returns:
        提取的值
    """
    prop_type = prop_value["type"]

    if prop_type == "title":
        texts = prop_value.get("title", [])
        return "".join([t["plain_text"] for t in texts])
    elif prop_type == "rich_text":
        texts = prop_value.get("rich_text", [])
        return "".join([t["plain_text"] for t in texts])
    elif prop_type == "number":
        return prop_value.get("number")
    elif prop_type == "select":
        select = prop_value.get("select")
        return select["name"] if select else None

    return None


def batch_create_pages(client: Client, database_id: str, properties_list: list[dict]) -> dict:
    """批量创建 Notion 页面

    Args:
        client: Notion 客户端
        database_id: 数据库 ID
        properties_list: 属性列表

    Returns:
        包含成功/失败统计的字典
    """
    database_id = normalize_database_id(database_id)
    success_count = 0
    failed_count = 0
    failed_items = []

    for idx, properties in enumerate(tqdm(properties_list, desc="写入 Notion")):
        try:
            client.pages.create(
                parent={"database_id": database_id}, properties=properties)
            success_count += 1
        except Exception as e:
            failed_count += 1
            failed_items.append({"index": idx, "error": str(e)})
            logger.error(f"创建页面失败 (索引 {idx}): {e}")

    return {"success": success_count, "failed": failed_count, "total": len(properties_list), "failed_items": failed_items}


def batch_delete_pages(client: Client, page_ids: list[str]) -> dict:
    """批量删除 Notion 页面

    Args:
        client: Notion 客户端
        page_ids: 页面 ID 列表

    Returns:
        包含成功/失败统计的字典
    """
    success_count = 0
    failed_count = 0

    for page_id in tqdm(page_ids, desc="删除页面"):
        try:
            client.pages.update(page_id=page_id, archived=True)
            success_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"删除页面失败 ({page_id}): {e}")

    return {"success": success_count, "failed": failed_count, "total": len(page_ids)}
