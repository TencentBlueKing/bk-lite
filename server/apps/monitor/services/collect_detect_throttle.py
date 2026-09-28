from rest_framework.throttling import SimpleRateThrottle

from apps.core.utils.team_utils import get_current_team


class CollectDetectOrgThrottle(SimpleRateThrottle):
    """采集探测试运行按组织限流。

    默认 2/second（约 2 QPS/组织），限制试运行打到节点上的并发探测。
    缓存键为 throttle_<scope>_<current_team>；缺少组织上下文时不限流，交由后续权限校验拒绝。
    """

    scope = "collect_detect_create"

    def get_cache_key(self, request, view):
        ident = get_current_team(request)
        if not ident:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}
