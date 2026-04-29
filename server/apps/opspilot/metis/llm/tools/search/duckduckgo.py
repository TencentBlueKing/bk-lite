from typing import List, Optional

from duckduckgo_search import DDGS
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger


@tool
def duckduckgo_search(query: str, max_results: Optional[int], config: RunnableConfig) -> str:
    """
    Perform a search using DuckDuckGo and return the results.
    :param query: search query
    :param max_results: default is 5
    :return:
    """
    content = ""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

            formatted_results = []
            for i, result in enumerate(results, 1):
                title = result.get("title", "无标题")
                body = result.get("body", "无内容")
                href = result.get("href", "无链接")
                formatted_results.append(f"{i}. {title}\n   {body}\n   链接: {href}\n")
            content = "\n".join(formatted_results)
    except Exception as ex:
        logger.error(f"执行 DuckDuckGo 搜索失败: {ex}")
        content = str(ex)

    logger.info(f"用户:[{config['configurable']['user_id']}]执行工具[DuckDuckGo 搜索],结果:[{content}]")
    return content


@tool
def duckduckgo_search_batch(
    queries: List[str],
    max_results: Optional[int] = 5,
    config: RunnableConfig = None,
) -> dict:
    """批量执行多个 DuckDuckGo 搜索，每个查询独立执行，单条失败不中断其他查询。

    Args:
        queries: 搜索词列表
        max_results: 每个查询最多返回的结果数，默认 5
    """
    results = []
    succeeded = 0
    failed = 0

    for query in queries:
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            formatted = [{"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")} for r in raw]
            results.append({"input": query, "ok": True, "data": formatted})
            succeeded += 1
        except Exception as e:
            logger.error(f"DuckDuckGo 批量搜索失败 [{query}]: {e}")
            results.append({"input": query, "ok": False, "error": str(e)})
            failed += 1

    return {"total": len(queries), "succeeded": succeeded, "failed": failed, "results": results}
