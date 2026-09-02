"""Jenkins build 工具：参数校验、触发成功/失败、批量查询隔离。"""
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.jenkins import build as build_mod

pytestmark = pytest.mark.unit


def _client(**methods):
    client = MagicMock()
    for name, value in methods.items():
        setattr(client, name, value)
    return client


def test_get_client_builds_jenkins_from_runnable_config():
    cfg = {
        "items": [
            {
                "config": {
                    "jenkins_url": "https://ci.example.com",
                    "jenkins_username": "u",
                    "jenkins_password": "p",
                }
            }
        ]
    }
    with (
        patch(
            "apps.opspilot.metis.llm.tools.jenkins.connection.build_jenkins_normalized_from_runnable",
            return_value=cfg,
        ),
        patch("apps.opspilot.metis.llm.tools.jenkins.build.jenkins.Jenkins") as jenkins_cls,
    ):
        jenkins_cls.return_value = "client"
        assert build_mod.get_client({"configurable": {}}, instance_name="ci") == "client"
    jenkins_cls.assert_called_once_with("https://ci.example.com", username="u", password="p")


def test_list_jobs_and_trigger_validates_then_returns_build_info():
    client = _client(
        get_jobs=lambda: [{"name": "job-a"}],
        get_job_info=lambda name: {"nextBuildNumber": 9, "url": "https://ci.example.com/job/job-a/"},
        build_job=lambda name, parameters=None: 77,
    )
    with patch.object(build_mod, "get_client", return_value=client):
        assert build_mod.list_jenkins_jobs.func(config={}) == [{"name": "job-a"}]
        with pytest.raises(ValueError, match="job_name must be a string"):
            build_mod.trigger_jenkins_build.func(job_name=1, parameters=None, config={})
        with pytest.raises(ValueError, match="parameters must be a dictionary or None"):
            build_mod.trigger_jenkins_build.func(job_name="job-a", parameters=["x"], config={})
        out = build_mod.trigger_jenkins_build.func(job_name="job-a", parameters={"k": "v"}, config={})
    assert out == {
        "status": "triggered",
        "job_name": "job-a",
        "queue_id": 77,
        "build_number": 9,
        "job_url": "https://ci.example.com/job/job-a/",
        "build_url": "https://ci.example.com/job/job-a/9/",
    }


def test_trigger_wraps_missing_job_and_build_errors():
    missing = _client(get_job_info=lambda name: None)
    with patch.object(build_mod, "get_client", return_value=missing):
        with pytest.raises(ValueError, match="Error checking job missing: Job missing not found"):
            build_mod.trigger_jenkins_build.func(job_name="missing", parameters=None, config={})

    exploding = _client(get_job_info=lambda name: (_ for _ in ()).throw(RuntimeError("404")))
    with patch.object(build_mod, "get_client", return_value=exploding):
        with pytest.raises(ValueError, match="Error checking job x: 404"):
            build_mod.trigger_jenkins_build.func(job_name="x", parameters=None, config={})

    fail_build = _client(
        get_job_info=lambda name: {"nextBuildNumber": 1, "url": "https://ci/job/x/"},
        build_job=lambda name, parameters=None: (_ for _ in ()).throw(RuntimeError("queue full")),
    )
    with patch.object(build_mod, "get_client", return_value=fail_build):
        with pytest.raises(ValueError, match="Error triggering build for x: queue full"):
            build_mod.trigger_jenkins_build.func(job_name="x", parameters=None, config={})


def test_job_info_batch_continues_after_single_failure():
    def get_job_info(name):
        if name == "bad":
            raise RuntimeError("gone")
        return {"name": name}

    client = _client(get_job_info=get_job_info)
    with patch.object(build_mod, "get_client", return_value=client):
        out = build_mod.get_jenkins_job_info_batch.func(job_names=["ok", "bad"], config={})
    assert out["total"] == 2
    assert out["succeeded"] == 1
    assert out["failed"] == 1
    assert out["results"][0] == {"input": "ok", "ok": True, "data": {"name": "ok"}}
    assert out["results"][1]["ok"] is False
    assert out["results"][1]["error"] == "gone"
