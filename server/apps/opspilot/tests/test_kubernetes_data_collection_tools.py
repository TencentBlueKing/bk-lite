import asyncio
import base64
import json
import sys
import types
from pathlib import Path


def test_kubernetes_constructor_params_expose_structured_instances_only():
    from apps.opspilot.metis.llm.tools.kubernetes import CONSTRUCTOR_PARAMS

    assert CONSTRUCTOR_PARAMS == [
        {
            "name": "kubernetes_instances",
            "type": "array",
            "required": False,
            "description": "Kubernetes 实例列表，每个实例包含 id、name、kubeconfig_data",
        }
    ]


def test_build_generated_file_download_event_returns_generic_payload():
    from apps.opspilot.services.generated_file_delivery_service import build_generated_file_download_event

    event = build_generated_file_download_event(
        filename="report.docx",
        content_bytes=b"hello",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert event["filename"] == "report.docx"
    assert event["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(event["download_id"]) == 8
    assert base64.b64decode(event["content_base64"]) == b"hello"


def test_generate_k8s_report_docx_keeps_k8s_specific_rendering():
    from apps.opspilot.metis.llm.tools.kubernetes.report_generator import generate_k8s_report_docx

    report_bytes = generate_k8s_report_docx(
        {
            "cluster_name": "test-cluster",
            "raw_items": [
                {
                    "namespace": "default",
                    "target_name": "api",
                    "target_type": "Deployment",
                    "severity": "high",
                    "summary": "镜像标签使用 latest",
                    "category": "image",
                }
            ],
        }
    )

    assert isinstance(report_bytes, bytes)
    assert report_bytes.startswith(b"PK")


def test_get_kubernetes_instances_prompt_requires_choice_when_unspecified():
    from apps.opspilot.metis.llm.tools.kubernetes.connection import get_kubernetes_instances_prompt

    prompt = get_kubernetes_instances_prompt(
        {
            "kubernetes_instances": [
                {"id": "test", "name": "测试集群", "kubeconfig_data": "apiVersion: v1"},
                {"id": "prod", "name": "生产集群", "kubeconfig_data": "apiVersion: v1"},
            ]
        }
    )

    assert "可用实例: 测试集群, 生产集群" in prompt
    assert "未指定实例时，必须先让用户选择一个目标实例" in prompt
    assert "默认对全部实例执行" not in prompt


def test_collect_k8s_context_targets_single_instance_when_instance_id_provided(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import collect_k8s_context_by_target_type

    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection._get_target_instances",
        return_value=[{"id": "prod", "name": "生产集群", "kubeconfig_data": "apiVersion: v1"}],
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection._collect_single_instance_context",
        return_value={"resource_snapshot": {"name": "pod-a"}, "events_timeline": None},
    )

    result = json.loads(
        collect_k8s_context_by_target_type.invoke(
            {
                "target": {"resource_type": "pod", "resource_name": "pod-a", "namespace": "default"},
                "instance_id": "prod",
            }
        )
    )

    assert result["instance"] == {"id": "prod", "name": "生产集群"}
    assert result["resource_snapshot"] == {"name": "pod-a"}


def test_collect_k8s_context_targets_all_instances_when_unspecified(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import collect_k8s_context_by_target_type

    instances = [
        {"id": "test", "name": "测试集群", "kubeconfig_data": "cfg-1"},
        {"id": "prod", "name": "生产集群", "kubeconfig_data": "cfg-2"},
    ]
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection._get_target_instances",
        return_value=instances,
    )
    collect_single = mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection._collect_single_instance_context",
        side_effect=[
            {"resource_snapshot": {"cluster": "test"}},
            {"resource_snapshot": {"cluster": "prod"}},
        ],
    )

    result = json.loads(
        collect_k8s_context_by_target_type.invoke(
            {
                "target": {"resource_type": "pod", "resource_name": "pod-a", "namespace": "default"},
            }
        )
    )

    assert result["mode"] == "multi_instance"
    assert result["instance_count"] == 2
    assert result["instances"][0]["instance"] == {"id": "test", "name": "测试集群"}
    assert result["instances"][1]["instance"] == {"id": "prod", "name": "生产集群"}
    assert collect_single.call_count == 2


def test_prepare_context_selects_instance_by_instance_id(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.utils import prepare_context

    load_kube_config = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.utils.config.load_kube_config")
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.utils._preprocess_kubeconfig",
        side_effect=lambda value: value,
    )

    cfg = {
        "configurable": {
            "kubernetes_instances": [
                {"id": "test", "name": "测试集群", "kubeconfig_data": "apiVersion: v1\nkind: Config\ncurrent-context: test"},
                {"id": "prod", "name": "生产集群", "kubeconfig_data": "apiVersion: v1\nkind: Config\ncurrent-context: prod"},
            ],
            "instance_id": "prod",
        }
    }

    prepare_context(cfg)

    assert load_kube_config.called
    loaded_content = load_kube_config.call_args.kwargs["config_file"].read()
    assert "current-context: prod" in loaded_content


def test_collect_pod_context_enriches_workload_and_config_refs_from_snapshot(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import _collect_pod_context

    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.describe_kubernetes_resource",
        new=mocker.Mock(
            invoke=mocker.Mock(
                return_value=json.dumps(
                    {
                        "name": "rabbitmq-exporter-weops-0",
                        "namespace": "rabbitmq",
                        "resource_type": "pod",
                        "spec": {
                            "nodeName": "node-a",
                            "containers": [
                                {
                                    "name": "telegraf",
                                    "env": [
                                        {"name": "TARGET_HOST", "value": "nightingale-nserver.n9e"},
                                        {
                                            "name": "CONFIG_FROM_SECRET",
                                            "valueFrom": {"secretKeyRef": {"name": "telegraf-secret", "key": "token"}},
                                        },
                                    ],
                                    "envFrom": [{"configMapRef": {"name": "telegraf-config"}}],
                                    "volumeMounts": [{"name": "config-vol", "mountPath": "/etc/telegraf"}],
                                }
                            ],
                            "volumes": [
                                {"name": "config-vol", "configMap": {"name": "telegraf-config"}},
                                {"name": "secret-vol", "secret": {"secretName": "telegraf-secret"}},
                            ],
                        },
                        "metadata": {"ownerReferences": [{"kind": "StatefulSet", "name": "rabbitmq-exporter-weops", "uid": "uid-1"}]},
                    },
                    ensure_ascii=False,
                )
            )
        ),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_resource_events_timeline",
        new=mocker.Mock(invoke=mocker.Mock(return_value=json.dumps({"timeline": []}, ensure_ascii=False))),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_kubernetes_pod_logs",
        new=mocker.Mock(invoke=mocker.Mock(return_value="plain logs")),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_kubernetes_previous_pod_logs",
        new=mocker.Mock(invoke=mocker.Mock(return_value="previous logs")),
    )
    diagnose_node_tool = mocker.Mock(invoke=mocker.Mock(return_value=json.dumps({"node_name": "node-a"}, ensure_ascii=False)))
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.diagnose_node_issues",
        new=diagnose_node_tool,
    )

    result = _collect_pod_context(
        {"resource_type": "pod", "resource_name": "rabbitmq-exporter-weops-0", "namespace": "rabbitmq"},
        {},
    )

    assert result["resource_snapshot"]["owner_workload"] == {
        "kind": "StatefulSet",
        "name": "rabbitmq-exporter-weops",
        "uid": "uid-1",
    }
    assert result["resource_snapshot"]["config_references"] == {
        "config_maps": ["telegraf-config"],
        "secrets": ["telegraf-secret"],
    }
    diagnose_node_tool.invoke.assert_called_once_with({"node_name": "node-a"})


