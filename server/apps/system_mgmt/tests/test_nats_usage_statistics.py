import pytest

from apps.system_mgmt.models.channel import Channel, ChannelChoices
from apps.system_mgmt.models.user import Group, User
from apps.system_mgmt.nats.usage import get_system_usage_statistics

pytestmark = pytest.mark.django_db


def test_system_usage_statistics_counts_selected_org_only():
    current = Group.objects.create(name="usage-org")
    other = Group.objects.create(name="other-org")
    User.objects.create(
        username="u1",
        display_name="u1",
        email="u1@example.com",
        password="x",
        group_list=[current.id],
    )
    User.objects.create(
        username="u2",
        display_name="u2",
        email="u2@example.com",
        password="x",
        group_list=[other.id],
    )
    Channel.objects.create(
        name="email-1",
        channel_type=ChannelChoices.EMAIL,
        config={"host": "smtp"},
        description="",
        team=[current.id],
    )
    Channel.objects.create(
        name="email-2",
        channel_type=ChannelChoices.EMAIL,
        config={"host": "smtp"},
        description="",
        team=[other.id],
    )

    result = get_system_usage_statistics(user_info={"team": current.id, "include_children": False})

    assert result["result"] is True
    assert result["data"]["organization_count"] == 1
    assert result["data"]["user_count"] == 1
    assert result["data"]["channel_count"] == 1
    assert result["data"]["enabled_channel_count"] == 1
    assert result["data"]["enabled_channel_rate"] == 100.0


def test_system_usage_organization_count_includes_descendants_without_include_children():
    parent = Group.objects.create(name="usage-parent")
    child = Group.objects.create(name="usage-child", parent_id=parent.id)
    User.objects.create(
        username="parent-u",
        display_name="parent-u",
        email="parent@example.com",
        password="x",
        group_list=[parent.id],
    )
    User.objects.create(
        username="child-u",
        display_name="child-u",
        email="child@example.com",
        password="x",
        group_list=[child.id],
    )
    Channel.objects.create(
        name="email-parent",
        channel_type=ChannelChoices.EMAIL,
        config={"host": "smtp"},
        description="",
        team=[parent.id],
    )
    Channel.objects.create(
        name="email-child",
        channel_type=ChannelChoices.EMAIL,
        config={"host": "smtp"},
        description="",
        team=[child.id],
    )

    result = get_system_usage_statistics(user_info={"team": parent.id, "include_children": False})

    assert result["result"] is True
    assert result["data"]["organization_count"] == 2
    assert result["data"]["user_count"] == 1
    assert result["data"]["channel_count"] == 1


def test_system_usage_statistics_forged_org_outside_group_tree_is_zero():
    current = Group.objects.create(name="usage-home")
    other = Group.objects.create(name="usage-forged")
    User.objects.create(
        username="forged-u",
        display_name="forged-u",
        email="forged@example.com",
        password="x",
        group_list=[other.id],
    )
    Channel.objects.create(
        name="email-forged",
        channel_type=ChannelChoices.EMAIL,
        config={"host": "smtp"},
        description="",
        team=[other.id],
    )

    result = get_system_usage_statistics(
        user_info={
            "team": other.id,
            "include_children": False,
            "group_tree": [{"id": current.id, "subGroups": []}],
        }
    )

    assert result["result"] is True
    assert result["data"] == {
        "organization_count": 0,
        "user_count": 0,
        "channel_count": 0,
        "enabled_channel_count": 0,
        "enabled_channel_rate": 0,
    }
