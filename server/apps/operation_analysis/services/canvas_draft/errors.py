class DraftAccessDenied(Exception):
    pass


class DraftNotFound(Exception):
    pass


class DraftValidationFailed(Exception):
    def __init__(self, errors: list[dict]):
        from apps.operation_analysis.services.user_messages import oa_message

        super().__init__(oa_message("messages.draft_validation_failed", "草稿校验失败"))
        self.errors = errors
