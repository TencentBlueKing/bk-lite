from loguru import logger
from src.tools.time_tools import get_current_time


def test_current_time_tool_returns_string():
    result = get_current_time.run("", config={
        'configurable': {
            'user_id': '1'
        }
    })
    logger.info(result)
