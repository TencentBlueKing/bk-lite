from typing import Any


class RpcError(Exception):
    """RPC 层结构化异常契约，不携带面向客户的自然语言。"""

    code = "rpc.error"

    def _init_rpc_error(self, *, params: dict[str, Any] | None = None) -> None:
        self.params = params or {}


class RpcValidationError(ValueError, RpcError):
    """RPC 参数校验失败，保留 ``ValueError`` 兼容性。"""

    code = "rpc.validation_error"

    def __init__(self, *, params: dict[str, Any] | None = None) -> None:
        self._init_rpc_error(params=params)
        super().__init__(self.code)


class RpcTargetSourceError(RpcValidationError):
    code = "rpc.invalid_target_source"


class RpcPlaybookSourceError(RpcValidationError):
    code = "rpc.invalid_playbook_source"


class RpcTimeoutError(TimeoutError, RpcError):
    """RPC 请求超时；客户文案与内部调用上下文分离。"""

    code = "rpc.request_timeout"

    def __init__(self, namespace: str, method_name: str, timeout) -> None:
        self._init_rpc_error()
        self.namespace = namespace
        self.method_name = method_name
        self.timeout = timeout
        super().__init__(self.code)


class RpcMethodNotFoundError(ValueError, RpcError):
    """本地 RPC 映射缺失；模块路径只供日志诊断。"""

    code = "rpc.method_not_found"

    def __init__(self, path: str, method_name: str) -> None:
        self._init_rpc_error()
        self.path = path
        self.method_name = method_name
        super().__init__(self.code)


class RpcLocalClientRequiredError(RuntimeError, RpcError):
    """某项 RPC 能力仅允许通过同进程客户端调用。"""

    code = "rpc.local_client_required"

    def __init__(self, operation: str) -> None:
        self._init_rpc_error()
        self.operation = operation
        super().__init__(self.code)
