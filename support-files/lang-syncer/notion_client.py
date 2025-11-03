"""
Notion API 客户端封装
提供 Database 的 CRUD 操作
"""
import requests
import pandas as pd
import time
from tqdm import tqdm


def _make_request_with_retry(method: str, url: str, headers: dict, **kwargs) -> requests.Response:
    """
    发送请求并处理速率限制
    
    Args:
        method: HTTP 方法 ('GET', 'POST', 'PATCH' 等)
        url: 请求 URL
        headers: 请求头
        **kwargs: 其他请求参数
        
    Returns:
        响应对象
    """
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        response = requests.request(method, url, headers=headers, **kwargs)
        
        # 如果遇到速率限制
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"遇到速率限制，等待 {retry_after} 秒后重试...")
            time.sleep(retry_after)
            retry_count += 1
            continue
        
        return response
    
    # 重试次数用尽，返回最后一次响应
    return response


def _get_notion_headers(token: str) -> dict:
    """获取 Notion API 请求头"""
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }


def _query_database_raw(database_id: str, token: str) -> list[dict]:
    """
    查询 Notion database 原始数据（包含 page_id）
    
    Returns:
        list[dict]: 原始页面对象列表
    """
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = _get_notion_headers(token)
    
    all_pages = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"错误: {response.status_code}")
            print(response.text)
            break
        
        response_data = response.json()
        all_pages.extend(response_data.get('results', []))
        has_more = response_data.get('has_more', False)
        next_cursor = response_data.get('next_cursor')
    
    return all_pages


def extract_plain_text(prop_value):
    """从 Notion 属性中提取 plain_text"""
    prop_type = prop_value.get('type')
    
    if prop_type == 'title':
        texts = prop_value.get('title', [])
        return ''.join([t.get('plain_text', '') for t in texts])
    elif prop_type == 'rich_text':
        texts = prop_value.get('rich_text', [])
        return ''.join([t.get('plain_text', '') for t in texts])
    elif prop_type == 'number':
        return prop_value.get('number')
    elif prop_type == 'select':
        select = prop_value.get('select')
        return select.get('name') if select else None
    elif prop_type == 'multi_select':
        items = prop_value.get('multi_select', [])
        return [item.get('name') for item in items]
    elif prop_type == 'date':
        date = prop_value.get('date')
        return date.get('start') if date else None
    elif prop_type == 'checkbox':
        return prop_value.get('checkbox')
    elif prop_type == 'url':
        return prop_value.get('url')
    elif prop_type == 'email':
        return prop_value.get('email')
    elif prop_type == 'phone_number':
        return prop_value.get('phone_number')
    elif prop_type == 'status':
        status = prop_value.get('status')
        return status.get('name') if status else None
    else:
        return None


def fetch_datasource(database_id: str, token: str, return_type: str = 'dataframe') -> pd.DataFrame | list[dict]:
    """
    获取 Notion database 数据
    自动处理分页，获取所有数据
    
    Args:
        database_id: Notion database ID
        token: Notion API token
        return_type: 返回类型，'dataframe' 或 'list'
        
    Returns:
        pd.DataFrame 或 list[dict]: 数据，包含 page_id 列
    """
    all_pages = _query_database_raw(database_id, token)
    
    parsed_data = []
    for page in all_pages:
        page_data = {'page_id': page['id']}
        properties = page.get('properties', {})
        
        for prop_name, prop_value in properties.items():
            page_data[prop_name] = extract_plain_text(prop_value)
        
        parsed_data.append(page_data)
    
    if return_type == 'dataframe':
        return pd.DataFrame(parsed_data)
    else:
        return parsed_data


def query_datasource(
    database_id: str, 
    token: str, 
    filter_conditions: dict = None,
    sorts: list[dict] = None,
    page_size: int = 100,
    return_type: str = 'dataframe'
) -> pd.DataFrame | list[dict]:
    """
    查询 Notion database 数据（支持过滤和排序）
    自动处理分页，获取所有数据
    
    Args:
        database_id: Notion database ID
        token: Notion API token
        filter_conditions: 过滤条件（可选）
        sorts: 排序条件列表（可选）
        page_size: 每页大小，默认 100
        return_type: 返回类型，'dataframe' 或 'list'
        
    Returns:
        pd.DataFrame 或 list[dict]: 数据，包含 page_id 列
    
    Example:
        # 过滤示例
        filter_conditions = {
            "property": "Status",
            "select": {"equals": "Done"}
        }
        
        # 排序示例
        sorts = [
            {"property": "Created", "direction": "descending"},
            {"property": "Name", "direction": "ascending"}
        ]
        
        df = query_datasource(database_id, token, filter_conditions, sorts)
    """
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = _get_notion_headers(token)
    
    all_pages = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {"page_size": page_size}
        
        if filter_conditions:
            payload["filter"] = filter_conditions
        
        if sorts:
            payload["sorts"] = sorts
        
        if next_cursor:
            payload["start_cursor"] = next_cursor
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"错误: {response.status_code}")
            print(response.text)
            break
        
        response_data = response.json()
        all_pages.extend(response_data.get('results', []))
        has_more = response_data.get('has_more', False)
        next_cursor = response_data.get('next_cursor')
    
    # 解析数据
    parsed_data = []
    for page in all_pages:
        page_data = {'page_id': page['id']}
        properties = page.get('properties', {})
        
        for prop_name, prop_value in properties.items():
            page_data[prop_name] = extract_plain_text(prop_value)
        
        parsed_data.append(page_data)
    
    if return_type == 'dataframe':
        return pd.DataFrame(parsed_data)
    else:
        return parsed_data


