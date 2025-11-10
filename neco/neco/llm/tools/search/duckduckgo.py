from typing import Optional

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
    content = ''
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

            formatted_results = []
            for i, result in enumerate(results, 1):
                title = result.get('title', '无标题')
                body = result.get('body', '无内容')
                href = result.get('href', '无链接')
                formatted_results.append(
                    f"{i}. {title}\n   {body}\n   链接: {href}\n")
            content = "\n".join(formatted_results)
    except Exception as ex:
        logger.error(f"执行 DuckDuckGo 搜索失败: {ex}")
        content = str(ex)

    logger.info(
        f"用户:[{config['configurable']['user_id']}]执行工具[DuckDuckGo 搜索],结果:[{content}]")
    return content
