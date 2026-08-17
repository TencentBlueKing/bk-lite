"""将维护阶段异常转成用户可读文案。

技术细节只写日志，不直接展示给用户。
"""

from __future__ import annotations

import re

_TIMEOUT_RE = re.compile(r"timeout|timed?\s*out|time[_\s-]?out|deadline exceeded", re.I)
_CONNECTION_RE = re.compile(
    r"connection\s*(refused|reset|aborted|error)|connect(ion)?\s*(failed|error)|"
    r"name or service not known|nodename nor servname|network is unreachable|"
    r"temporary failure in name resolution|failed to establish|max retries exceeded",
    re.I,
)
_AUTH_RE = re.compile(r"unauthorized|forbidden|invalid\s*api\s*key|authentication|401|403", re.I)
_RATE_RE = re.compile(r"rate\s*limit|too many requests|429|quota\s*exceeded", re.I)
_SERVER_RE = re.compile(r"internal server error|bad gateway|service unavailable|gateway timeout|502|503|504", re.I)
_EMBED_RE = re.compile(r"embed|embedding|/v1/embeddings", re.I)


def humanize_maintenance_error(exc_or_message) -> str:
    """把异常或原始错误串映射为简短中文说明。"""
    raw = str(exc_or_message or "").strip()
    if not raw:
        return "维护阶段执行失败"

    if _TIMEOUT_RE.search(raw):
        return "连接超时"
    if _CONNECTION_RE.search(raw):
        return "无法连接服务"
    if _AUTH_RE.search(raw):
        return "认证失败，请检查模型配置"
    if _RATE_RE.search(raw):
        return "请求过于频繁"
    if _SERVER_RE.search(raw):
        return "上游服务异常"
    if _EMBED_RE.search(raw):
        return "索引服务调用失败"
    return "维护阶段执行失败"


def stage_failed(exc_or_message) -> dict:
    return {"status": "failed", "error": humanize_maintenance_error(exc_or_message)}
