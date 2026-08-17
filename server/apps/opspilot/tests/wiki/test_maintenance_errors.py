import pytest

from apps.opspilot.services.wiki.maintenance_errors import humanize_maintenance_error, stage_failed


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Embedding provider timeout after 30s (openai-compatible /v1/embeddings)", "连接超时"),
        ("HTTPSConnectionPool(...): Max retries exceeded with url", "无法连接服务"),
        ("Connection refused", "无法连接服务"),
        ("401 Unauthorized: invalid api key", "认证失败，请检查模型配置"),
        ("429 Too Many Requests: rate limit", "请求过于频繁"),
        ("502 Bad Gateway", "上游服务异常"),
        ("embedding index failed: unknown provider error", "索引服务调用失败"),
        ("something totally unexpected", "维护阶段执行失败"),
        ("", "维护阶段执行失败"),
    ],
)
def test_humanize_maintenance_error(raw, expected):
    assert humanize_maintenance_error(raw) == expected


def test_stage_failed_stores_human_message_not_raw_exception():
    result = stage_failed(TimeoutError("Embedding provider timeout after 30s"))
    assert result == {"status": "failed", "error": "连接超时"}
