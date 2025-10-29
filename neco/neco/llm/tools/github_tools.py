import json
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from langchain_core.tools import tool
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

# 安全配置
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
GITHUB_API_BASE = "https://api.github.com"


def _validate_github_url(url: str) -> bool:
    """
    验证GitHub API URL的安全性

    Args:
        url: 待验证的URL

    Returns:
        bool: URL是否安全

    Raises:
        ValueError: URL不安全时抛出异常
    """
    try:
        parsed = urlparse(url)

        # 检查协议
        if parsed.scheme != 'https':
            raise ValueError(f"GitHub API仅支持HTTPS协议")

        # 检查域名
        if parsed.netloc != 'api.github.com':
            raise ValueError(f"仅支持GitHub官方API域名")

        return True

    except Exception as e:
        raise ValueError(f"URL验证失败: {e}")


def _validate_datetime_format(date_str: str) -> bool:
    """
    验证日期时间格式是否符合ISO 8601标准

    Args:
        date_str: 日期时间字符串

    Returns:
        bool: 格式是否正确

    Raises:
        ValueError: 格式不正确时抛出异常
    """
    try:
        # 尝试解析ISO 8601格式
        datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return True
    except ValueError:
        raise ValueError(f"日期格式错误，应为ISO 8601格式，如: 2025-09-08T00:00:00Z")


def _process_commits_data(commits: List[Dict]) -> Dict:
    """
    处理GitHub commits数据，按用户分组并排序

    Args:
        commits: GitHub API返回的commits数据列表

    Returns:
        Dict: 按用户名分组的commits数据
            格式: {
                "用户名": [
                    {
                        "message": "commit消息",
                        "date": "提交日期"
                    }
                ]
            }
    """
    if not commits:
        logger.warning("commits数据为空")
        return {}

    user_commits = {}

    for commit in commits:
        try:
            # 提取所需字段
            commit_info = commit.get('commit', {})
            author_info = commit_info.get('author', {})

            author_name = author_info.get('name', 'Unknown')
            commit_message = commit_info.get('message', '')
            commit_date = author_info.get('date', '')

            # 初始化用户列表
            if author_name not in user_commits:
                user_commits[author_name] = []

            # 添加commit记录
            user_commits[author_name].append({
                'message': commit_message,
                'date': commit_date
            })

        except Exception as e:
            logger.warning(f"处理commit数据时出错: {e}")
            continue

    # 按时间排序（从新到旧）
    for author_name in user_commits:
        user_commits[author_name].sort(
            key=lambda x: x['date'],
            reverse=True
        )

    logger.info(f"成功处理 {len(user_commits)} 个用户的commits数据")
    return user_commits


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def _fetch_github_commits(url: str, headers: Dict) -> List[Dict]:
    """
    获取GitHub commits数据，支持重试机制

    Args:
        url: GitHub API URL
        headers: 请求头

    Returns:
        List[Dict]: commits数据列表

    Raises:
        ValueError: 请求失败时抛出异常
    """
    logger.info(f"开始获取GitHub commits数据: {url}")

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            verify=True
        )

        # 检查响应状态
        if response.status_code == 401:
            raise ValueError("GitHub API认证失败，请检查token是否有效")
        elif response.status_code == 403:
            raise ValueError("GitHub API访问被拒绝，可能超出了速率限制")
        elif response.status_code == 404:
            raise ValueError("GitHub仓库不存在或无访问权限")
        elif response.status_code >= 400:
            logger.error(
                f"GitHub API返回错误状态: {response.status_code}, 响应: {response.text[:500]}")
            raise ValueError(f"GitHub API请求失败，状态码: {response.status_code}")

        commits_data = response.json()

        logger.info(f"成功获取 {len(commits_data)} 条commits记录")
        return commits_data

    except requests.exceptions.Timeout:
        logger.error(f"GitHub API请求超时: {url}")
        raise ValueError(f"请求超时: {url}")

    except requests.exceptions.ConnectionError as e:
        logger.error(f"GitHub API连接错误: {e}")
        raise ValueError(f"连接失败: {e}")

    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API请求异常: {e}")
        raise ValueError(f"请求失败: {e}")

    except json.JSONDecodeError as e:
        logger.error(f"GitHub API响应JSON解析失败: {e}")
        raise ValueError(f"响应数据格式错误: {e}")

    except Exception as e:
        logger.error(f"获取GitHub commits时发生未知错误: {e}")
        raise ValueError(f"请求处理失败: {e}")


