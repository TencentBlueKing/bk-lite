"""统一的 Jinja2 安全渲染工具。

历史上多个业务模块直接使用 ``jinja2.Template`` 或 ``Environment.from_string``
渲染用户可控内容（监控插件采集模板、OpsPilot ChatFlow 节点配置等），导致
SSTI / 模板注入 / 远程代码执行（详见 2026-05 安全审计报告）。

本模块提供统一的安全渲染入口，业务代码不应再直接调用默认 Jinja2 渲染用户
可控内容。

核心防护：

1. 使用 :class:`ImmutableSandboxedEnvironment`：拦截一切下划线属性访问
   （``__class__`` / ``__init__`` / ``__globals__`` / ``__mro__`` /
   ``__subclasses__`` 等），从根本上切断 ``{{ cycler.__init__.__globals__... }}``
   这类反射逃逸链；同时禁止对内置可变对象的修改操作。
2. 可选清空 ``globals``：移除 ``cycler`` / ``joiner`` / ``namespace`` /
   ``lipsum`` / ``range`` 等可作为逃逸入口的全局对象（纯变量替换场景默认开启）。
3. 渲染上下文应只包含简单数据（字符串、数字、dict、list），调用方需避免
   注入 ``request`` / ``settings`` / 模块 / 工具类等复杂对象。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from jinja2 import StrictUndefined, Undefined
from jinja2.sandbox import ImmutableSandboxedEnvironment


def create_secure_jinja_environment(
    *,
    strict_undefined: bool = False,
    clear_globals: bool = True,
    clear_filters: bool = False,
) -> ImmutableSandboxedEnvironment:
    """创建经过加固的 Jinja2 沙箱环境。

    Args:
        strict_undefined: 为 True 时未定义变量会抛出异常（默认行为保持宽松，
            未定义变量渲染为空字符串，与历史 ``jinja2.Template`` 行为一致）。
        clear_globals: 为 True 时清空全局对象（``cycler`` / ``joiner`` /
            ``namespace`` / ``lipsum`` / ``range`` 等）。纯变量替换场景建议开启。
        clear_filters: 为 True 时清空内置过滤器与测试函数。若业务模板需要
            ``default`` / ``tojson`` 等过滤器，请保持 False。

    Returns:
        加固后的 :class:`ImmutableSandboxedEnvironment` 实例。
    """
    env = ImmutableSandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined if strict_undefined else Undefined,
    )
    if clear_globals:
        env.globals.clear()
    if clear_filters:
        env.filters.clear()
        env.tests.clear()
    return env


def render_secure_template(
    template_content: Optional[str],
    context: Optional[Mapping[str, Any]] = None,
    *,
    strict_undefined: bool = False,
    clear_globals: bool = True,
    clear_filters: bool = False,
) -> Optional[str]:
    """使用安全沙箱环境渲染模板字符串。

    用于替换业务代码中直接的 ``jinja2.Template(content).render(**ctx)`` 调用。
    对于 SSTI payload（如 ``{{ cycler.__init__.__globals__.os.popen('id').read() }}``）
    会抛出 :class:`jinja2.exceptions.SecurityError`，而不会执行系统命令。

    Args:
        template_content: 模板内容；为 None 时原样返回 None。
        context: 渲染上下文（仅应包含简单数据）。
        strict_undefined: 见 :func:`create_secure_jinja_environment`。
        clear_globals: 见 :func:`create_secure_jinja_environment`。
        clear_filters: 见 :func:`create_secure_jinja_environment`。

    Returns:
        渲染后的字符串。

    Raises:
        jinja2.exceptions.SecurityError: 模板尝试访问受限属性 / 危险操作。
        jinja2.exceptions.TemplateError: 模板语法错误或（strict 模式下）变量未定义。
    """
    if template_content is None:
        return None
    env = create_secure_jinja_environment(
        strict_undefined=strict_undefined,
        clear_globals=clear_globals,
        clear_filters=clear_filters,
    )
    template = env.from_string(str(template_content))
    return template.render(**dict(context or {}))


def contains_template_syntax(text: Optional[str]) -> bool:
    """判断文本中是否包含 Jinja2 模板语法标记（``{{ }}`` 或 ``{% %}``）。

    用于"只允许纯文本 / 结构化内容、不应包含模板表达式"的场景
    （如监控插件 SNMP 采集片段）做前置拒绝。
    """
    if not text:
        return False
    return ("{{" in text and "}}" in text) or ("{%" in text and "%}" in text)
