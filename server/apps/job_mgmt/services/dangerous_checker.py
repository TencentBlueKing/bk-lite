"""危险规则检查服务"""

import os
import re
from typing import List

from django.core.cache import cache

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import DangerousLevel, MatchType
from apps.job_mgmt.models import DangerousPath, DangerousRule

# 规则缓存 TTL（秒），进程启动时从环境变量读取，修改后需重启服务生效；默认 120s
_RULES_CACHE_TTL = int(os.getenv("DANGEROUS_RULES_CACHE_TTL", "120"))

# 缓存 key
_CMD_RULES_CACHE_KEY = "dangerous_checker:cmd_rules"
_PATH_RULES_CACHE_KEY = "dangerous_checker:path_rules"


def _get_cmd_rules() -> list:
    """获取启用的命令规则（带缓存）。

    缓存格式：list[dict]，字段 id / name / pattern / level / team。
    TTL 由 DANGEROUS_RULES_CACHE_TTL 环境变量控制，默认 120s。
    规则变更时通过 post_save/post_delete 信号主动失效（见 signals.py）。
    """
    rules = cache.get(_CMD_RULES_CACHE_KEY)
    if rules is None:
        rules = list(
            DangerousRule.objects.filter(is_enabled=True).values("id", "name", "pattern", "level", "team")
        )
        cache.set(_CMD_RULES_CACHE_KEY, rules, _RULES_CACHE_TTL)
    return rules


def _get_path_rules() -> list:
    """获取启用的路径规则（带缓存）。

    缓存格式：list[dict]，字段 id / name / pattern / level / match_type / team。
    TTL 由 DANGEROUS_RULES_CACHE_TTL 环境变量控制，默认 120s。
    规则变更时通过 post_save/post_delete 信号主动失效（见 signals.py）。
    """
    rules = cache.get(_PATH_RULES_CACHE_KEY)
    if rules is None:
        rules = list(
            DangerousPath.objects.filter(is_enabled=True).values("id", "name", "pattern", "level", "match_type", "team")
        )
        cache.set(_PATH_RULES_CACHE_KEY, rules, _RULES_CACHE_TTL)
    return rules


class DangerousCheckResult:
    """危险检查结果"""

    def __init__(self):
        self.has_warning = False
        self.has_forbidden = False
        self.warnings: List[dict] = []
        self.forbidden: List[dict] = []

    @property
    def is_safe(self) -> bool:
        """是否安全（无禁止项）"""
        return not self.has_forbidden

    @property
    def can_execute(self) -> bool:
        """是否可以执行（无禁止项）"""
        return not self.has_forbidden

    def add_match(self, rule, matched_content: str):
        """添加匹配结果。rule 可为 ORM 对象或 dict（缓存格式）。"""
        if isinstance(rule, dict):
            rule_id = rule["id"]
            rule_name = rule["name"]
            pattern = rule["pattern"]
            level = rule["level"]
        else:
            rule_id = rule.id
            rule_name = rule.name
            pattern = rule.pattern
            level = rule.level

        match_info = {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "pattern": pattern,
            "level": level,
            "matched_content": matched_content,
        }
        if level == DangerousLevel.FORBIDDEN:
            self.has_forbidden = True
            self.forbidden.append(match_info)
        else:
            self.has_warning = True
            self.warnings.append(match_info)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "is_safe": self.is_safe,
            "can_execute": self.can_execute,
            "has_warning": self.has_warning,
            "has_forbidden": self.has_forbidden,
            "warnings": self.warnings,
            "forbidden": self.forbidden,
        }


class DangerousChecker:
    """危险规则检查器"""

    @staticmethod
    def _match_pattern(pattern: str, content: str) -> list:
        """
        匹配模式（同时支持包含匹配和正则匹配）

        优先尝试包含匹配，再尝试正则匹配，任一匹配成功即返回

        Args:
            pattern: 匹配模式
            content: 待匹配内容

        Returns:
            匹配到的内容列表
        """
        matches = []

        # 1. 包含匹配（忽略大小写）
        if pattern.lower() in content.lower():
            matches.append(pattern)
            return matches

        # 2. 正则匹配
        try:
            regex = re.compile(pattern, re.MULTILINE | re.IGNORECASE)
            regex_matches = regex.findall(content)
            for match in regex_matches:
                matched_content = match if isinstance(match, str) else match[0] if match else ""
                if matched_content:
                    matches.append(matched_content)
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {pattern}, error: {e}")

        return matches

    @staticmethod
    def _match_path_pattern(pattern: str, target_path: str, match_type: str) -> list:
        """
        路径匹配

        Args:
            pattern: 规则 pattern
            target_path: 目标路径
            match_type: 匹配方式 (exact/regex)

        Returns:
            匹配到的内容列表
        """
        if match_type == MatchType.EXACT:
            # 精确匹配：路径相等 或 路径前缀 + /
            # /temp 匹配 /temp, /temp/, /temp/abc
            # /temp 不匹配 /temptest, /data/temp
            normalized_pattern = pattern.rstrip("/")
            if target_path == normalized_pattern or target_path.startswith(normalized_pattern + "/"):
                return [pattern]
            return []

        # 正则匹配
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            regex_matches = regex.findall(target_path)
            return [m if isinstance(m, str) else m[0] for m in regex_matches if m]
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {pattern}, error: {e}")
            return []

    @staticmethod
    def check_command(script_content: str, team: List[int] = None) -> DangerousCheckResult:
        """
        检查脚本内容中的危险命令

        规则集从缓存读取（TTL 由 DANGEROUS_RULES_CACHE_TTL 环境变量控制，默认 120s），
        规则变更时通过 post_save/post_delete 信号主动失效，避免每次执行都打 DB。

        Args:
            script_content: 脚本内容
            team: 团队ID列表，用于过滤规则

        Returns:
            DangerousCheckResult: 检查结果
        """
        result = DangerousCheckResult()

        rules = _get_cmd_rules()

        # 按组织过滤（空列表表示全局规则）
        if team:
            rules = [r for r in rules if not r["team"] or bool(set(r["team"]) & set(team))]

        for rule in rules:
            matches = DangerousChecker._match_pattern(rule["pattern"], script_content)
            for matched_content in matches:
                result.add_match(rule, matched_content)

        return result

    @staticmethod
    def check_path(target_path: str, team: List[int] = None) -> DangerousCheckResult:
        """
        检查目标路径是否为危险路径

        规则集从缓存读取（TTL 由 DANGEROUS_RULES_CACHE_TTL 环境变量控制，默认 120s），
        规则变更时通过 post_save/post_delete 信号主动失效，避免每次执行都打 DB。

        Args:
            target_path: 目标路径
            team: 团队ID列表，用于过滤规则

        Returns:
            DangerousCheckResult: 检查结果
        """
        result = DangerousCheckResult()

        rules = _get_path_rules()

        # 按组织过滤
        if team:
            rules = [r for r in rules if not r["team"] or bool(set(r["team"]) & set(team))]

        for rule in rules:
            matches = DangerousChecker._match_path_pattern(rule["pattern"], target_path, rule["match_type"])
            for matched_content in matches:
                result.add_match(rule, matched_content)

        return result

    @staticmethod
    def check_script(script_content: str, team: List[int] = None) -> DangerousCheckResult:
        """检查脚本（命令检查的别名）"""
        return DangerousChecker.check_command(script_content, team)

    @staticmethod
    def check_file_distribution(target_path: str, team: List[int] = None) -> DangerousCheckResult:
        """检查文件分发（路径检查的别名）"""
        return DangerousChecker.check_path(target_path, team)
