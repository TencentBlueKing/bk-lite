import pytest

from apps.core.utils.virtual_organizations import authorized_virtual_organization_ids
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db


class _User:
    def __init__(self, group_list, is_superuser=False):
        self.group_list = group_list
        self.is_superuser = is_superuser


def test_named_guest_and_virtual_groups_are_included_from_group_list():
    ids = authorized_virtual_organization_ids(
        _User(
            [
                {"id": 10, "name": "Default"},
                {"id": 88, "name": "虚拟团队"},
                {"id": 99, "name": "OpsPilotGuest"},
            ]
        )
    )
    assert ids >= {88, 99}
    assert 10 not in ids


def test_authorized_is_virtual_groups_are_included_even_with_custom_names():
    parent, _ = Group.objects.get_or_create(name="虚拟团队", parent_id=0, defaults={"is_virtual": True})
    custom = Group.objects.create(name="cross-org-virtual", parent_id=parent.id, is_virtual=True)
    normal = Group.objects.create(name="normal-org", parent_id=0, is_virtual=False)

    ids = authorized_virtual_organization_ids(
        _User(
            [
                {"id": normal.id, "name": normal.name},
                {"id": custom.id, "name": custom.name},
            ]
        )
    )
    assert custom.id in ids
    assert normal.id not in ids
