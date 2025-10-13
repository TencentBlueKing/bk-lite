from rest_framework import viewsets

from apps.core.utils.loader import LanguageLoader


class BaseSystemMgmtViewSet(viewsets.ModelViewSet):
    """
    system_mgmt 应用的基础 ViewSet，提供统一的语言加载功能
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loader = None

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        if hasattr(request, "user") and request.user:
            locale = getattr(request.user, "locale", "en") or "en"
            self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)
        return request


class BaseOpsPilotViewSet(viewsets.ModelViewSet):
    """
    opspilot 应用的基础 ViewSet，提供统一的语言加载功能
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loader = None

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        if hasattr(request, "user") and request.user:
            locale = getattr(request.user, "locale", "en") or "en"
            self.loader = LanguageLoader(app="opspilot", default_lang=locale)
        return request
