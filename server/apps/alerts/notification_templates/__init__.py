"""告警通知模板领域能力。"""

from .renderer import TemplateRenderResult, TemplateValidationError, build_alert_context, render_source, validate_source

__all__ = [
    "TemplateRenderResult",
    "TemplateValidationError",
    "build_alert_context",
    "render_source",
    "validate_source",
]
