"""issue #3058 回归测试：node_mgmt 手动安装命令的 webhookd 请求按配置做 TLS 校验。"""

from unittest.mock import MagicMock

from apps.node_mgmt.utils.installer import get_manual_install_command


def _patch_post(monkeypatch, captured):
    def fake_post(url, **kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        return resp

    monkeypatch.setattr("apps.node_mgmt.utils.installer.requests.post", fake_post)


def _call():
    return get_manual_install_command(
        os="linux",
        package_id=1,
        cloud_region_id="cr1",
        sidecar_token="tok",
        server_url="https://node.internal",
        groups=[1],
        node_name="n1",
        node_id="nid",
        webhook_url="https://webhookd.internal",
    )


def test_install_command_uses_configured_ca_path(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "/etc/ssl/webhook-ca.pem")
    captured = {}
    _patch_post(monkeypatch, captured)

    _call()

    assert captured["verify"] == "/etc/ssl/webhook-ca.pem"
    assert captured["json"]["api_token"] == "tok"  # 凭据仍正常下发


def test_install_command_defaults_to_secure_verification(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_SSL_VERIFY", raising=False)
    captured = {}
    _patch_post(monkeypatch, captured)

    _call()

    assert captured["verify"] is True


def test_install_command_explicit_optout(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_SSL_VERIFY", "false")
    captured = {}
    _patch_post(monkeypatch, captured)

    _call()

    assert captured["verify"] is False