def test_collect_pod_context_traces_service_topology_from_dns_error_logs(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import _collect_pod_context

    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.describe_kubernetes_resource",
        new=mocker.Mock(
            invoke=mocker.Mock(
                return_value=json.dumps(
                    {
                        "name": "rabbitmq-exporter-weops-0",
                        "namespace": "rabbitmq",
                        "resource_type": "pod",
                        "spec": {"nodeName": "node-a", "containers": []},
                        "metadata": {},
                    },
                    ensure_ascii=False,
                )
            )
        ),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_resource_events_timeline",
        new=mocker.Mock(invoke=mocker.Mock(return_value=json.dumps({"timeline": []}, ensure_ascii=False))),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_kubernetes_pod_logs",
        new=mocker.Mock(invoke=mocker.Mock(return_value="lookup nightingale-nserver.n9e on 10.10.24.2:53: no such host")),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_kubernetes_previous_pod_logs",
        new=mocker.Mock(invoke=mocker.Mock(return_value="")),
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.diagnose_node_issues",
        new=mocker.Mock(invoke=mocker.Mock(return_value=json.dumps({"node_name": "node-a"}, ensure_ascii=False))),
    )
    trace_service_chain_tool = mocker.Mock(
        invoke=mocker.Mock(return_value=json.dumps({"service_name": "nightingale-nserver", "namespace": "n9e"}, ensure_ascii=False))
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.trace_service_chain",
        new=trace_service_chain_tool,
    )

    result = _collect_pod_context(
        {"resource_type": "pod", "resource_name": "rabbitmq-exporter-weops-0", "namespace": "rabbitmq"},
        {},
    )

    trace_service_chain_tool.invoke.assert_called_once_with({"service_name": "nightingale-nserver", "namespace": "n9e"})
    assert result["service_topology"] == {"service_name": "nightingale-nserver", "namespace": "n9e"}


