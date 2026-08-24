from apps.system_mgmt.services.ad_pull_dns import (
    AD_LOCAL_ROOT_SCOPE_ID,
    normalize_ad_pull_dns,
    resolve_ad_local_root_scope_id,
)


def test_normalize_ad_pull_dns_from_legacy_root_dn():
    assert normalize_ad_pull_dns({"root_dn": " OU=A,DC=x "}) == ["OU=A,DC=x"]


def test_normalize_ad_pull_dns_from_multiline_and_list():
    assert normalize_ad_pull_dns(
        {"root_dns": "OU=A,DC=x\n\nOU=C,DC=x\n"}
    ) == ["OU=A,DC=x", "OU=C,DC=x"]
    assert normalize_ad_pull_dns(
        {"root_dns": ["OU=A,DC=x", " ou=a,dc=x ", "OU=C,DC=x"]}
    ) == ["OU=A,DC=x", "OU=C,DC=x"]


def test_normalize_ad_pull_dns_drops_covered_descendant():
    parent = "OU=PAAS,DC=corp,DC=com"
    child = "OU=Dev,OU=PAAS,DC=corp,DC=com"
    assert normalize_ad_pull_dns({"root_dns": [parent, child]}) == [parent]


def test_normalize_ad_pull_dns_rejects_empty_and_whitespace():
    assert normalize_ad_pull_dns({"root_dns": []}) == []
    assert normalize_ad_pull_dns({"root_dns": "\n  \n"}) == []
    assert normalize_ad_pull_dns({"root_dn": ""}) == []


def test_resolve_ad_local_root_scope_id_single_vs_multi():
    assert resolve_ad_local_root_scope_id(["OU=A,DC=x"]) == "OU=A,DC=x"
    assert resolve_ad_local_root_scope_id(["OU=A,DC=x", "OU=C,DC=x"]) == AD_LOCAL_ROOT_SCOPE_ID