@tool()
def get_github_commits(
    owner: str,
    repo: str,
    since: str,
    until: str,
    token: Optional[str] = None
) -> str:
    """
    获取指定GitHub仓库在指定时间范围内的commits记录，并按用户分组处理。请根据用户指定的时间进行查询，不要猜测

    Args:
        owner (str): GitHub仓库所有者用户名或组织名
        repo (str): GitHub仓库名称
        since (str): 开始时间，ISO 8601格式，如: 2025-09-08T00:00:00Z
        until (str): 结束时间，ISO 8601格式，如: 2025-09-15T00:00:00Z  
        token (str, optional): GitHub Personal Access Token，用于提高API限制和访问私有仓库

    Returns:
        str: 按用户分组的commits数据JSON字符串，格式为:
            {
                "用户名": [
                    {
                        "message": "commit消息",
                        "date": "提交日期"
                    }
                ]
            }

    Raises:
        ValueError: 当参数无效或请求失败时抛出
    """
    # 参数验证
    if not owner or not isinstance(owner, str):
        raise ValueError("owner参数不能为空且必须是字符串")

    if not repo or not isinstance(repo, str):
        raise ValueError("repo参数不能为空且必须是字符串")

    if not since or not isinstance(since, str):
        raise ValueError("since参数不能为空且必须是字符串")

    if not until or not isinstance(until, str):
        raise ValueError("until参数不能为空且必须是字符串")

    # 验证日期格式
    _validate_datetime_format(since)
    _validate_datetime_format(until)

    # 构建API URL
    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
    params = {
        'since': since,
        'until': until,
        'per_page': 100  # 每页最大记录数
    }

    # 构建完整URL
    full_url = f"{api_url}?since={since}&until={until}&per_page=100"

    # 验证URL安全性
    _validate_github_url(full_url)

    # 构建请求头
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Metis-GitHub-Tools/1.0'
    }

    # 如果提供了token，添加认证头
    if token:
        headers['Authorization'] = f'token {token}'
        logger.info(f"使用GitHub token进行认证")
    else:
        logger.warning(f"未提供GitHub token，将使用未认证的请求（有速率限制）")

    # 记录请求信息（脱敏）
    logger.info(
        f"获取GitHub commits",
        extra={
            "owner": owner,
            "repo": repo,
            "since": since,
            "until": until,
            "has_token": bool(token)
        }
    )

    try:
        # 获取commits数据
        commits_data = _fetch_github_commits(full_url, headers)

        # 处理数据
        processed_data = _process_commits_data(commits_data)

        # 转换为JSON字符串
        result_json = json.dumps(processed_data, ensure_ascii=False, indent=2)

        logger.info(
            f"成功获取并处理GitHub commits数据",
            extra={
                "owner": owner,
                "repo": repo,
                "users_count": len(processed_data),
                "total_commits": sum(len(commits) for commits in processed_data.values())
            }
        )

        return result_json

    except Exception as e:
        logger.error(
            f"获取GitHub commits失败",
            extra={
                "owner": owner,
                "repo": repo,
                "since": since,
                "until": until,
                "error": str(e)
            }
        )
        raise


@tool()
def get_github_commits_with_pagination(
    owner: str,
    repo: str,
    since: str,
    until: str,
    token: Optional[str] = None,
    max_pages: int = 10
) -> str:
    """
    获取指定GitHub仓库在指定时间范围内的commits记录（支持分页），并按用户分组处理。

    当commits数量较多时，GitHub API会分页返回结果。此工具可以自动处理分页，获取完整的commits数据。

    Args:
        owner (str): GitHub仓库所有者用户名或组织名
        repo (str): GitHub仓库名称
        since (str): 开始时间，ISO 8601格式，如: 2025-09-08T00:00:00Z
        until (str): 结束时间，ISO 8601格式，如: 2025-09-15T00:00:00Z
        token (str, optional): GitHub Personal Access Token，用于提高API限制和访问私有仓库
        max_pages (int): 最大获取页数，默认10页，避免请求过多数据

    Returns:
        str: 按用户分组的commits数据JSON字符串，格式为:
            {
                "用户名": [
                    {
                        "message": "commit消息", 
                        "date": "提交日期"
                    }
                ]
            }

    Raises:
        ValueError: 当参数无效或请求失败时抛出
    """
    # 参数验证
    if not owner or not isinstance(owner, str):
        raise ValueError("owner参数不能为空且必须是字符串")

    if not repo or not isinstance(repo, str):
        raise ValueError("repo参数不能为空且必须是字符串")

    if not since or not isinstance(since, str):
        raise ValueError("since参数不能为空且必须是字符串")

    if not until or not isinstance(until, str):
        raise ValueError("until参数不能为空且必须是字符串")

    if not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages必须是正整数")

    # 验证日期格式
    _validate_datetime_format(since)
    _validate_datetime_format(until)

    # 构建请求头
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Metis-GitHub-Tools/1.0'
    }

    if token:
        headers['Authorization'] = f'token {token}'
        logger.info(f"使用GitHub token进行认证")
    else:
        logger.warning(f"未提供GitHub token，将使用未认证的请求（有速率限制）")

    logger.info(
        f"开始分页获取GitHub commits",
        extra={
            "owner": owner,
            "repo": repo,
            "since": since,
            "until": until,
            "max_pages": max_pages,
            "has_token": bool(token)
        }
    )

    all_commits = []
    page = 1

    try:
        while page <= max_pages:
            # 构建API URL
            api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
            full_url = f"{api_url}?since={since}&until={until}&per_page=100&page={page}"

            # 验证URL安全性
            _validate_github_url(full_url)

            logger.info(f"获取第 {page} 页数据")

            # 获取当前页数据
            page_commits = _fetch_github_commits(full_url, headers)

            # 如果当前页没有数据，说明已经获取完毕
            if not page_commits:
                logger.info(f"第 {page} 页无数据，停止分页获取")
                break

            all_commits.extend(page_commits)
            logger.info(f"第 {page} 页获取到 {len(page_commits)} 条记录")

            # 如果返回的记录数少于100，说明这是最后一页
            if len(page_commits) < 100:
                logger.info(f"第 {page} 页数据不足100条，为最后一页")
                break

            page += 1

        logger.info(f"分页获取完成，总共获取 {len(all_commits)} 条commits记录")

        # 处理数据
        processed_data = _process_commits_data(all_commits)

        # 转换为JSON字符串
        result_json = json.dumps(processed_data, ensure_ascii=False, indent=2)

        logger.info(
            f"成功获取并处理GitHub commits数据（分页）",
            extra={
                "owner": owner,
                "repo": repo,
                "pages_fetched": page - 1,
                "users_count": len(processed_data),
                "total_commits": sum(len(commits) for commits in processed_data.values())
            }
        )

        return result_json

    except Exception as e:
        logger.error(
            f"分页获取GitHub commits失败",
            extra={
                "owner": owner,
                "repo": repo,
                "since": since,
                "until": until,
                "page": page,
                "error": str(e)
            }
        )
        raise
