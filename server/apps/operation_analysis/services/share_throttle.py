from rest_framework.throttling import SimpleRateThrottle


class DashboardSharePrepareThrottle(SimpleRateThrottle):
    """未登录 prepare：按来源 IP 限流，降低 token 探测。"""

    scope = "dashboard_share_prepare"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class DashboardShareInvalidTokenThrottle(SimpleRateThrottle):
    """兑换失败：按来源 IP 限流。"""

    scope = "dashboard_share_invalid_token"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class DashboardShareExchangeUserThrottle(SimpleRateThrottle):
    scope = "dashboard_share_exchange"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class DashboardShareAccessUserThrottle(SimpleRateThrottle):
    scope = "dashboard_share_access"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
