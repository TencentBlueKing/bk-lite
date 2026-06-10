"""issue #3058 回归测试：log K8s 渲染请求按配置做 TLS 校验，不再硬编码 verify=False。

revert 准则：若把 verify=get_webhook_tls_verify() 改回 verify=False，下列断言必失败。
"""

from unittest.mock import MagicMock

from apps.log.services.k8s_collect import K8sLogCollectService


_ENV_VARS = {
    "WEBHOOK_SERVER_URL": "https://webhookd.internal",
    "NODE_SERVER_URL": "https://node.internal",
    "NATS_SERVERS": "nats://nats.internal:4222",
    "NATS_USERNAME": "u",
    "NATS_PASSWORD": "p",
    "NATS_TLS_CA": "ca-content",
}


def _patch_post(monkeypatch, captured):
    def fake_post(url, **kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"yaml": "kind: DaemonSet"}
        return resp

    monkeypatch.setattr("apps.log.services.k8s_collect.requests.post", fake_post)


def test_render_uses_configured_ca_path(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "/etc/ssl/webhook-ca.pem")
    monkeypatch.setattr(
        K8sLogCollectService, "get_cloud_region_envconfig", staticmethod(lambda cloud_region_id: dict(_ENV_VARS))
    )
    captured = {}
    _patch_post(monkeypatch, captured)

    result = K8sLogCollectService.render_config_from_cloud_region("c1", "cr1")

    assert result == "kind: DaemonSet"
    assert captured["verify"] == "/etc/ssl/webhook-ca.pem"


def test_render_defaults_to_secure_verification(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_SSL_VERIFY", raising=False)
    monkeypatch.setattr(
        K8sLogCollectService, "get_cloud_region_envconfig", staticmethod(lambda cloud_region_id: dict(_ENV_VARS))
    )
    captured = {}
    _patch_post(monkeypatch, captured)

    K8sLogCollectService.render_config_from_cloud_region("c1", "cr1")

    assert captured["verify"] is True


def test_render_explicit_optout(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "false")
    monkeypatch.setattr(
        K8sLogCollectService, "get_cloud_region_envconfig", staticmethod(lambda cloud_region_id: dict(_ENV_VARS))
    )
    captured = {}
    _patch_post(monkeypatch, captured)

    K8sLogCollectService.render_config_from_cloud_region("c1", "cr1")

    assert captured["verify"] is False
