"""job_mgmt.services.dangerous_checker 纯逻辑测试。

规格：脚本/路径危险规则匹配与结果聚合，是命令分发的安全闸门。
覆盖纯逻辑部分（匹配算法 + 结果聚合），不依赖 DB。
"""

from types import SimpleNamespace

import pytest

from apps.job_mgmt.constants import DangerousLevel, MatchType
from apps.job_mgmt.services.dangerous_checker import (
    DangerousChecker,
    DangerousCheckResult,
)

pytestmark = pytest.mark.unit


def _rule(level, pattern="rm -rf", name="r", rid=1):
    return SimpleNamespace(id=rid, name=name, pattern=pattern, level=level)


class TestMatchPattern:
    def test_包含匹配忽略大小写(self):
        assert DangerousChecker._match_pattern("RM -RF", "sudo rm -rf /") == ["RM -RF"]

    def test_正则匹配(self):
        # 不是子串，走正则分支
        matches = DangerousChecker._match_pattern(r"rm\s+-[rf]+", "do rm   -rf now")
        assert matches == ["rm   -rf"]

    def test_无匹配返回空(self):
        assert DangerousChecker._match_pattern("shutdown", "echo hello") == []

    def test_非法正则不抛异常返回空(self):
        # 既不是子串也不是合法正则
        assert DangerousChecker._match_pattern("[unclosed", "echo hi") == []


class TestMatchPathPattern:
    def test_精确匹配_自身与子路径(self):
        m = DangerousChecker._match_path_pattern
        assert m("/temp", "/temp", MatchType.EXACT) == ["/temp"]
        assert m("/temp", "/temp/abc", MatchType.EXACT) == ["/temp"]
        assert m("/temp/", "/temp/abc", MatchType.EXACT) == ["/temp/"]

    def test_精确匹配_不误伤相似前缀(self):
        m = DangerousChecker._match_path_pattern
        assert m("/temp", "/temptest", MatchType.EXACT) == []
        assert m("/temp", "/data/temp", MatchType.EXACT) == []

    def test_正则路径匹配(self):
        assert DangerousChecker._match_path_pattern(r"/etc/.*", "/etc/passwd", MatchType.REGEX) == ["/etc/passwd"]


class TestDangerousCheckResult:
    def test_禁止项使其不安全不可执行(self):
        r = DangerousCheckResult()
        r.add_match(_rule(DangerousLevel.FORBIDDEN), "rm -rf /")
        assert r.has_forbidden is True
        assert r.is_safe is False
        assert r.can_execute is False
        assert len(r.forbidden) == 1 and not r.warnings

    def test_确认项仅告警仍可执行(self):
        r = DangerousCheckResult()
        r.add_match(_rule(DangerousLevel.CONFIRM), "chmod 777")
        assert r.has_warning is True
        assert r.has_forbidden is False
        assert r.can_execute is True
        assert len(r.warnings) == 1 and not r.forbidden

    def test_to_dict_结构(self):
        r = DangerousCheckResult()
        r.add_match(_rule(DangerousLevel.FORBIDDEN), "x")
        d = r.to_dict()
        assert d["is_safe"] is False
        assert set(d) == {"is_safe", "can_execute", "has_warning", "has_forbidden", "warnings", "forbidden"}
