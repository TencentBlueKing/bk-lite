import pytest

from apps.node_mgmt.utils.winrm import default_winrm_port, winrm_profile_error


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scheme", "expected"),
    [
        ("https", 5986),
        ("http", 5985),
    ],
)
def test_default_winrm_port_follows_scheme(scheme, expected):
    assert default_winrm_port(scheme) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scheme", "port"),
    [
        ("https", 5986),
        ("https", 7443),
        ("http", 5985),
        ("http", 8877),
    ],
)
def test_winrm_profile_accepts_matching_scheme_and_port(scheme, port):
    assert winrm_profile_error(scheme, port, "ntlm") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scheme", "port"),
    [
        ("https", 5985),
        ("http", 5986),
    ],
)
def test_winrm_profile_rejects_well_known_scheme_port_mismatch(scheme, port):
    assert winrm_profile_error(scheme, port, "ntlm")


@pytest.mark.unit
def test_winrm_profile_still_requires_ntlm():
    assert winrm_profile_error("https", 5986, "basic")
    assert winrm_profile_error("http", 5985, "kerberos")
