class DraftAccessDenied(Exception):
    pass


class DraftNotFound(Exception):
    pass


class DraftValidationFailed(Exception):
    def __init__(self, errors: list[dict]):
        super().__init__("草稿校验失败")
        self.errors = errors
