"""opspilot-biz 切片: services/chatflow_init_service.ChatFlowInitService 真实测试。

聚焦无 DB 依赖的纯逻辑：workflow agent ID 改写、收件人清理、工具列表构建、
文件/JSON 读取与缺失分支、日志路由（普通模式 logger / 迁移模式 print）、init
配置缺失短路。模型对象用 mocker 模拟（真实 ORM 边界）。
"""

import json

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.services.chatflow_init_service import ChatFlowInitService


class TestUpdateWorkflowAgentIds:
    def test_按agentName匹配改写agent_id(self):
        svc = ChatFlowInitService()
        workflow = {
            "nodes": [
                {"id": "n1", "type": "agents", "data": {"config": {"agentName": "主技能"}}},
                {"id": "n2", "type": "agents", "data": {"config": {"agentName": "格式化技能"}}},
                {"id": "n3", "type": "start", "data": {"config": {"agentName": "主技能"}}},
            ]
        }
        out = svc._update_workflow_agent_ids(workflow, "主技能", 11, "格式化技能", 22)
        assert out["nodes"][0]["data"]["config"]["agent"] == 11
        assert out["nodes"][1]["data"]["config"]["agent"] == 22
        # 非 agents 类型节点不被改写
        assert "agent" not in out["nodes"][2]["data"]["config"]

    def test_无匹配名称不改写(self):
        svc = ChatFlowInitService()
        workflow = {"nodes": [{"id": "n1", "type": "agents", "data": {"config": {"agentName": "其他"}}}]}
        out = svc._update_workflow_agent_ids(workflow, "主技能", 1, "格式化", 2)
        assert "agent" not in out["nodes"][0]["data"]["config"]

    def test_无nodes键安全返回(self):
        svc = ChatFlowInitService()
        out = svc._update_workflow_agent_ids({}, "a", 1, "b", 2)
        assert out == {}


class TestClearWorkflowRecipients:
    def test_清空notification节点收件人(self):
        svc = ChatFlowInitService()
        workflow = {
            "nodes": [
                {"id": "n1", "type": "notification", "data": {"config": {"notificationRecipients": ["a", "b"]}}},
                {"id": "n2", "type": "agents", "data": {"config": {"notificationRecipients": ["x"]}}},
            ]
        }
        svc._clear_workflow_recipients(workflow)
        assert workflow["nodes"][0]["data"]["config"]["notificationRecipients"] == []
        # 非 notification 节点不动
        assert workflow["nodes"][1]["data"]["config"]["notificationRecipients"] == ["x"]

    def test_notification无收件人键跳过(self):
        svc = ChatFlowInitService()
        workflow = {"nodes": [{"id": "n1", "type": "notification", "data": {"config": {}}}]}
        svc._clear_workflow_recipients(workflow)
        assert "notificationRecipients" not in workflow["nodes"][0]["data"]["config"]


class TestBuildToolsList:
    def test_空工具名返回空(self):
        svc = ChatFlowInitService()
        assert svc._build_tools_list([]) == []

    def test_根据名称构建tools并取kwargs(self, mocker):
        svc = ChatFlowInitService()
        tool = mocker.MagicMock(id=5, icon="db", params={"kwargs": [{"key": "host"}]})
        tool.name = "postgres"
        fake_model = mocker.MagicMock()
        fake_model.objects.filter.return_value.first.return_value = tool
        mocker.patch.object(svc, "_get_model", return_value=fake_model)
        result = svc._build_tools_list(["postgres"])
        assert result == [{"id": 5, "name": "postgres", "icon": "db", "kwargs": [{"key": "host"}]}]

    def test_工具不存在记录warning并跳过(self, mocker):
        svc = ChatFlowInitService()
        fake_model = mocker.MagicMock()
        fake_model.objects.filter.return_value.first.return_value = None
        mocker.patch.object(svc, "_get_model", return_value=fake_model)
        log = mocker.patch.object(svc, "_log")
        assert svc._build_tools_list(["missing"]) == []
        log.assert_any_call("warning", "SkillTools 不存在: missing")

    def test_icon缺省回退gongjuji_params非dict走空kwargs(self, mocker):
        svc = ChatFlowInitService()
        tool = mocker.MagicMock(id=9, icon="", params="not-a-dict")
        tool.name = "k8s"
        fake_model = mocker.MagicMock()
        fake_model.objects.filter.return_value.first.return_value = tool
        mocker.patch.object(svc, "_get_model", return_value=fake_model)
        result = svc._build_tools_list(["k8s"])
        assert result[0]["icon"] == "gongjuji"
        assert result[0]["kwargs"] == []


