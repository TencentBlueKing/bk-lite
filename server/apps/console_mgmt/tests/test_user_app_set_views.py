"""console_mgmt 用户应用配置接口的生产规格测试。

规格要点（UserAppSetViewSet）：
- 标准 CRUD（list/create/retrieve/update/destroy）全部 405，强制走自定义动作；
- current_user_apps：取当前用户配置，无配置返回空列表；
- configure_user_apps：update_or_create 当前用户配置；缺 app_config_list 返回 400。
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
