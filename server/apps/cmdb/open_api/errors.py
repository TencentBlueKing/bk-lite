class CMDBOpenAPIError(Exception):
    def __init__(self, code: str, message: str, status_code: int, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data or {}
