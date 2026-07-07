class FormulaError(ValueError):
    """公式配置错误基类。"""


class FormulaSyntaxError(FormulaError):
    """公式语法错误。"""


class FormulaValidationError(FormulaError):
    """公式结构或语义校验错误。"""


class FormulaCompileError(FormulaError):
    """公式编译错误。"""
