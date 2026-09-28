import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.utils.package_permission import require_package_write_permission


class _User:
    def __init__(self, locale):
        self.locale = locale
        self.roles = ()
        self.is_superuser = False
        self.permission = set()


class _Request:
    def __init__(self, locale):
        self.user = _User(locale)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("zh-Hans", "不支持的包类型"),
        ("zh-CN", "不支持的包类型"),
        ("en", "Unsupported package type"),
        (None, "不支持的包类型"),
    ],
)
def test_unsupported_package_type_follows_request_locale(locale, expected):
    with pytest.raises(ValidationError) as caught:
        require_package_write_permission(_Request(locale), "plugin", "create")

    assert str(caught.value.detail["type"][0]) == expected


def test_known_package_type_still_checks_permission():
    with pytest.raises(PermissionDenied):
        require_package_write_permission(_Request("en"), PackageConstants.TYPE_COLLECTOR, "create")
