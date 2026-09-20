"""钥匙 Scope 形状与名单判定（无 DB）。"""

import pytest

from apps.core.openapi.token_scope import (
    SCOPE_ALL,
    allows_external,
    allows_internal,
    is_canonical_scope,
    migrate_stored_scope,
    normalize_scope,
)


def test_all_and_allowlist_shapes_are_canonical():
    assert is_canonical_scope({"mode": "all"})
    assert is_canonical_scope({
        "mode": "allowlist",
        "endpoints": ["GET cmdb/classifications", "EXTERNAL itsm"],
    })


@pytest.mark.parametrize(
    "scope",
    [
        None,
        {},
        {"cmdb": ["asset_info-View"]},
        {"mode": "all", "endpoints": []},
        {"mode": "allowlist", "endpoints": []},
        {"mode": "allowlist", "endpoints": ["GET /openapi/v1/cmdb/classifications"]},
        {"mode": "allowlist", "endpoints": ["GET cmdb/classifications", "GET cmdb/classifications"]},
        {"mode": "allowlist", "endpoints": ["PATCH cmdb/x"]},
        {"mode": "allowlist", "endpoints": ["GET _me/x"]},
    ],
)
def test_legacy_and_invalid_shapes_are_rejected(scope):
    assert is_canonical_scope(scope) is False
    with pytest.raises(ValueError):
        normalize_scope(scope)


def test_empty_and_permission_bit_json_migrate_to_all():
    assert migrate_stored_scope(None) == SCOPE_ALL
    assert migrate_stored_scope({}) == SCOPE_ALL
    assert migrate_stored_scope({"cmdb": ["asset_info-View"]}) == SCOPE_ALL
    assert migrate_stored_scope({"mode": "all"}) == SCOPE_ALL


def test_allowlist_internal_and_external_keys():
    scope = {
        "mode": "allowlist",
        "endpoints": ["GET cmdb/classifications", "EXTERNAL itsm"],
    }
    assert allows_internal(scope, "GET", "cmdb/classifications")
    assert allows_internal(scope, "GET", "cmdb/instances") is False
    assert allows_external(scope, "itsm")
    assert allows_external(scope, "monitor") is False
    assert allows_internal({"mode": "all"}, "POST", "job-mgmt/script-execute")
    assert allows_external(None, "itsm")
