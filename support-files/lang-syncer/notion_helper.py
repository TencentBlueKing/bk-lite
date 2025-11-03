"""Notion API 辅助函数"""

import pandas as pd
import httpx
from notion_client import Client
from loguru import logger
from tqdm import tqdm


def _query_database(client: Client, database_id: str, **kwargs):
    """直接使用 httpx 查询数据库 (SDK 的 request 方法有问题)"""
    # 使用与测试时相同的 API 版本
    notion_version = "2022-06-28"
    response = httpx.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers={
            "Authorization": f"Bearer {client.options.auth}",
            "Notion-Version": notion_version,
            "Content-Type": "application/json",
        },
        json=kwargs,
        timeout=client.options.timeout_ms / 1000,
    )
    response.raise_for_status()
    return response.json()


def fetch_database_to_dataframe(client: Client, database_id: str) -> pd.DataFrame:
    """从 Notion 数据库获取所有数据并转换为 DataFrame

    Args:
        client: Notion 客户端
        database_id: 数据库 ID（可以是带或不带连字符的格式）

    Returns:
        DataFrame，包含 page_id 和所有属性列
    """
    # 确保 database_id 是标准的 UUID 格式（带连字符）
    if len(database_id) == 32 and "-" not in database_id:
        database_id = f"{database_id[:8]}-{database_id[8:12]}-{database_id[12:16]}-{database_id[16:20]}-{database_id[20:]}"

    all_results = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        # 使用我们的辅助函数而不是 SDK 的 request 方法
        response = _query_database(client, database_id, **payload)
        all_results.extend(response.get("results", []))
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    # 解析为 DataFrame
    parsed_data = []
    for page in all_results:
        row = {"page_id": page["id"]}

        for prop_name, prop_value in page["properties"].items():
            prop_type = prop_value["type"]

            if prop_type == "title":
                texts = prop_value.get("title", [])
                row[prop_name] = "".join([t["plain_text"] for t in texts])
            elif prop_type == "rich_text":
                texts = prop_value.get("rich_text", [])
                row[prop_name] = "".join([t["plain_text"] for t in texts])
            elif prop_type == "number":
                row[prop_name] = prop_value.get("number")
            elif prop_type == "select":
                select = prop_value.get("select")
                row[prop_name] = select["name"] if select else None
            else:
                row[prop_name] = None

        parsed_data.append(row)

    return pd.DataFrame(parsed_data)


def batch_create_pages(client: Client, database_id: str, properties_list: list[dict]) -> dict:
    """批量创建 Notion 页面

    Args:
        client: Notion 客户端
        database_id: 数据库 ID（可以是带或不带连字符的格式）
        properties_list: 属性列表

    Returns:
        包含成功/失败统计的字典
    """
    # 确保 database_id 是标准的 UUID 格式（带连字符）
    # Notion API 要求使用标准 UUID 格式
    if len(database_id) == 32 and "-" not in database_id:
        # 将无连字符格式转换为标准 UUID 格式
        database_id = f"{database_id[:8]}-{database_id[8:12]}-{database_id[12:16]}-{database_id[16:20]}-{database_id[20:]}"

    success_count = 0
    failed_count = 0
    failed_items = []

    for idx, properties in enumerate(tqdm(properties_list, desc="写入 Notion")):
        try:
            client.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
            success_count += 1
        except Exception as e:
            failed_count += 1
            failed_items.append({"index": idx, "error": str(e)})
            logger.error(f"创建页面失败 (索引 {idx}): {e}")

    return {
        "success": success_count,
        "failed": failed_count,
        "total": len(properties_list),
        "failed_items": failed_items
    }


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

    return {
        "success": success_count,
        "failed": failed_count,
        "total": len(page_ids)
    }
