from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


@tool()
def get_current_time(
    timezone: str = "Asia/Shanghai",
    config: RunnableConfig = None,
) -> str:
    """
    这个工具可以用于获取当前时间，支持指定时区（默认 Asia/Shanghai）
    """
    result = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # logger.info(f"用户:[{config['configurable']['user_id']}]执行工具[获取当前时间],结果:[{result}]")
    return result