def test_build_incident_evidence_package_requires_key_pod_evidence_for_restart_analysis():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import build_incident_evidence_package

    result = json.loads(
        build_incident_evidence_package.invoke(
            {
                "alert": {"message": "container restarted 1757 times"},
                "target": {"resolved": True, "resource_type": "pod", "resource_name": "pod-a", "namespace": "default"},
                "events_timeline": {"status": "success", "data": {"timeline": []}, "error": None},
                "pod_logs": {"status": "success", "data": {"current": {"content": "boom"}}, "error": None},
                "resource_snapshot": None,
                "node_context": None,
            }
        )
    )

    assert result["ready_for_analysis"] is False


def test_setup_periodic_tasks_skips_database_sync_during_pytest(mocker, settings):
    from apps.core.celery import setup_periodic_tasks

    settings.IS_USE_CELERY = True
    settings.CELERY_BEAT_SCHEDULE = {
        "demo-task": {
            "task": "apps.demo.tasks.run",
            "schedule": 60,
            "args": [],
            "kwargs": {},
        }
    }

    interval_get_or_create = mocker.patch("django_celery_beat.models.IntervalSchedule.objects.get_or_create", side_effect=AssertionError)

    setup_periodic_tasks(sender=None)

    interval_get_or_create.assert_not_called()


def test_chatflow_engine_records_execution_summary_with_final_and_failed_nodes(mocker):
    from apps.opspilot.enum import WorkFlowTaskStatus
    from apps.opspilot.utils.chat_flow_utils.engine.core.enums import NodeStatus
    from apps.opspilot.utils.chat_flow_utils.engine.core.models import NodeExecutionContext
    from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

    workflow = mocker.Mock(id=301, flow_json={"nodes": [], "edges": []})
    task_result = mocker.Mock(status=WorkFlowTaskStatus.RUNNING)

    mocker.patch.object(ChatFlowEngine, "_parse_nodes", return_value=[])
    mocker.patch.object(ChatFlowEngine, "_parse_edges", return_value=[])
    mocker.patch.object(ChatFlowEngine, "_identify_entry_nodes", return_value=[])
    mocker.patch.object(ChatFlowEngine, "_build_topology", return_value=mocker.Mock())
    mocker.patch("apps.opspilot.utils.chat_flow_utils.engine.execution_repository.WorkFlowTaskResult.objects.filter")
    mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.engine.execution_repository.WorkFlowTaskResult.objects.create",
        return_value=task_result,
    )
    node_update = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.engine.execution_repository.WorkFlowTaskNodeResult.objects.filter"
    )

    from apps.opspilot.utils.chat_flow_utils.engine import execution_repository

    execution_repository.WorkFlowTaskResult.objects.filter.return_value.order_by.return_value.first.return_value = None
    node_update.return_value.update.return_value = 1

    engine = ChatFlowEngine(workflow, execution_id="exec-summary-1")
    engine.variable_manager.set_variable("node_node_collector_index", 1)
    engine.variable_manager.set_variable("node_node_collector_name", "Kubernetes 助手")
    engine.variable_manager.set_variable("node_node_collector_type", "agents")
    engine.variable_manager.set_variable("node_node_analyzer_index", 2)
    engine.variable_manager.set_variable("node_node_analyzer_name", "Kubernetes 数据汇总")
    engine.variable_manager.set_variable("node_node_analyzer_type", "agents")
    engine.execution_contexts = {
        "node_collector": NodeExecutionContext(node_id="node_collector", status=NodeStatus.COMPLETED),
        "node_analyzer": NodeExecutionContext(
            node_id="node_analyzer",
            status=NodeStatus.FAILED,
            error_message="evidence package missing field",
        ),
    }

    engine._record_execution_result({"last_message": "alert payload"}, {"content": "failed"}, success=False, start_node_type="agents")

    assert task_result.status == WorkFlowTaskStatus.FAIL
    assert task_result.output_data["summary"]["execution_id"] == "exec-summary-1"
    assert task_result.output_data["summary"]["final_node"]["node_id"] == "node_analyzer"
    assert task_result.output_data["summary"]["final_node"]["node_name"] == "Kubernetes 数据汇总"
    assert task_result.output_data["summary"]["failed_node"]["node_id"] == "node_analyzer"
    assert task_result.output_data["summary"]["failed_node"]["error"] == "evidence package missing field"
    task_result.save.assert_called_once()


