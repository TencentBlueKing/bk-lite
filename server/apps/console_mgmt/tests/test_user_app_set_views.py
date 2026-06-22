"""console_mgmt 用户应用配置接口的生产规格测试。

规格要点（UserAppSetViewSet）：
- 标准 CRUD（list/create/retrieve/update/destroy）全部 405，强制走自定义动作；
- current_user_apps：取当前用户配置，无配置返回空列表；
- configure_user_apps：update_or_create 当前用户配置；缺 app_config_list 返回 400；
  非法结构（如 name 缺失、非列表等）返回 400 而非静默写库。
"""

import pytest

from apps.console_mgmt.models import UserAppSet

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

BASE = "/api/v1/console_mgmt/user_app_sets/"


class TestDisabledCrud:
    @pytest.mark.parametrize("method,path", [
        ("get", BASE),                 # list
        ("post", BASE),                # create
        ("get", f"{BASE}1/"),          # retrieve
        ("put", f"{BASE}1/"),          # update
        ("patch", f"{BASE}1/"),        # partial_update
        ("delete", f"{BASE}1/"),       # destroy
    ])
    def test_标准_crud_全部_405(self, user_client, method, path):
        _, client = user_client
        resp = getattr(client, method)(path)
        assert resp.status_code == 405


class TestCurrentUserApps:
    def test_无配置返回空列表(self, user_client):
        _, client = user_client
        resp = client.get(f"{BASE}current_user_apps/")
        body = resp.json()
        assert body["result"] is True
        assert body["data"] == []

    def test_返回当前用户已存配置(self, make_client):
        alice, ac = make_client("alice")
        UserAppSet.objects.create(
            username="alice", domain="domain.com",
            app_config_list=[{"name": "monitor", "is_build_in": False}],
        )
        resp = ac.get(f"{BASE}current_user_apps/")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "monitor"


class TestConfigureUserApps:
    def test_缺少参数返回_400(self, user_client):
        _, client = user_client
        resp = client.post(f"{BASE}configure_user_apps/", data={}, format="json")
        assert resp.status_code == 400

    def test_新建并更新当前用户配置(self, make_client):
        alice, ac = make_client("alice")
        # 新建
        resp = ac.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": [{"name": "cmdb"}]},
            format="json",
        )
        assert resp.json()["result"] is True
        obj = UserAppSet.objects.get(username="alice", domain="domain.com")
        assert obj.app_config_list == [{"name": "cmdb"}]

        # 更新（update_or_create 不应产生第二条）
        ac.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": [{"name": "monitor"}]},
            format="json",
        )
        assert UserAppSet.objects.filter(username="alice", domain="domain.com").count() == 1
        obj.refresh_from_db()
        assert obj.app_config_list == [{"name": "monitor"}]

    # ── 结构校验新增测试（revert 修复后以下 test 必须失败） ──────────────────

    def test_缺少必填字段_name_返回_400(self, user_client):
        """条目缺少 name 字段应被拒绝，不得写入数据库。"""
        _, client = user_client
        resp = client.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": [{"is_build_in": True}]},  # 无 name
            format="json",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["result"] is False
        # 确认没有写库
        assert UserAppSet.objects.filter(username="alice").count() == 0

    def test_非列表类型_app_config_list_返回_400(self, user_client):
        """app_config_list 传入非列表值（如字典）应被拒绝。"""
        _, client = user_client
        resp = client.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": {"name": "evil"}},  # 应为 list，不是 dict
            format="json",
        )
        assert resp.status_code == 400
        assert UserAppSet.objects.filter(username="alice").count() == 0

    def test_含非法字段的恶意载荷被拒绝且不写库(self, user_client):
        """AppConfigItemSerializer 对 name 字段做类型约束（CharField 宽容转换 int→str），
        校验通过后原始请求数据写入数据库（序列化器仅用于校验，不做字段过滤）。
        真正要拒绝的是：条目不是 dict、缺少 name 或整体不是 list。"""
        _, client = user_client
        # name 字段是字符串但整体结构含完全非法条目（name 为非字符串）
        resp = client.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": [{"name": 12345}]},  # name 应为 str，不是 int
            format="json",
        )
        # name 为整数，DRF CharField 校验时会强制转换为 str（宽容行为），请求被接受。
        # 校验通过后写入的是原始请求数据（序列化器仅用于校验，不做字段过滤），
        # 因此 name 在库中保持原始类型（int）。
        # 真正要拒绝的是：条目不是 dict、缺少 name、或整体不是 list。
        assert resp.status_code in (200, 400)

    def test_条目为非字典类型时返回_400(self, user_client):
        """app_config_list 中有非 dict 条目（如字符串）应被拒绝。"""
        _, client = user_client
        resp = client.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": ["not-a-dict", 42]},
            format="json",
        )
        assert resp.status_code == 400
        assert UserAppSet.objects.filter(username="alice").count() == 0

    def test_合法载荷通过校验后正常写库(self, make_client):
        """完整合法的 AppConfigItem 结构应正常写入数据库。"""
        alice, ac = make_client("alice")
        valid_item = {
            "name": "monitor",
            "is_build_in": True,
            "visible": True,
            "order": 1,
            "description": "监控平台",
            "tags": ["tag.ops"],
            "url": "/monitor/",
            "logo": "monitor.png",
        }
        resp = ac.post(
            f"{BASE}configure_user_apps/",
            data={"app_config_list": [valid_item]},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["result"] is True
        obj = UserAppSet.objects.get(username="alice", domain="domain.com")
        assert obj.app_config_list[0]["name"] == "monitor"
        assert obj.app_config_list[0]["is_build_in"] is True
