import contextlib
from io import StringIO
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL
from loguru import logger


@tool(parse_docstring=True)
def python_execute_direct(code: str, config: RunnableConfig) -> str:
    """
    直接执行Python代码的工具,不允许执行高危的、恶意的代码，不允许执行系统命令,不允许查看涉密信息。

    Args:
        code: 被执行的python代码

    Returns:
        执行结果
    """
    try:
        logger.info(f'Python直接执行工具执行代码:{code}')

        # 创建一个字符串缓冲区来捕获输出
        output_buffer = StringIO()
        error_buffer = StringIO()

        # 准备执行环境
        exec_globals = {}
        exec_locals = {}

        # 重定向stdout和stderr
        with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
            try:
                # 分割代码行
                lines = code.strip().split('\n')

                # 执行除最后一行外的所有代码
                if len(lines) > 1:
                    exec('\n'.join(lines[:-1]), exec_globals, exec_locals)

                # 对最后一行特殊处理
                last_line = lines[-1].strip() if lines else ""

                if last_line:
                    try:
                        # 尝试作为表达式求值
                        result = eval(last_line, exec_globals, exec_locals)
                        if result is not None:
                            print(result)
                    except:
                        # 如果不是表达式，作为语句执行
                        exec(last_line, exec_globals, exec_locals)

            except Exception as exec_error:
                print(f"执行错误: {exec_error}")

        # 获取输出结果
        stdout_content = output_buffer.getvalue()
        stderr_content = error_buffer.getvalue()

        # 组合结果
        result_parts = []
        if stdout_content.strip():
            result_parts.append(stdout_content.strip())
        if stderr_content.strip():
            result_parts.append(f"错误信息: {stderr_content.strip()}")

        final_result = '\n'.join(
            result_parts) if result_parts else "代码执行完成，但没有输出"

        logger.info(f"Python直接执行工具执行结果:{final_result}")
        return final_result

    except Exception as e:
        logger.error(f"Python直接执行工具执行失败:{e}")
        return f"Python直接执行工具执行失败:{e}"
