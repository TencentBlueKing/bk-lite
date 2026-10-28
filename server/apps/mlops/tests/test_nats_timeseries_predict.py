import pytest

from apps.mlops import nats_api
from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob
from apps.mlops.tests.conftest import create_train_job
from apps.system_mgmt.models.menu import Menu
from apps.system_mgmt.models.role import Role
from apps.system_mgmt.models.user import Group, User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

CONTAINER_INFO = {"port": 3000, "state": "running", "status": "success"}


def _serving(team):
    train_job = create_train_job(TimeSeriesPredictTrainJob, team)
    return TimeSeriesPredictServing.objects.create(
        name=f"serving-{team}",
        description="",
        team=[team],
        train_job=train_job,
        model_version="latest",
        status="inactive",
        container_info=CONTAINER_INFO,
    )


def _actor(group, *, with_permission=True, username="predict-user"):
    menu = Menu.objects.create(
        name="timeseries_predict-Predict",
        display_name="Predict",
        url="/mlops/predict",
        app="mlops",
    )
    role = Role.objects.create(name=f"role-{username}", app="mlops", menu_list=[menu.id] if with_permission else [])
    group_row = Group.objects.create(name=f"team-{group}-{username}", parent_id=0)
    user = User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password="x",
        domain="domain.com",
        group_list=[group_row.id],
        role_list=[role.id],
    )
    return {
        "username": user.username,
        "domain": user.domain,
        "team_id": group_row.id,
        "locale": "zh-Hans",
    }, group_row.id


def test_predict_timeseries_serving_requires_actor():
    result = nats_api.predict_timeseries_serving(1, [{"timestamp": 1, "value": 1}])
    assert result["result"] is False
    assert "调用方" in result["message"]


def test_predict_timeseries_serving_rejects_unknown_user():
    result = nats_api.predict_timeseries_serving(
        1,
        [{"timestamp": 1, "value": 1}],
        actor_context={"username": "missing", "domain": "domain.com", "team_id": 1},
    )
    assert result["result"] is False
    assert result["message"] == "调用方用户不存在"


def test_predict_timeseries_serving_rejects_missing_permission():
    actor, team_id = _actor(1, with_permission=False)
    serving = _serving(team_id)
    result = nats_api.predict_timeseries_serving(serving.id, [{"timestamp": 1, "value": 1}], actor_context=actor)
    assert result["result"] is False
    assert result["message"] == "没有时序预测权限"


def test_predict_timeseries_serving_rejects_other_organization():
    actor, _team_id = _actor(1, username="org-a")
    other = Group.objects.create(name="team-other", parent_id=0)
    serving = _serving(other.id)
    result = nats_api.predict_timeseries_serving(serving.id, [{"timestamp": 1, "value": 1}], actor_context=actor)
    assert result["result"] is False
    assert result["message"] == "预测服务不在当前组织"


def test_predict_timeseries_serving_missing_serving():
    actor, _team_id = _actor(1, username="missing-serving")
    result = nats_api.predict_timeseries_serving(999999, [{"timestamp": 1, "value": 1}], actor_context=actor)
    assert result["result"] is False
    assert result["message"] == "预测服务不存在"


def test_predict_timeseries_serving_returns_upstream_body(monkeypatch):
    actor, team_id = _actor(1, username="ok-user")
    serving = _serving(team_id)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.build_predict_url",
        lambda serving_id, container_info: "http://fake/predict",
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True, "history": [{"timestamp": 1, "value": 1}], "prediction": [{"timestamp": 2, "value": 2}]}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", lambda *args, **kwargs: FakeResponse())
    result = nats_api.predict_timeseries_serving(
        serving.id,
        [{"timestamp": 1, "value": 1}],
        steps=3,
        actor_context=actor,
    )
    assert result["result"] is True
    assert result["data"]["history"][0]["value"] == 1
    assert result["data"]["prediction"][0]["value"] == 2


def test_predict_timeseries_serving_passes_business_failure(monkeypatch):
    actor, team_id = _actor(1, username="biz-user")
    serving = _serving(team_id)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.build_predict_url",
        lambda serving_id, container_info: "http://fake/predict",
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": False, "error": {"code": "E1000", "message": "频率失败"}}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", lambda *args, **kwargs: FakeResponse())
    result = nats_api.predict_timeseries_serving(serving.id, [{"timestamp": 1, "value": 1}], actor_context=actor)
    assert result["result"] is False
    assert result["status"] == 400
    assert result["data"]["error_code"] == "E1000"


def test_predict_timeseries_serving_passes_upstream_http_error(monkeypatch):
    actor, team_id = _actor(1, username="http-user")
    serving = _serving(team_id)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.build_predict_url",
        lambda serving_id, container_info: "http://fake/predict",
    )

    class FakeResponse:
        status_code = 503
        text = "down"

        def json(self):
            return {}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", lambda *args, **kwargs: FakeResponse())
    result = nats_api.predict_timeseries_serving(serving.id, [{"timestamp": 1, "value": 1}], actor_context=actor)
    assert result["result"] is False
    assert result["status"] == 500
