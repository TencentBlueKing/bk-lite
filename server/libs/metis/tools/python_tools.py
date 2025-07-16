from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL
import logging
logger = logging.getLogger(__name__)


@tool(parse_docstring=True)
def python_analyze_repl(code: str, config: RunnableConfig) -> str:
    """
    这个工具用于执行Python代码，用于辅助数据分析.
        要求:
            1. 生成的代码必须具备可靠性，安全性
            2. 优先使用python内置函数进行分析
            3. 进行数据分析的时候，可以使用pandas、numpy等库

    Args:
        code: 被执行的python代码

    Returns:
        分析结果
    """
    try:
        logger.info(f'Python数据分析工具执行代码:{code}')
        repl = PythonREPL()
        result = repl.run(code)
        logger.info(f"Python 数据分析工具执行结果:{result}")
        return result
    except Exception as e:
        logger.error(f"Python 数据分析工具执行失败:{e}")
        return f"Python 数据分析工具执行失败:{e}"
