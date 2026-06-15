"""issue #3058 回归测试：cmdb webhookd 渲染请求按配置做 TLS 校验，不再硬编码 verify=False。"""

from unittest.mock import MagicMock

from apps.cmdb.services.infra import InfraService


def _patch_post(monkeypatch, captured):
    def fake_post(url, **kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"yaml": "kind: DaemonSet"}
        return resp

    monkeypatch.setattr("apps.cmdb.services.infra.requests.post", fake_post)


def test_render_uses_configured_ca_path(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "/etc/ssl/webhook-ca.pem")
    captured = {}
    _patch_post(monkeypatch, captured)

    InfraService.render_config_from_api({"cluster_name": "c1"}, "https://webhookd.internal")

    assert captured["verify"] == "/etc/ssl/webhook-ca.pem"


def test_render_defaults_to_secure_verification(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_SSL_VERIFY", raising=False)
    captured = {}
    _patch_post(monkeypatch, captured)

    InfraService.render_config_from_api({"cluster_name": "c1"}, "https://webhookd.internal")

    assert captured["verify"] is True


def test_render_explicit_optout(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "false")
    captured = {}
    _patch_post(monkeypatch, captured)

    InfraService.render_config_from_api({"cluster_name": "c1"}, "https://webhookd.internal")

    assert captured["verify"] is False
