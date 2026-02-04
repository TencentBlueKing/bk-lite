"""日志预处理器，用于清洗和标准化日志消息。"""

import re
from typing import List, Optional, Dict, Any

from loguru import logger


class LogPreprocessor:
    """日志消息预处理器
    
    执行各种清洗和标准化操作：
    - 移除数字
    - 移除特殊字符
    - 转换为小写
    - 自定义正则表达式替换
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化预处理器

        Args:
            config: 预处理配置字典
        """
        self.config = config or {}
        self.remove_digits = self.config.get("remove_digits", False)
        self.remove_special_chars = self.config.get("remove_special_chars", False)
        self.lowercase = self.config.get("lowercase", False)
        self.custom_regex = self.config.get("custom_regex", [])

        # 编译自定义正则表达式模式
        self.compiled_patterns = []
        for regex_rule in self.custom_regex:
            pattern = regex_rule.get("pattern")
            replacement = regex_rule.get("replacement", "")
            if pattern:
                try:
                    compiled = re.compile(pattern)
                    self.compiled_patterns.append((compiled, replacement))
                except re.error as e:
                    logger.warning(f"Invalid regex pattern '{pattern}': {e}")

        logger.info(f"LogPreprocessor initialized with config: {self.config}")

    def preprocess(self, logs: List[str]) -> List[str]:
        """预处理日志消息列表

        Args:
            logs: 原始日志消息列表

        Returns:
            预处理后的日志消息列表
        """
        preprocessed_logs = []

        for log in logs:
            processed_log = self.preprocess_single(log)
            preprocessed_logs.append(processed_log)

        logger.info(f"Preprocessed {len(logs)} log messages")
        return preprocessed_logs

    def preprocess_single(self, log: str) -> str:
        """预处理单条日志消息

        Args:
            log: 原始日志消息

        Returns:
            预处理后的日志消息
        """
        processed = log

        # 首先应用自定义正则表达式替换
        for pattern, replacement in self.compiled_patterns:
            processed = pattern.sub(replacement, processed)

        # 移除数字
        if self.remove_digits:
            processed = re.sub(r"\d+", "<NUM>", processed)

        # 移除特殊字符
        if self.remove_special_chars:
            # 保留字母数字、空格和常用分隔符
            processed = re.sub(r"[^a-zA-Z0-9\s<>_\-\.]", " ", processed)

        # 转换为小写
        if self.lowercase:
            processed = processed.lower()

        # 标准化空白字符
        processed = " ".join(processed.split())

        return processed

    def fit(self, logs: List[str]) -> "LogPreprocessor":
        """拟合预处理器（对于无状态预处理器为空操作）

        Args:
            logs: 日志消息列表

        Returns:
            自身
        """
        logger.info("LogPreprocessor.fit() called (no-op)")
        return self

    def transform(self, logs: List[str]) -> List[str]:
        """转换日志消息（preprocess 的别名）

        Args:
            logs: 原始日志消息列表

        Returns:
            预处理后的日志消息列表
        """
        return self.preprocess(logs)

    def fit_transform(self, logs: List[str]) -> List[str]:
        """拟合并转换日志消息

        Args:
            logs: 原始日志消息列表

        Returns:
            预处理后的日志消息列表
        """
        self.fit(logs)
        return self.transform(logs)


class LogParser:
    """结构化日志消息解析器
    
    基于日志格式从日志消息中提取字段。
    """

    def __init__(self, log_format: str = "<Content>"):
        """初始化日志解析器

        Args:
            log_format: 日志格式字符串（例如："<Date> <Time> <Level> <Content>"）
        """
        self.log_format = log_format
        self.headers = self._extract_headers()

        # 从日志格式构建正则表达式模式
        self.pattern = self._build_pattern()

        logger.info(f"LogParser initialized with format: {log_format}")
        logger.info(f"Extracted headers: {self.headers}")

    def _extract_headers(self) -> List[str]:
        """从日志格式中提取标题名称

        Returns:
            标题名称列表
        """
        headers = re.findall(r"<(\w+)>", self.log_format)
        return headers

    def _build_pattern(self) -> re.Pattern:
        """从日志格式构建正则表达式模式

        Returns:
            编译后的正则表达式模式
        """
        # 将每个标题替换为捕获组
        pattern = self.log_format
        for header in self.headers:
            if header == "Content":
                # Content 捕获所有剩余内容
                pattern = pattern.replace(f"<{header}>", r"(?P<Content>.*)")
            else:
                # 其他字段捕获非空白字符
                pattern = pattern.replace(f"<{header}>", rf"(?P<{header}>\S+)")

        # 转义特殊字符
        pattern = pattern.replace("*", r"\*")

        return re.compile(pattern)

    def parse(self, log: str) -> Dict[str, str]:
        """解析单条日志消息

        Args:
            log: 原始日志消息

        Returns:
            解析后的字段字典
        """
        match = self.pattern.match(log)
        if match:
            return match.groupdict()
        else:
            # 如果解析失败，只返回 Content
            return {"Content": log}

    def parse_logs(self, logs: List[str]) -> List[Dict[str, str]]:
        """解析多条日志消息

        Args:
            logs: 原始日志消息列表

        Returns:
            解析后的日志字典列表
        """
        parsed_logs = [self.parse(log) for log in logs]
        logger.info(f"Parsed {len(logs)} log messages")
        return parsed_logs

    def extract_content(self, logs: List[str]) -> List[str]:
        """从日志中提取内容字段

        Args:
            logs: 原始日志消息列表

        Returns:
            内容字符串列表
        """
        parsed_logs = self.parse_logs(logs)
        contents = [parsed["Content"] for parsed in parsed_logs]
        return contents
