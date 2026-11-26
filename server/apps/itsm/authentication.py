from rest_framework.authentication import BaseAuthentication


class MiddlewareUserAuthentication(BaseAuthentication):
    """沿用 AuthMiddleware 已经校验过的用户，不再走 Session 认证。"""

    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user, None
        return None
