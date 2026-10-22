"""补丁管理可本地化的结构化业务异常。"""

from typing import Any


class CodedMessageError(ValueError):
    """携带稳定错误码，文案在边界按请求语言渲染。"""

    def __init__(self, code: str, default: str, **params: Any) -> None:
        self.code = code
        self.default = default
        self.params = params
        try:
            message = default.format(**params) if params else default
        except (KeyError, ValueError):
            message = default
        super().__init__(message)


class PatchBusinessError(ValueError):
    """服务层只携带稳定错误码和参数，不依赖 request 或语言加载器。"""

    def __init__(
        self,
        code: str,
        default_message: str,
        *,
        params: dict[str, Any] | None = None,
        raw_detail: str = "",
        field: str | None = None,
    ) -> None:
        self.code = code
        self.default_message = default_message
        self.params = params or {}
        self.raw_detail = raw_detail
        self.field = field
        super().__init__(default_message)