class TestReadHelpers:
    def test_read_file_读取内容(self, tmp_path):
        svc = ChatFlowInitService()
        p = tmp_path / "check.txt"
        p.write_text("巡检提示词", encoding="utf-8")
        assert svc._read_file(p) == "巡检提示词"

    def test_read_file_不存在返回None并记录(self, tmp_path, mocker):
        svc = ChatFlowInitService()
        log = mocker.patch.object(svc, "_log")
        assert svc._read_file(tmp_path / "nope.txt") is None
        assert log.call_args[0][0] == "warning"

    def test_read_json_读取字典(self, tmp_path):
        svc = ChatFlowInitService()
        p = tmp_path / "w.json"
        p.write_text(json.dumps({"nodes": []}), encoding="utf-8")
        assert svc._read_json(p) == {"nodes": []}

    def test_read_json_不存在返回None(self, tmp_path):
        svc = ChatFlowInitService()
        assert svc._read_json(tmp_path / "nope.json") is None


class TestLoggingMode:
    def test_普通模式使用opspilot_logger(self, mocker):
        svc = ChatFlowInitService()
        fake_logger = mocker.MagicMock()
        mocker.patch("apps.core.logger.opspilot_logger", fake_logger)
        svc._log("info", "hello")
        fake_logger.info.assert_called_once_with("hello")

    def test_迁移模式无logger走print(self, capsys):
        # apps 非 None => 迁移模式 => _get_logger 返回 None => print
        svc = ChatFlowInitService(apps=object())
        svc._log("warning", "迁移日志")
        captured = capsys.readouterr()
        assert "[WARNING] 迁移日志" in captured.out


class TestGetModel:
    def test_普通模式映射真实模型并缓存(self):
        svc = ChatFlowInitService()
        m1 = svc._get_model("Bot")
        assert m1.__name__ == "Bot"
        # 第二次命中缓存返回同一对象
        assert svc._get_model("Bot") is m1

    def test_迁移模式走apps_get_model(self, mocker):
        fake_apps = mocker.MagicMock()
        sentinel = object()
        fake_apps.get_model.return_value = sentinel
        svc = ChatFlowInitService(apps=fake_apps)
        assert svc._get_model("LLMSkill") is sentinel
        fake_apps.get_model.assert_called_once_with("opspilot", "LLMSkill")


class TestInit:
    def test_配置文件不存在直接短路(self, mocker):
        svc = ChatFlowInitService()
        mocker.patch.object(type(svc.CHATFLOW_DATA_DIR / "config.json"), "exists", return_value=False)
        log = mocker.patch.object(svc, "_log")
        single = mocker.patch.object(svc, "_init_single_chatflow")
        svc.init()
        single.assert_not_called()
        assert log.call_args[0][0] == "warning"

    def test_单个chatflow异常被捕获不中断(self, mocker, tmp_path):
        svc = ChatFlowInitService()
        cfg = [{"id": "a"}, {"id": "b"}]
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg), encoding="utf-8")
        mocker.patch.object(ChatFlowInitService, "CHATFLOW_DATA_DIR", tmp_path)
        log = mocker.patch.object(svc, "_log")
        single = mocker.patch.object(svc, "_init_single_chatflow", side_effect=ValueError("x"))
        svc.init()
        # 两个配置都尝试，异常各自被捕获
        assert single.call_count == 2
        # 记录 exception 级别日志
        assert any(c[0][0] == "exception" for c in log.call_args_list)
