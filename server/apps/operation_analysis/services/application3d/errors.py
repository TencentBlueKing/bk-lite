from __future__ import annotations


class Application3DError(Exception):
    code: str = "source_failure"

    def __init__(self, message: str = "", *, code: str | None = None, **extra):
        super().__init__(message or self.code)
        if code:
            self.code = code
        self.message = message or self.code
        self.extra = extra


class Application3DInvalidRequest(Application3DError):
    code = "invalid_request"


class Application3DPermissionDenied(Application3DError):
    code = "permission_denied"


class Application3DNotFound(Application3DError):
    code = "not_found"


class Application3DScopeChanged(Application3DError):
    code = "scope_changed"


class Application3DSourceFailure(Application3DError):
    code = "source_failure"


class Application3DCapacityExceeded(Application3DError):
    code = "capacity_exceeded"

    def __init__(self, *, actual_count: int, supported_count: int):
        super().__init__(
            "capacity_exceeded",
            code="capacity_exceeded",
            actualCount=actual_count,
            supportedCount=supported_count,
        )
        self.actual_count = actual_count
        self.supported_count = supported_count