def create_page(database_id: str, token: str, properties: dict | list[dict]) -> dict | list[dict]:
    """
    向 Notion database 添加一条或多条新数据
    
    Args:
        database_id: Notion database ID
        token: Notion API token
        properties: 页面属性（单个字典）或属性列表（多个字典），格式为 Notion API 的 properties 结构
        
    Returns:
        单个创建时返回页面对象，批量创建时返回结果统计 dict
    
    Example:
        # 创建单个页面
        properties = {
            "Name": {"title": [{"text": {"content": "测试标题"}}]},
            "Status": {"select": {"name": "进行中"}}
        }
        create_page(database_id, token, properties)
        
        # 批量创建页面
        properties_list = [
            {"Name": {"title": [{"text": {"content": "标题1"}}]}},
            {"Name": {"title": [{"text": {"content": "标题2"}}]}}
        ]
        create_page(database_id, token, properties_list)
    """
    url = "https://api.notion.com/v1/pages"
    headers = _get_notion_headers(token)
    
    # 如果是单个 properties
    if isinstance(properties, dict):
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"创建失败: {response.status_code}")
            print(response.text)
            return None
    
    # 如果是多个 properties
    elif isinstance(properties, list):
        success_count = 0
        failed_count = 0
        created_pages = []
        failed_items = []
        
        for idx, props in enumerate(tqdm(properties, desc="写入 Notion")):
            payload = {
                "parent": {"database_id": database_id},
                "properties": props
            }
            
            # 使用带重试的请求
            response = _make_request_with_retry('POST', url, headers, json=payload)
            
            if response.status_code == 200:
                success_count += 1
                created_pages.append(response.json())
            else:
                failed_count += 1
                failed_items.append({"index": idx, "properties": props})
                print(f"创建失败 (第 {idx + 1} 条): {response.status_code}")
                print(response.text)
            
            # 添加小延迟以避免触发速率限制（3 req/s = ~0.33s/req）
            time.sleep(0.35)
        
        return {
            "success": success_count,
            "failed": failed_count,
            "created_pages": created_pages,
            "failed_items": failed_items,
            "total": len(properties)
        }
    else:
        raise TypeError("properties 必须是 dict 或 list[dict] 类型")


def delete_page(page_id: str | list[str], token: str) -> bool | dict:
    """
    删除（归档）一个或多个 Notion 页面
    
    Args:
        page_id: 页面 ID（单个字符串）或页面 ID 列表
        token: Notion API token
        
    Returns:
        单个删除时返回 bool，批量删除时返回 dict（包含成功和失败统计）
    
    Example:
        # 删除单个页面
        delete_page("page-id-xxx", token)
        
        # 删除多个页面
        delete_page(["page-id-1", "page-id-2"], token)
    """
    # 如果是单个 page_id
    if isinstance(page_id, str):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        headers = _get_notion_headers(token)
        payload = {"archived": True}
        
        response = _make_request_with_retry('PATCH', url, headers, json=payload)
        
        if response.status_code == 200:
            return True
        else:
            print(f"删除失败: {response.status_code}")
            print(response.text)
            return False
    
    # 如果是多个 page_id
    elif isinstance(page_id, list):
        headers = _get_notion_headers(token)
        payload = {"archived": True}
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        
        for pid in tqdm(page_id, desc="删除页面"):
            url = f"https://api.notion.com/v1/pages/{pid}"
            response = _make_request_with_retry('PATCH', url, headers, json=payload)
            
            if response.status_code == 200:
                success_count += 1
            else:
                failed_count += 1
                failed_ids.append(pid)
                print(f"删除失败 ({pid}): {response.status_code}")
            
            # 添加小延迟以避免触发速率限制
            time.sleep(0.35)
        
        return {
            "success": success_count,
            "failed": failed_count,
            "failed_ids": failed_ids,
            "total": len(page_id)
        }
    else:
        raise TypeError("page_id 必须是 str 或 list[str] 类型")


def update_page(page_id: str, token: str, properties: dict) -> dict:
    """
    更新一个 Notion 页面的属性
    
    Args:
        page_id: 页面 ID
        token: Notion API token
        properties: 要更新的属性，格式为 Notion API 的 properties 结构
        
    Returns:
        dict: 更新后的页面对象，如果失败返回 None
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = _get_notion_headers(token)
    payload = {"properties": properties}
    
    response = _make_request_with_retry('PATCH', url, headers, json=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"更新失败: {response.status_code}")
        print(response.text)
        return None


def clear_and_update_datasource(database_id: str, token: str, data_list: list[dict]) -> dict:
    """
    全量更新 database：删除所有现有数据，然后写入新数据
    
    Args:
        database_id: Notion database ID
        token: Notion API token
        data_list: 新数据列表，每项为 Notion API 的 properties 结构
        
    Returns:
        dict: 操作结果统计
    """
    # 1. 获取所有现有页面
    all_pages = _query_database_raw(database_id, token)
    
    # 2. 删除所有现有页面
    deleted_count = 0
    for page in tqdm(all_pages, desc="删除旧数据"):
        if delete_page(page['id'], token):
            deleted_count += 1
    
    # 3. 写入新数据
    created_count = 0
    for properties in tqdm(data_list, desc="写入新数据"):
        if create_page(database_id, token, properties):
            created_count += 1
    
    return {
        "deleted": deleted_count,
        "created": created_count,
        "total_old": len(all_pages),
        "total_new": len(data_list)
    }
