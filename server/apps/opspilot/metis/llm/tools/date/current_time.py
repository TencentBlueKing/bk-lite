from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger


@tool()
def get_current_time(config: RunnableConfig) -> str:
    """
    这个工具可以用于获取当前时间
    """
    result = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # logger.info(f"用户:[{config['configurable']['user_id']}]执行工具[获取当前时间],结果:[{result}]")
    return result