def test_sse_subsequent_nodes_use_output_params_for_next_node_input(mocker):
    from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

    collector_node = {
        "id": "node_collector",
        "type": "agents",
        "data": {
            "label": "Kubernetes Collector",
            "config": {
                "outputParams": "incident_evidence_package",
            },
        },
    }
    analyzer_node = {
        "id": "node_analyzer",
        "type": "agents",
        "data": {
            "label": "Kubernetes Analyzer",
            "config": {
                "inputParams": "incident_evidence_package",
                "outputParams": "analysis_result",
            },
        },
    }
    workflow = mocker.Mock(id=302, flow_json={"nodes": [collector_node, analyzer_node], "edges": []})

    mocker.patch.object(ChatFlowEngine, "_parse_nodes", return_value=[collector_node, analyzer_node])
    mocker.patch.object(ChatFlowEngine, "_parse_edges", return_value=[])
    mocker.patch.object(ChatFlowEngine, "_identify_entry_nodes", return_value=["node_collector"])
    mocker.patch.object(ChatFlowEngine, "_build_topology", return_value=mocker.Mock())
    mocker.patch("apps.opspilot.utils.chat_flow_utils.engine.execution_repository.WorkFlowTaskResult.objects.filter")
    mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.engine.execution_repository.WorkFlowTaskResult.objects.create",
        return_value=mocker.Mock(),
    )
    mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.engine.execution_repository.WorkFlowTaskNodeResult.objects.filter"
    )

    engine = ChatFlowEngine(workflow, execution_id="exec-sse-params-1")
    evidence_package = '{"alert_id":"alert-001","ready_for_analysis":true}'

    next_node_inputs = []

    class DummyExecutor:
        def execute(self, node_id, node, input_data):
            next_node_inputs.append({"node_id": node_id, "input_data": input_data.copy()})
            return {"analysis_result": "ok"}

    mocker.patch.object(engine, "_get_next_nodes", return_value=["node_analyzer"])
    mocker.patch.object(
        engine, "_get_node_by_id", side_effect=lambda node_id: {"node_collector": collector_node, "node_analyzer": analyzer_node}[node_id]
    )
    mocker.patch.object(engine, "_get_node_executor", return_value=DummyExecutor())
    mocker.patch.object(engine, "_record_execution_result")
    mocker.patch.object(engine, "_record_node_execution_result")
    # 中断检查依赖 DB/缓存；本单测无 DB，显式 mock 为"未中断"以测试正常传递路径
    mocker.patch.object(engine, "_check_interrupt_requested", return_value=False)

    # F013: subsequent-node execution is now an awaited coroutine (no detached
    # daemon thread). Awaiting it must run the work in-flow to completion and
    # propagate the correct output-params-derived input to the next node.

    asyncio.run(engine._execute_subsequent_nodes_async(collector_node, [{"content": evidence_package}]))

    # The subsequent node ran and completed during the await (not dropped).
    assert next_node_inputs == [
        {
            "node_id": "node_analyzer",
            "input_data": {
                "incident_evidence_package": evidence_package,
            },
        }
    ]


def test_llm_execute_uses_skill_tools_by_default():
    from apps.opspilot.utils.skill_execution_params import resolve_request_tools

    assert resolve_request_tools(None, [{"name": "kubernetes_data_collection", "kwargs": []}]) == [
        {"name": "kubernetes_data_collection", "kwargs": []}
    ]


def test_resolve_request_tools_falls_back_to_skill_tools():
    from apps.opspilot.utils.skill_execution_params import resolve_request_tools

    assert resolve_request_tools(None, [{"name": "kubernetes_data_collection", "kwargs": []}]) == [
        {"name": "kubernetes_data_collection", "kwargs": []}
    ]
    assert resolve_request_tools([], [{"name": "kubernetes_data_collection", "kwargs": []}]) == [{"name": "kubernetes_data_collection", "kwargs": []}]
    # BL-NEW-001：请求工具必须在 Skill 授权范围内，未授权的 name 会被丢弃（不再原样覆盖）。
    assert resolve_request_tools([{"name": "override", "kwargs": []}], [{"name": "default", "kwargs": []}]) == []
    # 请求携带 Skill 已授权的同名工具（含运行时参数）则保留。
    assert resolve_request_tools(
        [{"name": "kubernetes_data_collection", "kwargs": [{"key": "kubeconfig_data", "value": "x"}]}],
        [{"name": "kubernetes_data_collection", "kwargs": []}],
    ) == [{"name": "kubernetes_data_collection", "kwargs": [{"key": "kubeconfig_data", "value": "x"}]}]


