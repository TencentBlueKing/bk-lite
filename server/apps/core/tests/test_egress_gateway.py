import requests

from apps.core.utils.egress_gateway import EgressGateway, MODE_DIRECT, MODE_TRUSTED_PROXY
from apps.core.utils.ssrf_validator import ValidatedTarget


def _target(url="https://evil.example/path", ip="93.184.216.34", hostname="evil.example", scheme="https", port=None):
    return ValidatedTarget(url=url, hostname=hostname, scheme=scheme, resolved_ips=(ip,), port=port)


def test_direct_pins_ip_sets_host_and_disables_env_proxy(mocker):
    session = mocker.MagicMock()
    session.request.return_value = requests.Response()
    mocker.patch("apps.core.utils.egress_gateway.requests.Session", return_value=session)

    gateway = EgressGateway(mode=MODE_DIRECT)
    gateway.send("GET", _target(), timeout=5)

    assert session.trust_env is False
    assert session.request.call_args[0] == ("GET", "https://93.184.216.34/path")
    assert session.request.call_args.kwargs["headers"]["Host"] == "evil.example"
    adapter = session.mount.call_args[0][1]
    assert adapter.server_hostname == "evil.example"


def test_trusted_proxy_without_registry_stays_direct(mocker):
    session = mocker.MagicMock()
    session.request.return_value = requests.Response()
    mocker.patch("apps.core.utils.egress_gateway.requests.Session", return_value=session)

    gateway = EgressGateway(mode=MODE_TRUSTED_PROXY, trusted_proxies=())
    gateway.send("GET", _target())

    assert session.request.call_args[0][1] == "https://93.184.216.34/path"
    assert "proxies" not in session.request.call_args.kwargs


def test_ipv6_connect_url_is_bracketed():
    target = _target(ip="2001:db8::1")
    assert target.connect_url() == "https://[2001:db8::1]/path"
    assert target.host_header() == "evil.example"


def test_non_default_port_kept_on_host_and_connect():
    target = ValidatedTarget(
        url="https://evil.example:8443/path",
        hostname="evil.example",
        scheme="https",
        resolved_ips=("93.184.216.34",),
        port=8443,
    )
    assert target.connect_url() == "https://93.184.216.34:8443/path"
    assert target.host_header() == "evil.example:8443"
