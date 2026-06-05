"""
安全模板渲染工具

基于 OWASP 和 Jinja2 官方安全指南：
- 方案 A：白名单变量替换（推荐，最安全）
- 方案 B：严格配置的 SandboxedEnvironment（备选）

防护能力：
1. 危险模式检测（dunder、cycler/joiner/namespace、控制语句、过滤器等）
2. 白名单变量替换（仅允许简单变量插值）
3. 阻止所有已知 SSTI bypass 技术
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from jinja2 import BaseLoader, DebugUndefined
from jinja2 import meta
from jinja2.sandbox import SandboxedEnvironment

from apps.core.logger import logger


class TemplateSecurityError(ValueError):
    """模板安全校验失败异常"""

    pass


class StrictSandboxedEnvironment(SandboxedEnvironment):
    """SandboxedEnvironment with stricter attribute and callable access rules."""

    FORBIDDEN_ATTRIBUTES = {
        "mro",
        "base",
        "bases",
        "subclasses",
        "globals",
        "func_globals",
        "builtins",
        "gi_frame",
        "f_globals",
        "f_locals",
        "cr_frame",
        "tb_frame",
    }

    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        if attr.startswith("_") or attr.lower() in self.FORBIDDEN_ATTRIBUTES:
            return False
        if callable(value):
            return False
        return super().is_safe_attribute(obj, attr, value)

    def is_safe_callable(self, obj: Any) -> bool:
        return False


# ============================================================
# 危险模式检测（基于已知 SSTI bypass 技术）
# ============================================================

GLOBAL_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\{%", "Jinja2 控制语句"),
]

EXPRESSION_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Python 内省
    (r"__\w+__", "dunder 属性访问 (如 __class__, __globals__)"),
    (r"\bmro\b", "MRO 链访问"),
    (r"\bbase\b", "base 类访问"),
    (r"\bsubclasses\b", "subclasses 枚举"),
    # Jinja2 特殊对象
    (r"\bcycler\b", "cycler 对象（可访问 __globals__）"),
    (r"\bjoiner\b", "joiner 对象（可访问 __globals__）"),
    (r"\bnamespace\b", "namespace 对象（可访问 __globals__）"),
    (r"\blipsum\b", "lipsum 对象（可访问 __globals__）"),
    # 危险函数/模块
    (r"\beval\b", "eval 函数"),
    (r"\bexec\b", "exec 函数"),
    (r"\bimport\b", "import 语句"),
    (r"\bopen\b", "open 函数"),
    (r"\bpopen\b", "popen 命令执行"),
    (r"\bsubprocess\b", "subprocess 模块"),
    (r"\bos\s*\.", "os 模块访问"),
    (r"\bsys\s*\.", "sys 模块访问"),
    (r"\bbuiltins\b", "builtins 访问"),
    (r"\bglobals\b", "globals 访问"),
    (r"\bgetattr\b", "getattr 函数"),
    (r"\bsetattr\b", "setattr 函数"),
    (r"\bdelattr\b", "delattr 函数"),
    # Jinja2 表达式语法
    (r"\|", "Jinja2 过滤器"),
    (r"\[", "下标/切片访问"),
    (r"\(", "函数调用"),
    # Flask/Web 对象
    (r"\brequest\b", "request 对象"),
    (r"\bconfig\b", "config 对象"),
    (r"\bself\b", "self 引用"),
    (r"\burl_for\b", "url_for 函数"),
    (r"\bg\b", "Flask g 对象"),
]

JINJA_EXPRESSION_PATTERN = re.compile(r"\{\{.*?\}\}", re.DOTALL)


def _find_dangerous_pattern(content: str, patterns: list[tuple[str, str]]) -> str | None:
    for pattern, description in patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return description
    return None


def check_dangerous_patterns(template_str: str) -> None:
    """
    检测模板中的危险模式

    Args:
        template_str: 模板字符串

    Raises:
        TemplateSecurityError: 发现危险模式时抛出
    """
    template_lower = template_str.lower()

    description = _find_dangerous_pattern(template_lower, GLOBAL_DANGEROUS_PATTERNS)
    if description:
        logger.warning(f"[SSTI] 检测到危险模式: {description}, template={template_str[:100]}...")
        raise TemplateSecurityError(f"模板包含禁止的模式: {description}")

    # 仅在真正的 Jinja2 表达式内部检查高危替代，避免将普通文本字符误判为 SSTI。
    for expression in JINJA_EXPRESSION_PATTERN.findall(template_lower):
        description = _find_dangerous_pattern(expression, EXPRESSION_DANGEROUS_PATTERNS)
        if description:
            logger.warning(f"[SSTI] 检测到危险模式: {description}, template={template_str[:100]}...")
            raise TemplateSecurityError(f"模板包含禁止的模式: {description}")


# ============================================================
# 方案 A：白名单变量替换（推荐）
# ============================================================

# 允许的变量模式：{{ variable }} 或 {{ variable.property.subprop }}
SAFE_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\}\}")


def safe_render(template_str: str, context: dict[str, Any]) -> str:
    """
    安全的模板变量替换，仅支持简单变量插值。

    允许: {{ last_message }}, {{ user.name }}, {{ memory_context }}
    禁止: {{ foo.__class__ }}, {{ foo|filter }}, {% if %}, {{ foo[0] }}, {{ foo() }}

    Args:
        template_str: 模板字符串
        context: 变量上下文

    Returns:
        渲染后的字符串

    Raises:
        TemplateSecurityError: 模板包含危险模式
    """
    if not template_str:
        return template_str

    # 1. 检测危险模式
    check_dangerous_patterns(template_str)

    # 2. 仅替换白名单变量
    def replace_var(match: re.Match) -> str:
        var_path = match.group(1)
        value: Any = context
        try:
            for part in var_path.split("."):
                # 禁止访问私有属性
                if part.startswith("_"):
                    return ""
                if isinstance(value, dict):
                    value = value.get(part, "")
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return ""
            return str(value) if value is not None else ""
        except Exception:
            return ""

    return SAFE_VAR_PATTERN.sub(replace_var, template_str)


SAFE_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def sanitize_template_context(value: Any, *, max_depth: int = 8) -> Any:
    """
    Convert template context to plain data so templates cannot traverse Python
    objects, Django model instances, modules, functions, or classes.
    """
    if max_depth < 0:
        return ""
    if isinstance(value, SAFE_PRIMITIVE_TYPES):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_template_context(item, max_depth=max_depth - 1)
            for key, item in value.items()
            if isinstance(key, SAFE_PRIMITIVE_TYPES)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_template_context(item, max_depth=max_depth - 1) for item in value]
    return str(value)


def validate_template_variables(template_str: str, env: SandboxedEnvironment, allowed_variables: set[str]) -> None:
    """
    Ensure a Jinja template references only explicitly allowed top-level
    business variables.
    """
    ast = env.parse(template_str)
    referenced = meta.find_undeclared_variables(ast)
    unexpected = sorted(referenced - allowed_variables)
    if unexpected:
        raise TemplateSecurityError(f"模板包含未授权变量: {', '.join(unexpected)}")


# ============================================================
# 方案 C：安全 Jinja2 沙箱环境（需要完整模板能力时使用）
# ============================================================


def build_sandboxed_env(
    loader=None,
    undefined=DebugUndefined,
    extra_filters: dict | None = None,
) -> SandboxedEnvironment:
    """
    构建安全 Jinja2 沙箱环境，供需要完整 Jinja2 模板能力的模块使用。

    防护能力：
    - 使用 SandboxedEnvironment 阻断属性链攻击（__globals__, __class__ 等）
    - 清空 globals（移除 cycler/joiner/namespace/lipsum 等可被利用的内置对象）
    - 清空默认 filters 和 tests，仅保留调用方显式声明的 filters

    Args:
        loader: Jinja2 模板加载器，默认 BaseLoader
        undefined: 未定义变量处理策略，默认 DebugUndefined
        extra_filters: 额外允许的过滤器字典

    Returns:
        配置好的 SandboxedEnvironment 实例
    """
    env = StrictSandboxedEnvironment(
        loader=loader or BaseLoader(),
        undefined=undefined,
    )
    env.globals.clear()
    env.filters.clear()
    env.tests.clear()
    if extra_filters:
        env.filters.update(extra_filters)
    return env
