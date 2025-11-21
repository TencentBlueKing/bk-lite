import logging

import pytest
from django.contrib.auth.hashers import make_password

from apps.system_mgmt.models import User
from apps.system_mgmt.nats_api import get_all_users

logger = logging.getLogger(__name__)


def create_test_users():
    """创建测试用户数据"""
    test_users = [
        {
            "username": "test_user1",
            "display_name": "测试用户1",
            "email": "test1@example.com",
            "password": make_password("password123"),
            "locale": "zh-Hans",
        },
        {
            "username": "test_user2",
            "display_name": "测试用户2",
            "email": "test2@example.com",
            "password": make_password("password123"),
            "locale": "en-US",
        },
    ]

    # 创建测试用户并返回创建的用户列表
    created_users = []
    for user_data in test_users:
        user = User.objects.create(**user_data)
        created_users.append(user)

    return created_users


@pytest.mark.django_db
def test_get_all_users():
    # 初始化测试用户数据
    create_test_users()

    # 调用被测函数
    result = get_all_users()
    logger.info(result)

    # 验证结果
    assert result["result"] is True
    assert len(result["data"]) >= 2  # 至少包含我们创建的两个用户

    # 验证返回的用户数据包含我们创建的用户
    usernames = [user["username"] for user in result["data"]]
    assert "test_user1" in usernames
    assert "test_user2" in usernames


def parse_data(data):
    items = data["data"].get("items", [])
    processed_items = []  # 用于暂存所有处理后的原始数据与计数，便于排序

    for item in items:
        bk_biz_name = item.get("bk_biz_name", "未知业务")
        active_status = item.get("active_status_count", {})

        # 告警相关数量
        warning_count = active_status.get("warning", 0)
        fatal_count = active_status.get("fatal", 0)
        remain_count = active_status.get("remain", 0)

        # 活动告警总数量 = warning + fatal
        active_alert_count = warning_count + fatal_count
        # 决定状态
        if fatal_count > 0:
            status = "danger"
        elif warning_count > 0 or remain_count > 0:
            status = "warned"
        else:
            status = "normal"

        brief = str(active_alert_count)

        # 暂时保存所有必要信息，用于后续排序
        processed_items.append(
            {
                "bk_biz_name": bk_biz_name,
                "fatal_count": fatal_count,
                "warning_count": warning_count,
                "remain_count": remain_count,
                "status": status,
                "brief": brief,
            }
        )

    # 排序：首先按 fatal_count 降序，然后 warning_count 降序，然后 remain_count 降序
    processed_items_sorted = sorted(processed_items, key=lambda x: (-x["fatal_count"], -x["warning_count"], -x["remain_count"]))

    # 构造最终返回的列表
    return_data = []
    for pitem in processed_items_sorted:
        transformed_item = {
            "status": pitem["status"],
            "name": pitem["bk_biz_name"],
            "brief": pitem["brief"],
            "other_url": False,
        }
        return_data.append(transformed_item)

    return True, return_data
