"""skill_channel 对话 page_context：当轮注入、不落历史、超限防御。"""

import json
import logging
from unittest.mock import patch

import pytest
from django.http import StreamingHttpResponse
from rest_framework.test import APIRequestFactory

from apps.base.models import User
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMModel, LLMSkill, ModelVendor, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services import skill_channel_chat_service as chat_svc

pytestmark = pytest.mark.django_db


def _superuser(username="page_ctx_su"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _skill():
    return LLMSkill.objects.create(name="page-ctx-skill", team=[1], usage_team=[1])


def _channel(skill):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.PLATFORM,
        enabled=True,
        usage_team=[1],
        name="platform",
    )


def _tiny_png_data_url():
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _stream_request(user, message="hi"):
    factory = APIRequestFactory()
    request = factory.post("/", {"message": message}, format="json")
    request.user = user
    return request


def _patched_stream():
    def gen():
        yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    return patch(
        "apps.opspilot.services.skill_channel_chat_service.stream_agui_chat",
        return_value=StreamingHttpResponse(gen(), content_type="text/event-stream"),
    )


class TestInjectPageContext:
    def test_wraps_text_and_images(self):
        result = chat_svc.inject_page_context(
            "现在几点了",
            {
                "url": "/monitor/view/dashboard/host",
                "title": "host",
                "sections": [{"id": "meta", "label": "对象", "content": "主机 A", "priority": 10}],
                "images": [{"caption": "CPU", "dataUrl": _tiny_png_data_url()}],
            },
        )
        assert isinstance(result, list)
        assert result[0]["type"] == "image_url"
        assert result[0]["image_url"].startswith("data:image/png")
        text = result[-1]["message"]
        assert "现在几点了" in text
        assert "<current_page>" in text
        assert "主机 A" in text
        assert "仅当问题与页面相关时参考" in text
        assert "CPU" in text

    def test_empty_context_keeps_original(self):
        assert chat_svc.inject_page_context("hi", None) == "hi"
        assert chat_svc.inject_page_context("hi", {}) == "hi"

    def test_unknown_mode_skips(self):
        assert chat_svc.inject_page_context("hi", {"title": "x"}, mode="tool") == "hi"

    def test_drops_low_priority_when_over_budget(self):
        snapshot = {
            "sections": [
                {"id": "low", "label": "低", "content": "L" * 5000, "priority": 1},
                {"id": "high", "label": "高", "content": "H" * 5000, "priority": 9},
            ]
        }
        result = chat_svc.inject_page_context("q", snapshot)
        assert "H" * 20 in result
        assert "## 低" not in result
        assert len(result) <= 8000 + 400

    def test_named_question_keeps_only_matching_chart(self):
        page_context = {
            "sections": [
                {
                    "id": "visible-charts",
                    "label": "可见图表",
                    "content": "1. 系统负载趋势；最新值: 1.98, 1.8, 1.58\n2. 磁盘使用率 Top；最新值: 80.9",
                    "priority": 9,
                }
            ],
            "images": [
                {"caption": "系统负载趋势；最新值: 1.98, 1.8, 1.58", "dataUrl": _tiny_png_data_url()},
                {"caption": "磁盘使用率 Top；最新值: 80.9", "dataUrl": _tiny_png_data_url() + "A"},
            ],
        }
        result = chat_svc.inject_page_context("分析下磁盘使用率情况", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 1
        text = result[-1]["message"]
        assert "磁盘使用率 Top" in text
        assert "系统负载趋势" not in text
        assert "《磁盘使用率 Top》" in text
        assert "禁止回答、复述或续写历史对话里已经分析过的其它图表" in text
        assert "不要沿用上一问的结论、表格、图表名或时间范围" in text

    def test_disk_usage_question_keeps_resource_trend_not_throughput(self):
        page_context = {
            "sections": [
                {
                    "id": "dashboard-time-range",
                    "label": "时间筛选",
                    "content": "当前筛选: 最近15分钟\nKPI 快照:\n磁盘使用率: 82.9%\nCPU 使用率: 86.0%",
                    "priority": 9,
                },
                {
                    "id": "visible-charts",
                    "label": "可见图表",
                    "content": (
                        "1. 资源使用趋势；序列: CPU 使用率, 内存使用率, 磁盘使用率, I/O Wait 占比；最新值: 86.0, 79.0, 82.9, 6.9\n" "2. 磁盘吞吐趋势；序列: 读吞吐, 写吞吐；最新值: 12.1, 8.4"
                    ),
                    "priority": 9,
                },
            ],
            "images": [
                {
                    "caption": "资源使用趋势；序列: CPU 使用率, 内存使用率, 磁盘使用率, I/O Wait 占比；最新值: 86.0, 79.0, 82.9, 6.9",
                    "dataUrl": _tiny_png_data_url(),
                },
                {
                    "caption": "磁盘吞吐趋势；序列: 读吞吐, 写吞吐；最新值: 12.1, 8.4",
                    "dataUrl": _tiny_png_data_url() + "A",
                },
            ],
        }
        result = chat_svc.inject_page_context("磁盘使用率高吗", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 1
        text = result[-1]["message"]
        assert "资源使用趋势" in text
        assert "磁盘使用率: 82.9%" in text
        assert "磁盘吞吐趋势" not in text
        assert "《资源使用趋势》" in text

    def test_cpu_time_question_keeps_distribution_chart(self):
        page_context = {
            "sections": [
                {
                    "id": "visible-charts",
                    "label": "可见图表",
                    "content": "1. 图表；Y轴: 0~100\n2. 资源使用趋势；序列: CPU 使用率\n3. CPU 时间分布；序列: 用户态, 内核态",
                    "priority": 9,
                }
            ],
            "images": [
                {"caption": "图表；Y轴: 0~100", "dataUrl": _tiny_png_data_url()},
                {"caption": "资源使用趋势；序列: CPU 使用率", "dataUrl": _tiny_png_data_url() + "A"},
                {"caption": "CPU 时间分布；序列: 用户态, 内核态", "dataUrl": _tiny_png_data_url() + "B"},
            ],
        }
        result = chat_svc.inject_page_context("分析下cpu时间分布", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 1
        text = result[-1]["message"]
        assert "CPU 时间分布" in text
        assert "资源使用趋势" not in text
        assert "《CPU 时间分布》" in text
        assert "本轮用户问题是「分析下cpu时间分布」" in text
        assert text.index("本轮用户问题是") < text.index("\n\n分析下cpu时间分布")

    def test_cpu_usage_time_paraphrase_keeps_distribution_not_resource_trend(self):
        page_context = {
            "sections": [
                {
                    "id": "visible-charts",
                    "label": "可见图表",
                    "content": (
                        "1. 资源使用趋势；序列: CPU 使用率, 内存使用率, 磁盘使用率, I/O Wait 占比；最新值: 39.6, 62.5, 80.9, 3.2\n"
                        "2. 系统负载趋势；序列: 1 分钟, 5 分钟, 15 分钟；最新值: 2.0, 1.8, 1.6\n"
                        "3. CPU 时间分布；序列: 用户态 55.0% (21.8%), 内核态 28.0% (11.1%)"
                    ),
                    "priority": 9,
                }
            ],
            "images": [
                {
                    "caption": "资源使用趋势；序列: CPU 使用率, 内存使用率, 磁盘使用率, I/O Wait 占比；最新值: 39.6, 62.5, 80.9, 3.2",
                    "dataUrl": _tiny_png_data_url(),
                },
                {"caption": "系统负载趋势；序列: 1 分钟, 5 分钟, 15 分钟；最新值: 2.0, 1.8, 1.6", "dataUrl": _tiny_png_data_url() + "A"},
                {
                    "caption": "CPU 时间分布；序列: 用户态 55.0% (21.8%), 内核态 28.0% (11.1%)",
                    "dataUrl": _tiny_png_data_url() + "B",
                },
            ],
        }
        assert chat_svc.chart_title_matches_question("CPU 时间分布", "具体分析下CPU使用时间")
        assert not chat_svc.chart_title_matches_question("资源使用趋势", "具体分析下CPU使用时间")
        assert not chat_svc.chart_title_matches_question("磁盘吞吐趋势", "磁盘使用率高吗")
        assert chat_svc.chart_matches_question(
            "资源使用趋势；序列: CPU 使用率, 内存使用率, 磁盘使用率, I/O Wait 占比；最新值: 86.0, 79.0, 82.9, 6.9",
            "磁盘使用率高吗",
        )
        assert not chat_svc.chart_matches_question(
            "磁盘吞吐趋势；序列: 读吞吐, 写吞吐；最新值: 12.1, 8.4",
            "磁盘使用率高吗",
        )
        result = chat_svc.inject_page_context("具体分析下CPU使用时间", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 1
        text = result[-1]["message"]
        assert "CPU 时间分布" in text
        assert "《CPU 时间分布》" in text
        assert "资源使用趋势" not in text
        assert "80.9" not in text
        assert "本轮用户问题是「具体分析下CPU使用时间」" in text

    def test_history_drops_when_focused_chart_changes(self):
        history = [
            {"event": "user", "message": "分析下cpu时间分布"},
            {"event": "bot", "message": "根据图表《CPU 时间分布》分析如下：用户态 76.4%"},
        ]
        # 本轮点名任一图表都丢历史，避免切换时间筛选后复述旧时间窗结论。
        assert chat_svc._history_for_focused_charts(history, ["系统负载趋势"]) == []
        assert chat_svc._history_for_focused_charts(history, ["CPU 时间分布"]) == []
        assert chat_svc._history_for_focused_charts(history, []) == history
        overview_history = [
            {"event": "user", "message": "分析这个主机的情况"},
            {"event": "bot", "message": "磁盘使用率 80.9%，内存 62.5%"},
        ]
        assert chat_svc._history_for_focused_charts(overview_history, ["CPU 时间分布"]) == []

    def test_overview_question_keeps_all_charts(self):
        page_context = {
            "images": [
                {"caption": "系统负载趋势；最新值: 1.98", "dataUrl": _tiny_png_data_url()},
                {"caption": "磁盘使用率 Top；最新值: 80.9", "dataUrl": _tiny_png_data_url() + "A"},
            ],
        }
        result = chat_svc.inject_page_context("当前仪表盘哪个指标异常", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 2

    def test_generic_captions_cannot_focus(self):
        page_context = {
            "images": [
                {"caption": "图表；最新值: 1.98, 1.8, 1.58", "dataUrl": _tiny_png_data_url()},
                {"caption": "图表；最新值: 80.9", "dataUrl": _tiny_png_data_url() + "A"},
            ],
        }
        result = chat_svc.inject_page_context("分析下磁盘使用率情况", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 2

    def test_drops_oversized_and_extra_images(self):
        huge = "data:image/png;base64," + ("A" * (chat_svc.PAGE_CONTEXT_MAX_IMAGE_CHARS + 10))
        images = [{"caption": f"c{i}", "dataUrl": _tiny_png_data_url()} for i in range(8)]
        images.append({"caption": "huge", "dataUrl": huge})
        result = chat_svc.inject_page_context("q", {"images": images})
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 6
        assert all(len(item["image_url"]) <= chat_svc.PAGE_CONTEXT_MAX_IMAGE_CHARS for item in image_items)

    def test_rejects_remote_image_urls(self):
        page_context = {
            "images": [
                {"caption": "ok", "dataUrl": _tiny_png_data_url()},
                {"caption": "remote", "dataUrl": "https://evil.example/x.png"},
                {"caption": "http", "dataUrl": "http://127.0.0.1/secret.png"},
                {"caption": "text-data", "dataUrl": "data:text/plain;base64,YQ=="},
            ],
        }
        result = chat_svc.inject_page_context("q", page_context)
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 1
        assert image_items[0]["image_url"].startswith("data:image/")


class TestStreamPageContext:
    def test_injects_into_llm_params_but_persists_plain_text(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser()
        page_context = {
            "title": "host dashboard",
            "sections": [{"id": "obj", "label": "实例", "content": "host-1", "priority": 5}],
            "images": [{"caption": "cpu", "dataUrl": _tiny_png_data_url()}],
        }
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="这个尖峰是什么",
                    request=_stream_request(user),
                    external_user_id="u@domain.com",
                    session_id="sess-pc-1",
                    page_context=page_context,
                )
        params = mock_stream.call_args.args[0]
        injected = params["user_message"]
        assert isinstance(injected, list)
        assert any(item.get("type") == "image_url" for item in injected)
        assert "host-1" in injected[-1]["message"]
        user_msgs = list(SkillConversationMessage.objects.filter(role="user"))
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "这个尖峰是什么"
        assert "<current_page>" not in user_msgs[0].content
        assert "data:image" not in user_msgs[0].content

    def test_missing_page_context_matches_baseline(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_su2")
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su2"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="hi",
                    request=_stream_request(user),
                    external_user_id="u2@domain.com",
                    session_id="sess-pc-empty",
                )
        params = mock_stream.call_args.args[0]
        assert params["user_message"] == "hi"
        assert SkillConversationMessage.objects.filter(role="user", content="hi").exists()

    def test_second_turn_keeps_only_latest_snapshot(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_su3")
        request = _stream_request(user)
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su3"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="第一问",
                    request=request,
                    external_user_id="u3@domain.com",
                    session_id="sess-pc-2",
                    page_context={"sections": [{"id": "a", "label": "A", "content": "SNAPSHOT-A", "priority": 1}]},
                )
                conv = SkillConversation.objects.get(session_id="sess-pc-2")
                SkillConversationMessage.objects.create(
                    conversation=conv,
                    role=SkillConversationMessage.ROLE_ASSISTANT,
                    content="答一",
                )
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="第二问",
                    request=request,
                    external_user_id="u3@domain.com",
                    session_id="sess-pc-2",
                    page_context={"sections": [{"id": "b", "label": "B", "content": "SNAPSHOT-B", "priority": 1}]},
                )
        second_params = mock_stream.call_args.args[0]
        assert "SNAPSHOT-B" in second_params["user_message"]
        assert "SNAPSHOT-A" not in second_params["user_message"]
        history_blob = str(second_params["chat_history"])
        assert "SNAPSHOT-A" not in history_blob
        assert "SNAPSHOT-B" not in history_blob
        stored = list(SkillConversationMessage.objects.filter(conversation__session_id="sess-pc-2", role="user").values_list("content", flat=True))
        assert stored == ["第一问", "第二问"]

    def test_named_chart_followup_drops_previous_chart_history(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_su_focus")
        request = _stream_request(user)
        page_context = {
            "images": [
                {"caption": "CPU 时间分布；序列: 用户态 76.4% (21.8%)", "dataUrl": _tiny_png_data_url()},
                {"caption": "系统负载趋势；序列: 1 分钟, 5 分钟", "dataUrl": _tiny_png_data_url() + "A"},
            ]
        }
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su_focus"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="分析下cpu时间分布",
                    request=request,
                    external_user_id="u-focus@domain.com",
                    session_id="sess-pc-focus",
                    page_context=page_context,
                )
                conv = SkillConversation.objects.get(session_id="sess-pc-focus")
                SkillConversationMessage.objects.create(
                    conversation=conv,
                    role=SkillConversationMessage.ROLE_ASSISTANT,
                    content="根据图表《CPU 时间分布》分析如下：用户态 76.4%",
                )
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="介绍下系统负载趋势",
                    request=request,
                    external_user_id="u-focus@domain.com",
                    session_id="sess-pc-focus",
                    page_context=page_context,
                )
        second_params = mock_stream.call_args.args[0]
        assert second_params["chat_history"] == []
        injected = second_params["user_message"]
        text = injected[-1]["message"] if isinstance(injected, list) else injected
        assert "《系统负载趋势》" in text
        assert "不要沿用上一问的结论、表格、图表名或时间范围" in text

    def test_overview_then_cpu_paraphrase_drops_host_analysis(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_su_overview")
        request = _stream_request(user)
        page_context = {
            "images": [
                {
                    "caption": "资源使用趋势；序列: CPU 使用率, 内存使用率, 磁盘使用率；最新值: 39.6, 62.5, 80.9",
                    "dataUrl": _tiny_png_data_url(),
                },
                {"caption": "系统负载趋势；序列: 1 分钟, 5 分钟；最新值: 2.0, 1.8", "dataUrl": _tiny_png_data_url() + "A"},
                {
                    "caption": "CPU 时间分布；序列: 用户态 55.0% (21.8%), 内核态 28.0% (11.1%)",
                    "dataUrl": _tiny_png_data_url() + "B",
                },
            ]
        }
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su_overview"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="分析这个主机的情况",
                    request=request,
                    external_user_id="u-overview@domain.com",
                    session_id="sess-pc-overview",
                    page_context=page_context,
                )
                conv = SkillConversation.objects.get(session_id="sess-pc-overview")
                SkillConversationMessage.objects.create(
                    conversation=conv,
                    role=SkillConversationMessage.ROLE_ASSISTANT,
                    content="根据当前监控仪表盘，对主机 local 的情况分析如下：磁盘使用率 80.9%",
                )
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="具体分析下CPU使用时间",
                    request=request,
                    external_user_id="u-overview@domain.com",
                    session_id="sess-pc-overview",
                    page_context=page_context,
                )
        second_params = mock_stream.call_args.args[0]
        assert second_params["chat_history"] == []
        injected = second_params["user_message"]
        text = injected[-1]["message"] if isinstance(injected, list) else injected
        assert "《CPU 时间分布》" in text
        assert "资源使用趋势" not in text
        assert "80.9" not in text
        assert "不要沿用上一问的结论、表格、图表名或时间范围" in text


class TestPageContextIngestLog:
    def test_report_counts_tokens_without_image_payload(self):
        page_context = {
            "url": "/monitor/view/dashboard/host",
            "app": "monitor",
            "title": "host",
            "sections": [{"id": "obj", "label": "实例", "content": "主机 local CPU 尖峰", "priority": 5}],
            "images": [{"caption": "CPU", "dataUrl": _tiny_png_data_url()}],
        }
        injected = chat_svc.inject_page_context("这个尖峰是什么", page_context)
        report = chat_svc.build_page_context_ingest_report(
            persist_text="这个尖峰是什么",
            injected_user_message=injected,
            page_context=page_context,
            skill_prompt="你是运维助手",
            chat_history=[{"event": "user", "message": "上一问"}, {"event": "bot", "message": "上一答"}],
        )
        assert report is not None
        assert report["url"] == "/monitor/view/dashboard/host"
        assert report["user_question"] == "这个尖峰是什么"
        assert report["user_question_tokens"] > 0
        assert report["snapshot_tokens"] > report["user_question_tokens"]
        assert "<current_page>" in report["snapshot_text"]
        assert "主机 local CPU 尖峰" in report["snapshot_text"]
        assert report["image_count"] == 1
        assert report["image_est_tokens"] == chat_svc.PAGE_CONTEXT_IMAGE_TOKEN_ESTIMATE
        assert report["sections"][0]["id"] == "obj"
        assert "data:image" not in json.dumps(report, ensure_ascii=False)
        assert report["estimated_input_tokens"] == (
            report["user_question_tokens"]
            + report["snapshot_tokens"]
            + report["skill_prompt_tokens"]
            + report["history_tokens"]
            + report["image_est_tokens"]
        )

    def test_empty_context_has_no_report(self):
        assert (
            chat_svc.build_page_context_ingest_report(
                persist_text="hi",
                injected_user_message="hi",
                page_context=None,
            )
            is None
        )

    def test_absent_page_context_logs_debug_without_question_payload(self, caplog):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_absent_log")
        question = "SECRET_PAGE_CONTEXT_ABSENT_QUESTION_SENTINEL"
        session_id = "sess-pc-absent"
        caplog.set_level(logging.DEBUG, logger="opspilot")
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_absent_log"},
            ):
                resp = chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message=question,
                    request=_stream_request(user, message=question),
                    external_user_id="absent@domain.com",
                    session_id=session_id,
                    page_context=None,
                )
        assert isinstance(resp, StreamingHttpResponse)
        assert resp["Content-Type"].startswith("text/event-stream")
        mock_stream.assert_called_once()
        params = mock_stream.call_args.args[0]
        ingest_kwargs = mock_stream.call_args.args[2]
        assert params["user_message"] == question
        assert "page_context_ingest" not in ingest_kwargs
        assert SkillConversationMessage.objects.filter(role="user", content=question).exists()

        records = [record for record in caplog.records if "page_context absent" in str(record.msg)]
        assert len(records) == 1
        record = records[0]
        assert record.name == "opspilot"
        assert record.levelno == logging.DEBUG
        assert record.msg == "page_context absent: session_id=%s"
        assert record.args == (session_id,)
        rendered = record.getMessage()
        formatted = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
        assert rendered == f"page_context absent: session_id={session_id}"
        assert question not in rendered
        assert question not in formatted
        assert question not in "".join(str(part) for part in record.args)
        assert question not in caplog.text
        assert not any(rec.levelno >= logging.INFO and "page_context absent" in rec.getMessage() for rec in caplog.records)

    def test_emits_summary_at_info_and_details_at_debug(self):
        report = chat_svc.build_page_context_ingest_report(
            persist_text="现在负载如何",
            injected_user_message=chat_svc.inject_page_context(
                "现在负载如何",
                {"title": "host", "sections": [{"id": "m", "label": "概览", "content": "CPU 42%", "priority": 1}]},
            ),
            page_context={"title": "host", "sections": [{"id": "m", "label": "概览", "content": "CPU 42%", "priority": 1}]},
        )
        with patch.object(chat_svc.logger, "info") as mock_info, patch.object(chat_svc.logger, "debug") as mock_debug:
            chat_svc.log_page_context_ingest(report)
        info_messages = [" ".join(str(a) for a in call.args) for call in mock_info.call_args_list]
        debug_messages = [" ".join(str(a) for a in call.args) for call in mock_debug.call_args_list]
        assert len(info_messages) == 1
        assert "page_context ingest:" in info_messages[0]
        assert "现在负载如何" in info_messages[0]
        assert any("page_context section" in msg for msg in debug_messages)
        assert any("page_context ingest_total" in msg for msg in debug_messages)
        assert not any("page_context snapshot_prompt" in msg for msg in info_messages + debug_messages)
        assert not any("page_context injected_user_prompt" in msg for msg in info_messages + debug_messages)

    def test_stream_stores_ingest_on_request_kwargs(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_log")
        page_context = {
            "title": "host dashboard",
            "sections": [{"id": "obj", "label": "实例", "content": "host-1", "priority": 5}],
        }
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_log"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="看下这台机器",
                    request=_stream_request(user),
                    external_user_id="log@domain.com",
                    session_id="sess-pc-log",
                    page_context=page_context,
                )
        kwargs = mock_stream.call_args.args[2]
        ingest = kwargs["page_context_ingest"]
        assert ingest["title"] == "host dashboard"
        assert ingest["user_question"] == "看下这台机器"
        assert "host-1" in ingest["snapshot_text"]
        assert ingest["snapshot_tokens"] > 0
        assert ingest["estimated_input_tokens"] > ingest["snapshot_tokens"]


class TestPageContextMultimodalAndBudget:
    def test_drop_images_keeps_text(self):
        injected = chat_svc.inject_page_context(
            "看图",
            {"images": [{"caption": "CPU", "dataUrl": _tiny_png_data_url()}], "title": "t"},
        )
        assert any(item.get("type") == "image_url" for item in injected)
        stripped = chat_svc.drop_images_from_user_message(injected)
        if isinstance(stripped, list):
            assert not any(item.get("type") == "image_url" for item in stripped)
            text = stripped[-1]["message"]
        else:
            text = stripped
        assert "CPU" in text
        assert "<current_page>" in text

    def test_non_multimodal_model_strips_images_in_stream(self):
        vendor = ModelVendor.objects.create(name="v-pc", vendor_type="openai", api_base="http://x", team=[1])
        model = LLMModel.objects.create(name="text-only", team=[1], vendor=vendor, model="m", is_multimodal=False)
        skill = LLMSkill.objects.create(name="pc-mm", team=[1], usage_team=[1], llm_model=model)
        ch = _channel(skill)
        user = _superuser("page_ctx_mm")
        page_context = {
            "title": "host",
            "sections": [{"id": "obj", "label": "实例", "content": "host-1", "priority": 5}],
            "images": [{"caption": "CPU", "dataUrl": _tiny_png_data_url()}],
        }
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_mm"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="分析下",
                    request=_stream_request(user),
                    external_user_id="mm@domain.com",
                    session_id="sess-pc-mm",
                    page_context=page_context,
                )
        params = mock_stream.call_args.args[0]
        msg = params["user_message"]
        if isinstance(msg, list):
            assert not any(item.get("type") == "image_url" for item in msg)
            text = msg[-1]["message"]
        else:
            text = msg
        assert "CPU" in text

    def test_single_turn_budget_returns_error_stream(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_budget")
        page_context = {
            "title": "host",
            "sections": [{"id": "obj", "label": "实例", "content": "host-1", "priority": 5}],
            "images": [{"caption": "CPU", "dataUrl": _tiny_png_data_url()}],
        }
        with patch.object(chat_svc, "PAGE_CONTEXT_SINGLE_TURN_MAX_TOKENS", 1):
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_budget"},
            ):
                with patch(
                    "apps.opspilot.services.skill_channel_chat_service.stream_agui_chat",
                ) as mock_stream:
                    with patch(
                        "apps.opspilot.services.skill_channel_chat_service.create_error_stream_response",
                    ) as mock_err:
                        mock_err.return_value = StreamingHttpResponse(
                            iter([b"err"]),
                            content_type="text/event-stream",
                        )
                        resp = chat_svc.stream_skill_channel_chat(
                            channel=ch,
                            user_message="分析",
                            request=_stream_request(user),
                            external_user_id="budget@domain.com",
                            session_id="sess-pc-budget",
                            page_context=page_context,
                        )
                        mock_stream.assert_not_called()
                        mock_err.assert_called_once_with(chat_svc.PAGE_CONTEXT_TOO_LARGE_MESSAGE)
        assert isinstance(resp, StreamingHttpResponse)

    def test_session_budget_returns_new_session_hint(self):
        assert (
            chat_svc.page_context_budget_error(
                {
                    "snapshot_tokens": 10,
                    "image_est_tokens": 10,
                    "estimated_input_tokens": chat_svc.PAGE_CONTEXT_SESSION_MAX_TOKENS + 1,
                }
            )
            == chat_svc.PAGE_CONTEXT_SESSION_OVERFLOW_MESSAGE
        )