def test_llm_view_execute_passes_default_collection_tools_to_stream_chat(mocker):
    from apps.opspilot.viewsets.llm_view import LLMViewSet

    skill_obj = mocker.Mock()
    skill_obj.name = "k8s-collector"
    skill_obj.skill_type = 1
    skill_obj.skill_prompt = "你是 K8s 运维助手。"
    skill_obj.tools = [{"name": "kubernetes_data_collection", "kwargs": []}]
    skill_obj.team = [7]
    skill_obj.enable_km_route = False
    skill_obj.km_llm_model = None
    skill_obj.enable_suggest = False
    skill_obj.enable_query_rewrite = False
    skill_obj.skill_params = []
    skill_obj.skill_packages = [
        {
            "name": "RCA 复盘",
            "description": "根因分析与复盘报告",
            "required_tools": ["kubernetes_data_collection"],
            "triggers": ["CrashLoopBackOff"],
            "skill_markdown": "按事件概述、关键证据、根因结论输出。",
        }
    ]

    user = mocker.Mock()
    user.username = "tester"
    user.id = 1001
    user.is_superuser = True
    user.locale = "zh-Hans"

    request = mocker.Mock()
    request.data = {
        "skill_id": "11",
        "user_message": "Pod CrashLoopBackOff on order-api",
        "llm_model": 1,
        "skill_params": [],
    }
    request.user = user
    request.COOKIES = {}
    request.META = {"REMOTE_ADDR": "127.0.0.1"}

    stream_response = mocker.Mock()
    mocker.patch("apps.opspilot.viewsets.llm_view.LLMSkill.objects.get", return_value=skill_obj)
    mocker.patch("apps.opspilot.utils.prompt_utils.merge_skill_params", return_value=[])
    stream_chat = mocker.patch("apps.opspilot.viewsets.llm_view.stream_chat", return_value=stream_response)

    response = LLMViewSet().execute(request)

    assert response is stream_response
    stream_params = stream_chat.call_args.args[0]
    assert stream_params["tools"] == [{"name": "kubernetes_data_collection", "kwargs": []}]
    assert stream_params["locale"] == "zh-Hans"
    assert stream_params["group"] == 7
    assert "RCA 复盘" in stream_params["skill_prompt"]
    assert "按事件概述" in stream_params["skill_prompt"]
    assert stream_chat.call_args.args[1] == "k8s-collector"


def test_get_chat_msg_keeps_evidence_package_json_intact_when_knowledge_sources_enabled(mocker):
    from apps.opspilot.views import get_chat_msg

    skill_obj = mocker.Mock()
    skill_obj.name = "k8s-collector"
    skill_obj.id = 12
    skill_obj.enable_rag_knowledge_source = True

    evidence_package = json.dumps(
        {
            "schema_version": "1.0",
            "alert": {"alert_id": "alert-001"},
            "ready_for_analysis": True,
        },
        ensure_ascii=False,
    )
    doc_map = {"doc-1": {"name": "Kubernetes Runbook"}}
    title_map = {"doc-1": "Kubernetes Runbook"}

    mocker.patch(
        "apps.opspilot.views.ChatService.invoke_chat",
        return_value=(
            {"message": evidence_package, "prompt_tokens": 10, "completion_tokens": 20},
            doc_map,
            title_map,
        ),
    )
    mocker.patch("apps.opspilot.views.insert_skill_log")

    return_data, content, is_error = get_chat_msg(
        current_ip="127.0.0.1",
        kwargs={"model": "gpt-4o"},
        params={"user_message": "collect k8s evidence"},
        skill_obj=skill_obj,
        user_message="collect k8s evidence",
    )

    assert not is_error
    assert content == evidence_package
    assert return_data["choices"][0]["message"]["content"] == evidence_package


