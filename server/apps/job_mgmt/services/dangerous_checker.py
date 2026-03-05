"""危险规则检查服务"""

import logging
import re
from typing import List

from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.models import DangerousPath, DangerousRule

logger = logging.getLogger(__name__)


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
        """添加匹配结果"""
        match_info = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "pattern": rule.pattern,
            "level": rule.level,
            "matched_content": matched_content,
        }
        if rule.level == DangerousLevel.FORBIDDEN:
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
    def check_command(script_content: str, team: List[int] = None) -> DangerousCheckResult:
        """
        检查脚本内容中的危险命令

        Args:
            script_content: 脚本内容
            team: 团队ID列表，用于过滤规则

        Returns:
            DangerousCheckResult: 检查结果
        """
        result = DangerousCheckResult()

        # 获取启用的命令规则
        rules = DangerousRule.objects.filter(is_enabled=True)

        # 按组织过滤（空列表表示全局规则）
        if team:
            from django.db.models import Q

            rules = rules.filter(Q(team=[]) | Q(team__overlap=team))

        for rule in rules:
            try:
                pattern = re.compile(rule.pattern, re.MULTILINE | re.IGNORECASE)
                matches = pattern.findall(script_content)
                for match in matches:
                    matched_content = match if isinstance(match, str) else match[0] if match else ""
                    result.add_match(rule, matched_content)
            except re.error as e:
                logger.warning(f"Invalid regex pattern in rule {rule.id}: {rule.pattern}, error: {e}")

        return result

    @staticmethod
    def check_path(target_path: str, team: List[int] = None) -> DangerousCheckResult:
        """
        检查目标路径是否为危险路径

        Args:
            target_path: 目标路径
            team: 团队ID列表，用于过滤规则

        Returns:
            DangerousCheckResult: 检查结果
        """
        result = DangerousCheckResult()

        # 获取启用的路径规则
        rules = DangerousPath.objects.filter(is_enabled=True)

        # 按组织过滤
        if team:
            from django.db.models import Q

            rules = rules.filter(Q(team=[]) | Q(team__overlap=team))

        for rule in rules:
            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE)
                if pattern.search(target_path):
                    result.add_match(rule, target_path)
            except re.error as e:
                logger.warning(f"Invalid regex pattern in rule {rule.id}: {rule.pattern}, error: {e}")

        return result

    @staticmethod
    def check_script(script_content: str, team: List[int] = None) -> DangerousCheckResult:
        """检查脚本（命令检查的别名）"""
        return DangerousChecker.check_command(script_content, team)

    @staticmethod
    def check_file_distribution(target_path: str, team: List[int] = None) -> DangerousCheckResult:
        """检查文件分发（路径检查的别名）"""
        return DangerousChecker.check_path(target_path, team)
