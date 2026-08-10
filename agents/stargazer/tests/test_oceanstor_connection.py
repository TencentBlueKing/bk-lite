import sys
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


def test_oceanstor_login_honors_port_and_certificate_verification(monkeypatch):
    from plugins.inputs.oceanstor import oceanstor_info

    calls = []

    class _Response:
        @staticmethod
        def json():
            return {
                "data": {
                    "iBaseToken": "token",
                    "deviceid": "device-1",
                }
            }

    def _post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(oceanstor_info.requests, "post", _post)
    manager = oceanstor_info.OceanStorManager(
        {
            "host": "10.0.0.88",
            "port": 8443,
            "username": "collector",
            "password": "secret",
            "verify_tls": False,
        }
    )

    manager.login()

    assert manager.base_url == "https://10.0.0.88:8443"
    assert calls[0][1]["verify"] is False
