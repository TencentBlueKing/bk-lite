class AlertExtensionRouteRegistry:
    """在 Alerts 既有 URL 空间中挂载可选版本路由。"""

    def __init__(self):
        self._entries = {}
        self.urlpatterns = []

    def clear(self):
        self._entries.clear()
        self._rebuild()

    def register(self, key, patterns):
        self._entries[key] = list(patterns)
        self._rebuild()

    def _rebuild(self):
        self.urlpatterns[:] = [
            pattern
            for patterns in self._entries.values()
            for pattern in patterns
        ]


alert_extension_routes = AlertExtensionRouteRegistry()
