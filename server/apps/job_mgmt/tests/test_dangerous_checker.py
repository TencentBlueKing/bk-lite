"""job_mgmt.services.dangerous_checker 纯逻辑测试。

规格：脚本/路径危险规则匹配与结果聚合，是命令分发的安全闸门。
覆盖纯逻辑部分（匹配算法 + 结果聚合）和缓存层，不依赖 DB。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from apps.job_mgmt.constants import DangerousLevel, MatchType
from apps.job_mgmt.services.dangerous_checker import (
    _CMD_RULES_CACHE_KEY,
    _PATH_RULES_CACHE_KEY,
    DangerousChecker,
    DangerousCheckResult,
    _get_cmd_rules,
    _get_path_rules,
)

pytestmark = pytest.mark.unit


def _rule(level, pattern="rm -rf", name="r", rid=1):
    """返回 ORM 对象风格的 SimpleNamespace（供 add_match 兼容路径使用）。"""
    return SimpleNamespace(id=rid, name=name, pattern=pattern, level=level)


def _rule_dict(level, pattern="rm -rf", name="r", rid=1, team=None):
    """返回缓存格式的 dict（供 check_command/check_path 内部使用）。"""
    return {"id": rid, "name": name, "pattern": pattern, "level": level, "team": team or []}


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

    def test_add_match_接受dict格式规则(self):
        """add_match 必须同时支持 ORM 对象和 dict（缓存格式）。"""
        r = DangerousCheckResult()
        r.add_match(_rule_dict(DangerousLevel.FORBIDDEN, pattern="rm -rf"), "rm -rf /")
        assert r.has_forbidden is True
        assert r.forbidden[0]["pattern"] == "rm -rf"


class TestCmdRulesCache:
    """验证 _get_cmd_rules 缓存行为：命中缓存不走 DB，未命中时写缓存。"""

    def test_缓存未命中时查询DB并写入缓存(self):
        fake_rules = [_rule_dict(DangerousLevel.FORBIDDEN)]
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # 模拟缓存未命中

        mock_qs = MagicMock()
        mock_qs.filter.return_value.values.return_value = iter(fake_rules)

        with patch("apps.job_mgmt.services.dangerous_checker.cache", mock_cache), \
             patch("apps.job_mgmt.services.dangerous_checker.DangerousRule") as mock_model:
            mock_model.objects = mock_qs
            result = _get_cmd_rules()

        # 结果应为 DB 返回的规则列表
        assert result == fake_rules
        # 应写入缓存
        mock_cache.set.assert_called_once()
        set_args = mock_cache.set.call_args
        assert set_args[0][0] == _CMD_RULES_CACHE_KEY

    def test_缓存命中时不查询DB(self):
        fake_rules = [_rule_dict(DangerousLevel.CONFIRM)]
        mock_cache = MagicMock()
        mock_cache.get.return_value = fake_rules  # 模拟缓存命中

        with patch("apps.job_mgmt.services.dangerous_checker.cache", mock_cache), \
             patch("apps.job_mgmt.services.dangerous_checker.DangerousRule") as mock_model:
            result = _get_cmd_rules()

        # 缓存命中：不应查询 DB
        mock_model.objects.filter.assert_not_called()
        assert result == fake_rules

    def test_check_command_使用缓存规则不直接查DB(self):
        """check_command 必须通过 _get_cmd_rules 获取规则，不直接调用 ORM。

        若 revert 修复（改回直接 DangerousRule.objects.filter），
        此测试会因 mock_cache.get 从未被调用而失败。
        """
        fake_rules = [_rule_dict(DangerousLevel.FORBIDDEN, pattern="rm -rf")]
        mock_cache = MagicMock()
        mock_cache.get.return_value = fake_rules  # 缓存已热

        with patch("apps.job_mgmt.services.dangerous_checker.cache", mock_cache), \
             patch("apps.job_mgmt.services.dangerous_checker.DangerousRule") as mock_model:
            result = DangerousChecker.check_command("sudo rm -rf /")

        # 应命中缓存（get 被调用，key 正确）
        mock_cache.get.assert_called_with(_CMD_RULES_CACHE_KEY)
        # 不应直接查 DB
        mock_model.objects.filter.assert_not_called()
        # 应检测到禁止规则
        assert result.has_forbidden is True

    def test_check_command_团队过滤在Python层完成(self):
        """team 过滤必须在 Python 层完成（缓存 dict 列表），不再走 ORM Q 过滤。"""
        rules = [
            _rule_dict(DangerousLevel.FORBIDDEN, pattern="rm -rf", rid=1, team=[]),  # 全局规则，应命中
            _rule_dict(DangerousLevel.FORBIDDEN, pattern="mkfs", rid=2, team=[99]),  # 其他团队规则，应过滤
        ]
        mock_cache = MagicMock()
        mock_cache.get.return_value = rules

        with patch("apps.job_mgmt.services.dangerous_checker.cache", mock_cache):
            result = DangerousChecker.check_command("mkfs /dev/sda; rm -rf /", team=[1])

        # team=99 的规则不属于 team=[1]，只有全局规则（team=[]）匹配
        matched_ids = [f["rule_id"] for f in result.forbidden]
        assert 1 in matched_ids  # 全局规则命中
        assert 2 not in matched_ids  # 其他团队规则被过滤


class TestPathRulesCache:
    """验证 _get_path_rules 缓存行为。"""

    def test_缓存未命中时查询DB并写入缓存(self):
        fake_rules = [{"id": 1, "name": "p", "pattern": "/etc", "level": DangerousLevel.FORBIDDEN,
                       "match_type": MatchType.EXACT, "team": []}]
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        mock_qs = MagicMock()
        mock_qs.filter.return_value.values.return_value = iter(fake_rules)

        with patch("apps.job_mgmt.services.dangerous_checker.cache", mock_cache), \
             patch("apps.job_mgmt.services.dangerous_checker.DangerousPath") as mock_model:
            mock_model.objects = mock_qs
            result = _get_path_rules()

        assert result == fake_rules
        mock_cache.set.assert_called_once()
        assert mock_cache.set.call_args[0][0] == _PATH_RULES_CACHE_KEY

    def test_check_path_使用缓存规则不直接查DB(self):
        """check_path 必须通过 _get_path_rules 获取规则，不直接调用 ORM。"""
        fake_rules = [{"id": 1, "name": "p", "pattern": "/etc", "level": DangerousLevel.FORBIDDEN,
                       "match_type": MatchType.EXACT, "team": []}]
        mock_cache = MagicMock()
        mock_cache.get.return_value = fake_rules

        with patch("apps.job_mgmt.services.dangerous_checker.cache", mock_cache), \
             patch("apps.job_mgmt.services.dangerous_checker.DangerousPath") as mock_model:
            result = DangerousChecker.check_path("/etc/passwd")

        mock_cache.get.assert_called_with(_PATH_RULES_CACHE_KEY)
        mock_model.objects.filter.assert_not_called()
        assert result.has_forbidden is True
