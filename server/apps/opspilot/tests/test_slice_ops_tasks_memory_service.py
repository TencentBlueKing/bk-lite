"""ops-tasks-engine 切片: tasks.py 记忆写入 / 批量缓存 / chatflow celery 任务真实测试。

聚焦真实编排与 DB 副作用，仅在 LLM 客户端与 ChatFlow 引擎工厂等外部边界打桩：
- process_memory_write: 无模型时直接创建/追加；有模型时 write_rule 规范化 + 智能合并
  （LLM 返回真实形态 JSON）；JSON/LLM 失败推迟写入不落原文；记忆空间不存在抛错
- process_memory_write_cache: 缺 workflow_id/node_id 回退直接写入；未达阈值仅缓存不 flush；
  达阈值触发 flush（写入 Memory 并清空缓存）
- _flush_memory_write_cache_group: 强制 flush 真实落库 + 缓存删除；空批内容直接清理
- flush_memory_write_cache_for_node / flush_all_pending_memory_write_cache 编排
- _resolve_org_display_name: 命中组名 / 回退“组织-{id}”
- chat_flow_celery_task / chat_flow_test_execute_task: bot 不存在/无 chatflow 短路；正常执行
- _get_bot_chat_flow: 下线 bot 返回 None
- cleanup_expired_workflow_attachments_task

外部边界打桩：tasks._build_memory_write_client（LLM）、tasks.create_chat_flow_engine（引擎）、
cleanup_expired_workflow_attachments（存储清理）。DB 用真实 Postgres。
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pydantic.root_model  # noqa  预热
import pytest

from apps.opspilot import tasks
from apps.opspilot.models import Bot, BotWorkFlow, Memory, MemorySpace, MemoryWriteCache
from apps.opspilot.tasks.memory import _MEMORY_WRITE_DEFERRED_FLUSH_LOG, _MEMORY_WRITE_DEFERRED_WRITE_LOG, MemoryWriteLlmUnavailable

_LLM_PAYLOAD_SENTINEL = "RCA_PAYLOAD_SENTINEL_DO_NOT_LOG"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_close_connections(mocker):
    """tasks 内部用 close_old_connections() 管理连接生命周期（针对 celery/eventlet 真实运行环境）。
    在 pytest-django 的事务回滚包裹下，它会关闭测试事务赖以工作的连接，与被测逻辑无关，
    属真实外部边界（连接池管理），在此打桩为 no-op，保证 DB 副作用断言可观测。"""
    mocker.patch("apps.opspilot.tasks.memory.close_old_connections", return_value=None)
    mocker.patch("apps.opspilot.tasks._common.close_old_connections", return_value=None)


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    """真实形态的 LLM 客户端桩：invoke 返回带 .content 的对象。"""

    def __init__(self, content):
        self._content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return _FakeResp(self._content)


class _SeqClient:
    """按调用顺序返回不同 LLM 响应。"""

    def __init__(self, *contents):
        self._contents = list(contents)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if not self._contents:
            raise AssertionError("unexpected extra LLM invoke")
        return _FakeResp(self._contents.pop(0))


def _make_space(**kw):
    defaults = dict(name="sp", team=[1], scope=MemorySpace.SCOPE_PERSONAL, write_rule="", default_model="")
    defaults.update(kw)
    return MemorySpace.objects.create(**defaults)


def _patch_write_client(mocker, client):
    return mocker.patch("apps.opspilot.tasks.memory._build_memory_write_client", return_value=client)


# ===========================================================================
# process_memory_write —— 无模型路径（不触发 LLM）
# ===========================================================================
class TestProcessMemoryWriteNoModel:
    def test_无模型创建个人记忆(self):
        sp = _make_space()
        result = tasks.process_memory_write(
            memory_space_id=sp.id,
            title="T",
            content="第一条",
            owner_username="alice",
            owner_domain="d.com",
        )
        mem = Memory.objects.get(memory_space=sp, owner_username="alice")
        assert result is None
        assert mem.content == "第一条"
        assert mem.organization_id is None

    def test_无模型追加到现有记忆(self):
        sp = _make_space()
        Memory.objects.create(memory_space=sp, title="T", content="旧", owner_username="bob", owner_domain="d.com", created_by="bob")
        tasks.process_memory_write(memory_space_id=sp.id, title="T2", content="新", owner_username="bob", owner_domain="d.com")
        mem = Memory.objects.get(memory_space=sp, owner_username="bob")
        assert "旧" in mem.content and "新" in mem.content
        # 不重复创建
        assert Memory.objects.filter(memory_space=sp, owner_username="bob").count() == 1

    def test_组织记忆按organization_id唯一(self):
        sp = _make_space(scope=MemorySpace.SCOPE_TEAM)
        tasks.process_memory_write(memory_space_id=sp.id, title="T", content="org内容", owner_username="组A", owner_domain="", organization_id=7)
        mem = Memory.objects.get(memory_space=sp, organization_id=7)
        assert mem.content == "org内容"

    def test_记忆空间不存在抛错(self):
        with pytest.raises(MemorySpace.DoesNotExist):
            tasks.process_memory_write(memory_space_id=999999, title="T", content="c", owner_username="x", owner_domain="d")

    @pytest.mark.django_db(transaction=True)
    def test_并发写入同一目标只创建一条并保留两次内容(self, mocker):
        sp = _make_space()
        original_get_memory = tasks._get_memory_for_target
        first_reads_done = Barrier(2)

        def synchronized_get_memory(*args, **kwargs):
            memory = original_get_memory(*args, **kwargs)
            if not kwargs.get("for_update", False):
                first_reads_done.wait(timeout=5)
            return memory

        mocker.patch.object(tasks, "_get_memory_for_target", side_effect=synchronized_get_memory)

        def write(content):
            tasks.process_memory_write(
                memory_space_id=sp.id,
                title="T",
                content=content,
                owner_username="alice",
                owner_domain="d.com",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(write, content) for content in ("第一条", "第二条")]
            for future in futures:
                future.result(timeout=10)

        memories = list(Memory.objects.filter(memory_space=sp, owner_username="alice", owner_domain="d.com"))
        assert len(memories) == 1
        assert "第一条" in memories[0].content
        assert "第二条" in memories[0].content


# ===========================================================================
# process_memory_write —— 有模型路径（LLM 边界打桩）
# ===========================================================================
class TestProcessMemoryWriteWithModel:
    def test_新记忆走write_rule规范化(self, mocker):
        sp = _make_space(write_rule="只保留要点", default_model="5")
        fake = _FakeClient("规范化后的内容")
        _patch_write_client(mocker, fake)
        tasks.process_memory_write(memory_space_id=sp.id, title="T", content="原始很长内容", owner_username="u", owner_domain="d")
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert mem.content == "规范化后的内容"
        # write_rule 触发了一次 LLM 规范化
        assert len(fake.calls) == 1

    def test_有现有记忆走LLM智能合并(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(memory_space=sp, title="旧标题", content="旧内容", owner_username="u", owner_domain="d", created_by="u")
        merged_json = '```json\n{"title": "合并标题", "content": "合并内容"}\n```'
        fake = _FakeClient(merged_json)
        _patch_write_client(mocker, fake)
        tasks.process_memory_write(memory_space_id=sp.id, title="T", content="新内容", owner_username="u", owner_domain="d")
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert mem.title == "合并标题"
        assert mem.content == "合并内容"

    def test_合并JSON解析失败不改写记忆(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(memory_space=sp, title="旧标题", content="旧内容", owner_username="u", owner_domain="d", created_by="u")
        fake = _FakeClient("不是合法JSON的返回")
        _patch_write_client(mocker, fake)
        with pytest.raises(MemoryWriteLlmUnavailable) as exc_info:
            tasks.process_memory_write(memory_space_id=sp.id, title="T", content="新内容", owner_username="u", owner_domain="d")
        assert exc_info.value.failed_stage == "merge"
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert mem.content == "旧内容"
        assert mem.title == "旧标题"

    def test_write_rule调用失败不落原文(self, mocker, caplog):
        sp = _make_space(write_rule="只保留要点", default_model="5")

        class _FailingClient:
            def invoke(self, messages):
                raise ConnectionError(_LLM_PAYLOAD_SENTINEL)

        _patch_write_client(mocker, _FailingClient())
        caplog.set_level(logging.WARNING, logger="opspilot")
        with pytest.raises(MemoryWriteLlmUnavailable) as exc_info:
            tasks.process_memory_write(memory_space_id=sp.id, title="T", content=_LLM_PAYLOAD_SENTINEL, owner_username="u", owner_domain="d")
        assert exc_info.value.failed_stage == "write_rule"
        assert Memory.objects.filter(memory_space=sp, owner_username="u").count() == 0
        records = [record for record in caplog.records if record.msg == _MEMORY_WRITE_DEFERRED_WRITE_LOG]
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        assert record.args == (sp.id, "write_rule", "ConnectionError")
        assert record.getMessage() == _MEMORY_WRITE_DEFERRED_WRITE_LOG % (sp.id, "write_rule", "ConnectionError")
        assert record.exc_info is None
        assert _LLM_PAYLOAD_SENTINEL not in record.msg
        assert _LLM_PAYLOAD_SENTINEL not in str(record.args)
        assert _LLM_PAYLOAD_SENTINEL not in caplog.text

    def test_配置模型但client构建失败回退直写(self, mocker):
        sp = _make_space(default_model="5")
        _patch_write_client(mocker, None)
        tasks.process_memory_write(memory_space_id=sp.id, title="T", content="直写内容", owner_username="u", owner_domain="d")
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert mem.content == "直写内容"

    def test_卡片键命中只更新该类且不把其它类送进模型(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(
            memory_space=sp,
            title="告警档案",
            content=(
                "### Unhealthy\n- reason: Unhealthy\n- 复发:\n"
                "  - 2026-08-06 20:03 | web | unknown\n\n"
                "### BackOff\n- reason: BackOff\n- 关键证据: pnpm install\n"
            ),
            owner_username="u",
            owner_domain="d",
            created_by="u",
        )
        fake = _SeqClient(
            '{"card": "### Unhealthy\\n- reason: Unhealthy\\n- 复发:\\n  - 2026-08-06 20:03 | web | unknown\\n  - 2026-09-09 11:00 | web | INC-1\\n"}'
        )
        _patch_write_client(mocker, fake)
        tasks.process_memory_write(
            memory_space_id=sp.id,
            title="T",
            content="### Unhealthy\n- reason: Unhealthy\n- 事件编号: INC-1\n",
            owner_username="u",
            owner_domain="d",
        )
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert "INC-1" in mem.content
        assert "### BackOff" in mem.content
        assert "pnpm install" in mem.content
        assert len(fake.calls) == 1
        prompt = fake.calls[0][-1].content
        assert "### Unhealthy" in prompt
        assert "pnpm install" not in prompt
        assert "已有类别目录" not in prompt

    def test_键未命中走目录语义归类再只更新命中卡片(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(
            memory_space=sp,
            title="告警档案",
            content="### Unhealthy\n- reason: Unhealthy\n- 关键证据: probe refused\n\n### BackOff\n- reason: BackOff\n- 关键证据: pnpm install\n",
            owner_username="u",
            owner_domain="d",
            created_by="u",
        )
        fake = _SeqClient(
            '{"action": "update", "index": 0}',
            '{"card": "### Unhealthy\\n- reason: Unhealthy\\n- 复发:\\n  - 2026-09-09 11:00 | web | INC-2\\n"}',
        )
        _patch_write_client(mocker, fake)
        tasks.process_memory_write(
            memory_space_id=sp.id,
            title="T",
            content="Readiness probe failed: connection refused",
            owner_username="u",
            owner_domain="d",
        )
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert "INC-2" in mem.content
        assert "pnpm install" in mem.content
        assert len(fake.calls) == 2
        classify_prompt = fake.calls[0][-1].content
        assert "已有类别目录" in classify_prompt
        assert "标题=Unhealthy" in classify_prompt
        assert "标题=BackOff" in classify_prompt
        assert "Readiness probe failed" in classify_prompt
        assert "### BackOff" not in classify_prompt
        update_prompt = fake.calls[1][-1].content
        assert "### Unhealthy" in update_prompt
        assert "### BackOff" not in update_prompt

    def test_目录判定新类则追加且不改旧卡片(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(
            memory_space=sp,
            title="告警档案",
            content="### Unhealthy\n- reason: Unhealthy\n",
            owner_username="u",
            owner_domain="d",
            created_by="u",
        )
        fake = _SeqClient('{"action": "create"}')
        _patch_write_client(mocker, fake)
        tasks.process_memory_write(
            memory_space_id=sp.id,
            title="T",
            content="### ImagePullBackOff\n- reason: ImagePullBackOff\n",
            owner_username="u",
            owner_domain="d",
        )
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert "### Unhealthy" in mem.content
        assert "### ImagePullBackOff" in mem.content
        assert len(fake.calls) == 1
        assert "已有类别目录" in fake.calls[0][-1].content

    def test_目录归类失败不改写记忆(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(
            memory_space=sp,
            title="告警档案",
            content="### Unhealthy\n- reason: Unhealthy\n",
            owner_username="u",
            owner_domain="d",
            created_by="u",
        )
        fake = _SeqClient("不是合法JSON的返回")
        _patch_write_client(mocker, fake)
        with pytest.raises(MemoryWriteLlmUnavailable) as exc_info:
            tasks.process_memory_write(
                memory_space_id=sp.id,
                title="T",
                content="Readiness probe failed",
                owner_username="u",
                owner_domain="d",
            )
        assert exc_info.value.failed_stage == "classify"
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert mem.content == "### Unhealthy\n- reason: Unhealthy\n"


# ===========================================================================
# process_memory_write_cache —— 批量缓存编排
# ===========================================================================
class TestProcessMemoryWriteCache:
    def test_缺workflow回退直接写入(self, mocker):
        sp = _make_space()
        direct = mocker.patch.object(tasks, "process_memory_write")
        tasks.process_memory_write_cache(memory_space_id=sp.id, title="T", content="c", owner_username="u", owner_domain="d", workflow_id=None)
        direct.assert_called_once()
        # 没有创建缓存
        assert MemoryWriteCache.objects.count() == 0

    def test_空内容直接返回(self):
        sp = _make_space()
        tasks.process_memory_write_cache(
            memory_space_id=sp.id, title="T", content="", owner_username="u", owner_domain="d", workflow_id=1, node_id="n"
        )
        assert MemoryWriteCache.objects.count() == 0

    def test_未达阈值仅缓存不flush(self, mocker):
        sp = _make_space()
        flush = mocker.patch.object(tasks, "_flush_memory_write_cache_group")
        tasks.process_memory_write_cache(
            memory_space_id=sp.id,
            title="T",
            content="c1",
            owner_username="u",
            owner_domain="d",
            workflow_id=1,
            node_id="n",
            write_batch_size=3,
        )
        # 缓存了一条，未触发 flush
        assert MemoryWriteCache.objects.filter(workflow_id=1, node_id="n").count() == 1
        flush.assert_not_called()

    def test_达阈值触发flush(self, mocker):
        sp = _make_space()
        flush = mocker.patch.object(tasks, "_flush_memory_write_cache_group", return_value=True)
        # batch_size=2，先放一条
        MemoryWriteCache.objects.create(workflow_id=1, node_id="n", memory_target_id="u@d", content="pre")
        tasks.process_memory_write_cache(
            memory_space_id=sp.id,
            title="T",
            content="c2",
            owner_username="u",
            owner_domain="d",
            workflow_id=1,
            node_id="n",
            write_batch_size=2,
        )
        flush.assert_called_once()


# ===========================================================================
# _flush_memory_write_cache_group —— 真实落库
# ===========================================================================
class TestFlushGroup:
    def test_强制flush写入记忆并删除缓存(self, mocker):
        sp = _make_space()
        MemoryWriteCache.objects.create(workflow_id=2, node_id="n", memory_target_id="u@d", content="A")
        MemoryWriteCache.objects.create(workflow_id=2, node_id="n", memory_target_id="u@d", content="B")
        # 跳过 LLM 归纳，使用原始拼接内容
        mocker.patch("apps.opspilot.tasks.memory._summarize_memory_batch_content", side_effect=lambda space, content, model_id=None: content)
        ok = tasks._flush_memory_write_cache_group(
            memory_space_id=sp.id,
            title="自动记忆",
            model_id=None,
            workflow_id=2,
            node_id="n",
            memory_target_id="u@d",
            force_flush=True,
        )
        assert ok is True
        # 缓存被清空
        assert MemoryWriteCache.objects.filter(workflow_id=2, node_id="n").count() == 0
        # 记忆已写入，内容含两条
        mem = Memory.objects.get(memory_space=sp, owner_username="u", owner_domain="d")
        assert "A" in mem.content and "B" in mem.content

    def test_无待处理项返回False(self):
        sp = _make_space()
        ok = tasks._flush_memory_write_cache_group(
            memory_space_id=sp.id, title="T", model_id=None, workflow_id=99, node_id="n", memory_target_id="x", force_flush=True
        )
        assert ok is False

    def test_归纳LLM失败保留缓存且不落库(self, mocker, caplog):
        sp = _make_space(default_model="5")
        cache_ids = [
            MemoryWriteCache.objects.create(workflow_id=4, node_id="n", memory_target_id="u@d", content="A").id,
            MemoryWriteCache.objects.create(workflow_id=4, node_id="n", memory_target_id="u@d", content="B").id,
        ]

        class _FailingClient:
            def invoke(self, messages):
                raise ConnectionError(_LLM_PAYLOAD_SENTINEL)

        _patch_write_client(mocker, _FailingClient())
        caplog.set_level(logging.WARNING, logger="opspilot")
        ok = tasks._flush_memory_write_cache_group(
            memory_space_id=sp.id,
            title="自动记忆",
            model_id=5,
            workflow_id=4,
            node_id="n",
            memory_target_id="u@d",
            force_flush=True,
        )
        assert ok is False
        remaining = list(MemoryWriteCache.objects.filter(id__in=cache_ids).order_by("id"))
        assert len(remaining) == 2
        assert all(item.status == MemoryWriteCache.STATUS_PENDING for item in remaining)
        assert all(item.processing_started_at is None for item in remaining)
        assert Memory.objects.filter(memory_space=sp).count() == 0
        records = [record for record in caplog.records if record.msg == _MEMORY_WRITE_DEFERRED_FLUSH_LOG]
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        assert record.args == (sp.id, 4, "n", 2, "summarize", "ConnectionError")
        assert record.getMessage() == _MEMORY_WRITE_DEFERRED_FLUSH_LOG % (sp.id, 4, "n", 2, "summarize", "ConnectionError")
        assert record.exc_info is None
        traceback_errors = [item for item in caplog.records if item.levelno >= logging.ERROR and item.exc_info]
        assert traceback_errors == []
        assert _LLM_PAYLOAD_SENTINEL not in record.msg
        assert _LLM_PAYLOAD_SENTINEL not in str(record.args)
        assert _LLM_PAYLOAD_SENTINEL not in caplog.text

    def test_合并LLM失败保留缓存且不改已有记忆(self, mocker):
        sp = _make_space(default_model="5")
        Memory.objects.create(memory_space=sp, title="旧标题", content="旧内容", owner_username="u", owner_domain="d", created_by="u")
        cache_ids = [
            MemoryWriteCache.objects.create(workflow_id=5, node_id="n", memory_target_id="u@d", content="新A").id,
            MemoryWriteCache.objects.create(workflow_id=5, node_id="n", memory_target_id="u@d", content="新B").id,
        ]
        mocker.patch("apps.opspilot.tasks.memory._summarize_memory_batch_content", return_value="归纳后的内容")

        class _FailingClient:
            def invoke(self, messages):
                raise ConnectionError("upstream down")

        _patch_write_client(mocker, _FailingClient())
        ok = tasks._flush_memory_write_cache_group(
            memory_space_id=sp.id,
            title="自动记忆",
            model_id=5,
            workflow_id=5,
            node_id="n",
            memory_target_id="u@d",
            force_flush=True,
        )
        assert ok is False
        remaining = list(MemoryWriteCache.objects.filter(id__in=cache_ids))
        assert len(remaining) == 2
        assert all(item.status == MemoryWriteCache.STATUS_PENDING for item in remaining)
        mem = Memory.objects.get(memory_space=sp, owner_username="u")
        assert mem.content == "旧内容"
        assert mem.title == "旧标题"


# ===========================================================================
# flush_memory_write_cache_for_node / flush_all_pending
# ===========================================================================
class TestFlushOrchestration:
    def test_for_node按target分组flush(self, mocker):
        sp = _make_space()
        MemoryWriteCache.objects.create(workflow_id=3, node_id="n", memory_target_id="u1@d", content="X")
        MemoryWriteCache.objects.create(workflow_id=3, node_id="n", memory_target_id="u2@d", content="Y")
        flush = mocker.patch.object(tasks, "_flush_memory_write_cache_group", return_value=True)
        tasks.flush_memory_write_cache_for_node(workflow_id=3, node_id="n", memory_space_id=sp.id)
        # 两个不同 target 各触发一次
        assert flush.call_count == 2
        targets = {c.kwargs["memory_target_id"] for c in flush.call_args_list}
        assert targets == {"u1@d", "u2@d"}

    def test_all_pending无待处理直接返回(self, mocker):
        flush = mocker.patch.object(tasks, "flush_memory_write_cache_for_node")
        tasks.flush_all_pending_memory_write_cache()
        flush.assert_not_called()

    def test_all_pending按节点配置flush(self, mocker):
        sp = _make_space()
        bot = Bot.objects.create(name="b", team=[1], usage_team=[1])
        wf = BotWorkFlow.objects.create(
            bot=bot,
            flow_json={"nodes": [{"id": "mw1", "type": "memory_write", "data": {"config": {"memorySpace": sp.id, "title": "记忆"}}}]},
        )
        MemoryWriteCache.objects.create(workflow_id=wf.id, node_id="mw1", memory_target_id="u@d", content="Z")
        flush = mocker.patch.object(tasks, "flush_memory_write_cache_for_node")
        tasks.flush_all_pending_memory_write_cache()
        flush.assert_called_once()
        assert flush.call_args.kwargs["node_id"] == "mw1"
        assert flush.call_args.kwargs["memory_space_id"] == sp.id


# ===========================================================================
# _resolve_org_display_name
# ===========================================================================
class TestResolveOrgDisplayName:
    def test_命中组名(self):
        from apps.system_mgmt.models import Group

        g = Group.objects.create(name="运维组", parent_id=0)
        assert tasks._resolve_org_display_name(g.id) == "运维组"

    def test_未命中回退组织id(self):
        assert tasks._resolve_org_display_name(123456) == "组织-123456"


# ===========================================================================
# chat_flow_celery_task / chat_flow_test_execute_task / _get_bot_chat_flow
# ===========================================================================
class _FakeEngine:
    def __init__(self):
        self.executed = None
        self.is_test = False
        self.entry_type = None

    def execute(self, input_data):
        self.executed = input_data
        return {"success": True}


@pytest.fixture
def _inline_native_thread(mocker):
    """_run_in_native_thread 把任务派发到独立线程（独立 DB 连接），在事务回滚的测试中
    看不到未提交数据。这是 eventlet/ORM 安全边界，与编排逻辑无关，桩为同线程直接执行，
    使测试可观测真实编排与 DB 副作用。"""

    def _inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    mocker.patch.object(tasks, "_run_in_native_thread", side_effect=_inline)


@pytest.mark.usefixtures("_inline_native_thread")
class TestChatFlowCeleryTasks:
    def test_bot不存在短路不建引擎(self, mocker):
        create = mocker.patch.object(tasks, "create_chat_flow_engine")
        tasks.chat_flow_celery_task(bot_id=999999, node_id="n", message="hi")
        create.assert_not_called()

    def test_bot无chatflow短路(self, mocker):
        bot = Bot.objects.create(name="b", team=[1], usage_team=[1], online=True)
        create = mocker.patch.object(tasks, "create_chat_flow_engine")
        tasks.chat_flow_celery_task(bot_id=bot.id, node_id="n", message="hi")
        create.assert_not_called()

    def test_正常执行构建输入并调用引擎(self, mocker):
        bot = Bot.objects.create(name="b", team=[1], usage_team=[1], online=True, created_by="creator")
        BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": [], "edges": []})
        engine = _FakeEngine()
        create = mocker.patch.object(tasks, "create_chat_flow_engine", return_value=engine)
        tasks.chat_flow_celery_task(bot_id=bot.id, node_id="nodeA", message="你好")
        create.assert_called_once_with(mocker.ANY, "nodeA", entry_type="celery")
        assert engine.executed == {
            "last_message": "你好",
            "user_id": "creator",
            "bot_id": bot.id,
            "node_id": "nodeA",
            "entry_type": "celery",
        }
        assert "caller_identity" not in engine.executed

    def test_test_execute_workflow不存在短路(self, mocker):
        create = mocker.patch.object(tasks, "create_chat_flow_engine")
        tasks.chat_flow_test_execute_task(workflow_id=999999, node_id="n", input_data={"last_message": "x"}, entry_type="openai", execution_id="e1")
        create.assert_not_called()

    def test_test_execute正常标记is_test(self, mocker):
        bot = Bot.objects.create(name="b", team=[1], usage_team=[1])
        wf = BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": [], "edges": []})
        engine = _FakeEngine()
        mocker.patch.object(tasks, "create_chat_flow_engine", return_value=engine)
        tasks.chat_flow_test_execute_task(workflow_id=wf.id, node_id="n", input_data={"last_message": "x"}, entry_type="restful", execution_id="e1")
        assert engine.is_test is True
        assert engine.entry_type == "restful"
        assert engine.executed == {"last_message": "x"}

    def test_get_bot_chat_flow下线bot返回None(self):
        bot = Bot.objects.create(name="b", team=[1], usage_team=[1], online=False)
        BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": []})
        assert tasks._get_bot_chat_flow(bot.id) is None


# ===========================================================================
# cleanup_expired_workflow_attachments_task
# ===========================================================================
class TestCleanupTask:
    def test_返回清理数量(self, mocker):
        mocker.patch.object(tasks, "cleanup_expired_workflow_attachments", return_value=5)
        assert tasks.cleanup_expired_workflow_attachments_task() == 5
