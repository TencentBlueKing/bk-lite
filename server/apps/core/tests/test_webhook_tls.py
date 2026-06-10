"""webhook TLS 校验配置 helper 的单元测试（Django-free）。

覆盖 issue #3058 修复点：webhookd 渲染请求不再硬编码关闭 TLS 校验，
改为按 WEBHOOK_SERVER_SSL_VERIFY 环境变量可配置、默认安全。
"""

from pathlib import Path

import pytest

from apps.core.utils.webhook_tls import get_webhook_tls_verify


# 所有向 webhookd 下发凭据的渲染/安装请求，必须用可配置校验而非硬编码 verify=False。
# 列在此处的文件即受守护：任何一处 revert 回 verify=False，下方守卫测试必失败。
_WEBHOOK_CALL_SITES = [
    "apps/log/services/k8s_collect.py",
    "apps/monitor/services/infra.py",
    "apps/cmdb/services/infra.py",
    "apps/node_mgmt/services/cloudregion.py",
    "apps/node_mgmt/utils/installer.py",
    "apps/node_mgmt/views/sidecar.py",
]


def _server_root():
    # 本文件位于 server/apps/core/tests/ → server 根目录为 parents[3]
    return Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("rel_path", _WEBHOOK_CALL_SITES)
def test_webhook_call_sites_do_not_hardcode_verify_false(rel_path):
    source = (_server_root() / rel_path).read_text(encoding="utf-8")
    assert "verify=False" not in source, f"{rel_path} 重新引入了 verify=False（webhookd 凭据下发禁止关闭 TLS 校验）"
    assert "get_webhook_tls_verify" in source, f"{rel_path} 未使用可配置 TLS 校验 helper"


def test_default_is_secure_when_env_unset(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_SSL_VERIFY", raising=False)
    assert get_webhook_tls_verify() is True


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "  TRUE  "])
def test_truthy_values_enable_verification(monkeypatch, value):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", value)
    assert get_webhook_tls_verify() is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no"])
def test_explicit_optout_disables_verification(monkeypatch, value):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", value)
    assert get_webhook_tls_verify() is False


def test_custom_ca_path_is_returned_as_is(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "/etc/ssl/certs/webhook-ca.pem")
    assert get_webhook_tls_verify() == "/etc/ssl/certs/webhook-ca.pem"