def test_chat_service_formats_kubernetes_data_collection_tool_server(mocker):
    from apps.opspilot.services.chat_service import ChatService

    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"

    skill_tool = mocker.Mock()
    skill_tool.name = "kubernetes_data_collection"
    skill_tool.is_build_in = True
    skill_tool.params = {
        "name": "kubernetes_data_collection",
        "url": "langchain:kubernetes_data_collection",
        "kwargs": [],
        "enable_auth": False,
        "auth_token": "",
    }

    mocker.patch("apps.opspilot.services.history_service.history_service.process_user_message_and_images", return_value=("alert", []))
    mocker.patch("apps.opspilot.services.history_service.history_service.process_chat_history", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.resolve_skill_params", return_value="system")
    mocker.patch("apps.opspilot.services.chat_service.SkillTools.objects.filter")
    from apps.opspilot.services import chat_service as chat_service_module

    chat_service_module.SkillTools.objects.filter.return_value = [skill_tool]

    kwargs = {
        "user_message": "alert",
        "chat_history": [],
        "skill_prompt": "system",
        "skill_params": [],
        "temperature": 0.1,
        "user_id": 1,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,
        "locale": "zh-Hans",
        "tools": [{"id": 999, "name": "kubernetes_data_collection", "kwargs": []}],
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(kwargs, llm_model)

    assert chat_kwargs["tools_servers"] == [
        {
            "name": "kubernetes_data_collection",
            "url": "langchain:kubernetes_data_collection",
            "enable_auth": False,
            "auth_token": "",
        }
    ]


def test_execute_chat_flow_test_mode_enqueues_async_run(rf, mocker):
    sys.modules.setdefault("oracledb", object())
    sys.modules.setdefault("pyodbc", object())
    falkordb_module = types.ModuleType("falkordb")
    falkordb_module.Graph = type("Graph", (), {})
    falkordb_asyncio_module = types.ModuleType("falkordb.asyncio")
    falkordb_asyncio_module.FalkorDB = type("FalkorDB", (), {})
    sys.modules.setdefault("falkordb", falkordb_module)
    sys.modules.setdefault("falkordb.asyncio", falkordb_asyncio_module)

    from apps.opspilot import views

    user = mocker.Mock()
    user.team = 1
    user.username = "tester"
    user.domain = "example.com"
    user.locale = "zh-Hans"

    bot_obj = mocker.Mock(id=101)
    bot_workflow = mocker.Mock(id=202, flow_json={"nodes": []})
    engine = mocker.Mock()
    engine.execution_id = "engine-exec-id"
    engine._get_node_by_id.return_value = {"type": "agents"}
    async_task = mocker.Mock(id="celery-task-id")

    mocker.patch("apps.opspilot.views.validate_openai_token", return_value=(True, user))
    mocker.patch("apps.opspilot.views.Bot.objects.filter")
    mocker.patch("apps.opspilot.views.BotWorkFlow.objects.filter")
    mocker.patch("apps.opspilot.views.create_chat_flow_engine", return_value=engine)
    delay = mocker.patch("apps.opspilot.views.chat_flow_test_execute_task.delay", return_value=async_task)
    mocker.patch("apps.opspilot.views.WorkFlowTaskResult.objects.filter")
    mocker.patch("apps.opspilot.views.uuid.uuid4", return_value="test-execution-id")

    views.Bot.objects.filter.return_value.first.return_value = bot_obj
    views.BotWorkFlow.objects.filter.return_value.first.return_value = bot_workflow
    views.WorkFlowTaskResult.objects.filter.return_value.exists.return_value = False

    request = rf.post(
        "/fake",
        data=json.dumps({"message": "alert payload", "is_test": True}),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer token",
    )
    request.COOKIES = {"current_team": "1"}
    request.META["REMOTE_ADDR"] = "127.0.0.1"
    request.META["HTTP_USER_AGENT"] = "pytest"

    response = views.execute_chat_flow(request, 101, "agents-1")

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["result"] is True
    assert payload["data"]["status"] == "accepted"
    assert payload["data"]["execution_id"] == "test-execution-id"
    assert payload["data"]["task_id"] == "celery-task-id"
    delay.assert_called_once()
    delay_args = delay.call_args.args
    assert delay_args[0] == 202
    assert delay_args[1] == "agents-1"
    assert delay_args[2]["last_message"] == "alert payload"
    assert delay_args[2]["execution_id"] == "test-execution-id"
    assert delay_args[2]["entry_type"] == "agents"
    assert delay_args[3] == "agents"
    assert delay_args[4] == "test-execution-id"


def test_chat_flow_test_execute_task_runs_engine_with_entry_type(mocker):
    sys.modules.setdefault("oracledb", object())
    sys.modules.setdefault("pyodbc", object())
    falkordb_module = types.ModuleType("falkordb")
    falkordb_module.Graph = type("Graph", (), {})
    falkordb_asyncio_module = types.ModuleType("falkordb.asyncio")
    falkordb_asyncio_module.FalkorDB = type("FalkorDB", (), {})
    sys.modules.setdefault("falkordb", falkordb_module)
    sys.modules.setdefault("falkordb.asyncio", falkordb_asyncio_module)

    from apps.opspilot import tasks

    workflow = mocker.Mock(id=202)
    engine = mocker.Mock()

    mocker.patch("apps.opspilot.tasks.BotWorkFlow.objects.filter")
    mocker.patch("apps.opspilot.tasks.create_chat_flow_engine", return_value=engine)
    mocker.patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda func: func())

    tasks.BotWorkFlow.objects.filter.return_value.first.return_value = workflow

    tasks.chat_flow_test_execute_task.run(
        202,
        "agents-1",
        {"last_message": "alert payload", "execution_id": "exec-1"},
        "agents",
        "exec-1",
    )

    tasks.create_chat_flow_engine.assert_called_once_with(
        workflow,
        "agents-1",
        entry_type="agents",
        execution_id="exec-1",
    )
    assert engine.entry_type == "agents"
    engine.execute.assert_called_once_with({"last_message": "alert payload", "execution_id": "exec-1"})


def test_kubernetes_tools_loader_metadata_includes_node_diagnostics_and_collection_tools():
    sys.modules.setdefault("oracledb", object())
    sys.modules.setdefault("pyodbc", object())

    from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

    metadata = ToolsLoader.get_all_tools_metadata()
    kubernetes_item = next(item for item in metadata if item["name"] == "kubernetes")
    tool_names = {tool["name"] for tool in kubernetes_item["tools"]}

    assert "diagnose_node_issues" in tool_names
    assert "normalize_alert_event" in tool_names
    assert "resolve_k8s_target_from_alert" in tool_names
    assert "collect_k8s_context_by_target_type" in tool_names
    assert "build_incident_evidence_package" in tool_names
    assert "get_kubernetes_previous_pod_logs" in tool_names


def test_kubernetes_data_collection_toolkit_exposes_only_collection_focused_tools():
    sys.modules.setdefault("oracledb", object())
    sys.modules.setdefault("pyodbc", object())

    from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

    metadata = ToolsLoader.get_all_tools_metadata()
    toolkit_item = next(item for item in metadata if item["name"] == "kubernetes_data_collection")
    tool_names = {tool["name"] for tool in toolkit_item["tools"]}

    assert "normalize_alert_event" in tool_names
    assert "resolve_k8s_target_from_alert" in tool_names
    assert "collect_k8s_context_by_target_type" in tool_names
    assert "build_incident_evidence_package" in tool_names
    assert "get_kubernetes_previous_pod_logs" in tool_names
    assert "restart_pod" not in tool_names
    assert "rollback_deployment" not in tool_names
    assert "delete_kubernetes_resource" not in tool_names


def test_builtin_k8s_chatflow_uses_restricted_data_collection_toolkit():
    config_path = Path(__file__).resolve().parents[1] / "management" / "chatflow_data" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    k8s_item = next(item for item in config if item["id"] == "k8s")

    assert k8s_item["tools"] == ["kubernetes_data_collection"]


def test_builtin_k8s_chatflow_prompts_align_alert_input_and_evidence_output():
    chatflow_dir = Path(__file__).resolve().parents[1] / "management" / "chatflow_data" / "k8s"
    check_prompt = (chatflow_dir / "check.txt").read_text(encoding="utf-8")
    format_prompt = (chatflow_dir / "format.txt").read_text(encoding="utf-8")

    assert "normalize_alert_event" in check_prompt
    assert "build_incident_evidence_package" in check_prompt
    assert "incident evidence package" in check_prompt
    assert "incident evidence package" in format_prompt
    assert "根因" in format_prompt
    assert "不要重新采集" in format_prompt


def test_normalize_alert_event_builds_stable_schema():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import normalize_alert_event

    result = normalize_alert_event.invoke(
        {
            "alert_payload": {
                "source": "alert-center",
                "alert_id": "alert-001",
                "title": "Pod CrashLoopBackOff",
                "message": "Pod order-api-7d8c6 is restarting repeatedly",
                "severity": "critical",
                "status": "firing",
                "firing_time": "2026-04-28T10:00:00Z",
                "labels": {"cluster": "prod-a", "namespace": "order", "pod": "order-api-7d8c6"},
                "annotations": {"summary": "order-api pod enters CrashLoopBackOff"},
            }
        }
    )

    payload = json.loads(result)
    assert payload["source"] == "alert-center"
    assert payload["alert_id"] == "alert-001"
    assert payload["labels"]["cluster"] == "prod-a"
    assert payload["annotations"]["summary"] == "order-api pod enters CrashLoopBackOff"


def test_resolve_k8s_target_from_alert_prefers_pod_fields():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    result = resolve_k8s_target_from_alert.invoke(
        {
            "normalized_alert": {
                "labels": {
                    "cluster": "prod-a",
                    "namespace": "order",
                    "pod": "order-api-7d8c6",
                    "container": "app",
                    "deployment": "order-api",
                }
            }
        }
    )

    payload = json.loads(result)
    assert payload["resolved"] is True
    assert payload["resource_type"] == "pod"
    assert payload["resource_name"] == "order-api-7d8c6"
    assert payload["pod_name"] == "order-api-7d8c6"
    assert payload["container_name"] == "app"
    assert payload["deployment_name"] == "order-api"


def test_resolve_k8s_target_from_alert_marks_missing_data_when_unresolved():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    result = resolve_k8s_target_from_alert.invoke({"normalized_alert": {"labels": {"cluster": "prod-a"}}})

    payload = json.loads(result)
    assert payload["resolved"] is False
    assert payload["resource_type"] is None
    assert "resource identifier" in payload["reason"]
    assert "resource_type_or_name" in payload["missing_data"]


def test_build_incident_evidence_package_wraps_uniform_evidence_blocks():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import build_incident_evidence_package

    result = build_incident_evidence_package.invoke(
        {
            "alert": {"alert_id": "alert-001", "title": "Pod CrashLoopBackOff"},
            "target": {"resource_type": "pod", "resource_name": "order-api-7d8c6", "resolved": True},
            "collection_scope": {"time_window_minutes": 60, "log_lines": 200},
            "resource_snapshot": {"phase": "Running"},
            "events_timeline": {"timeline": []},
            "pod_logs": {"current": {"content": "hello"}, "previous": None},
            "missing_data": ["previous_container_logs_not_supported"],
            "errors": [],
        }
    )

    payload = json.loads(result)
    assert payload["schema_version"] == "1.0"
    assert payload["resource_snapshot"]["status"] == "success"
    assert payload["resource_snapshot"]["data"]["phase"] == "Running"
    assert payload["events_timeline"]["status"] == "success"
    assert payload["pod_logs"]["status"] == "success"
    assert payload["missing_data"] == ["previous_container_logs_not_supported"]
    assert payload["ready_for_analysis"] is True


def test_build_incident_evidence_package_marks_failed_blocks():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import build_incident_evidence_package

    result = build_incident_evidence_package.invoke(
        {
            "alert": {"alert_id": "alert-002"},
            "target": {"resource_type": None, "resource_name": None, "resolved": False},
            "resource_snapshot": {"__error__": "lookup failed"},
            "errors": [{"step": "resource_snapshot", "message": "lookup failed"}],
            "missing_data": ["resource_type_or_name"],
        }
    )

    payload = json.loads(result)
    assert payload["resource_snapshot"]["status"] == "failed"
    assert payload["resource_snapshot"]["error"] == "lookup failed"
    assert payload["ready_for_analysis"] is False


def test_collect_k8s_context_by_target_type_uses_pod_strategy(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import collect_k8s_context_by_target_type

    describe_tool = mocker.Mock()
    describe_tool.invoke.return_value = '{"name":"order-api-7d8c6"}'
    timeline_tool = mocker.Mock()
    timeline_tool.invoke.return_value = '{"timeline":[]}'
    current_logs_tool = mocker.Mock()
    current_logs_tool.invoke.return_value = "current logs"
    previous_logs_tool = mocker.Mock()
    previous_logs_tool.invoke.return_value = "previous logs"
    node_context_tool = mocker.Mock()
    node_context_tool.invoke.return_value = '{"health_status":"warning"}'

    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection.describe_kubernetes_resource", new=describe_tool)
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_resource_events_timeline", new=timeline_tool)
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_kubernetes_pod_logs", new=current_logs_tool)
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.data_collection.get_kubernetes_previous_pod_logs",
        new=previous_logs_tool,
    )
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection.diagnose_node_issues", new=node_context_tool)

    result = collect_k8s_context_by_target_type.invoke(
        {
            "target": {
                "resource_type": "pod",
                "resource_name": "order-api-7d8c6",
                "namespace": "order",
                "pod_name": "order-api-7d8c6",
                "container_name": "app",
                "node_name": "node-3",
            },
            "collection_scope": {"time_window_minutes": 60, "log_lines": 200, "include_change_context": False},
        }
    )

    payload = json.loads(result)
    assert payload["resource_snapshot"]["name"] == "order-api-7d8c6"
    assert payload["events_timeline"]["timeline"] == []
    assert payload["pod_logs"]["current"]["content"] == "current logs"
    assert payload["pod_logs"]["previous"]["content"] == "previous logs"
    assert payload["node_context"]["health_status"] == "warning"
    describe_tool.invoke.assert_called_once()
    timeline_tool.invoke.assert_called_once()
    current_logs_tool.invoke.assert_called_once()
    previous_logs_tool.invoke.assert_called_once()
    node_context_tool.invoke.assert_called_once()
