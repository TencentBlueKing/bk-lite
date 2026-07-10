"""knowledge_retrieve 工具单元测试（_service 层：mock 检索服务，无 DB / 无真实检索）。

校验内容：
- 工具名称 / 参数 schema（query 必填，kb_ids 可选）。
- 调用时按知识库逐个调用 search_fn，且传入正确的 query / kwargs。
- 结果被格式化为带来源标签的字符串。
- kb_ids 过滤、空结果、QA 模式、单库异常隔离等边界行为。
"""

from types import SimpleNamespace

import pytest

from apps.opspilot.metis.llm.tools.knowledge_tool import build_knowledge_retrieve_tool


def _make_kb(kb_id, name):
    """构造一个最小化的知识库桩对象（仅需 id / name）。"""
    return SimpleNamespace(id=kb_id, name=name)


@pytest.mark.unit
class TestBuildKnowledgeRetrieveTool:
    def test_tool_name_and_args_schema(self):
        """工具名为 knowledge_retrieve，参数包含必填 query 与可选 kb_ids。"""
        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[_make_kb(1, "KB-A")],
            kwargs_map={1: {"foo": "bar"}},
            search_fn=lambda *a, **k: [],
        )
        assert tool.name == "knowledge_retrieve"

        schema = tool.args_schema.model_json_schema()
        props = schema["properties"]
        assert "query" in props
        assert "kb_ids" in props
        assert "query" in schema.get("required", [])
        # kb_ids 可选
        assert "kb_ids" not in schema.get("required", [])

    def test_invokes_search_per_kb_with_query_and_kwargs(self):
        """每个知识库各调用一次 search_fn，并传入对应 query 和 kwargs。"""
        calls = []

        def fake_search(kb, query, kwargs, score_threshold=0, is_qa=False):
            calls.append((kb, query, kwargs, score_threshold, is_qa))
            return [{"content": f"内容-{kb.name}", "score": 0.9, "knowledge_id": 7, "knowledge_title": "标题"}]

        kb_a, kb_b = _make_kb(1, "KB-A"), _make_kb(2, "KB-B")
        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[kb_a, kb_b],
            kwargs_map={1: {"k": "a"}, 2: {"k": "b"}},
            search_fn=fake_search,
            score_threshold=0.5,
        )

        result = tool.invoke({"query": "怎么重启服务"})

        assert len(calls) == 2
        assert calls[0][0] is kb_a
        assert calls[0][1] == "怎么重启服务"
        assert calls[0][2] == {"k": "a"}
        assert calls[0][3] == 0.5
        assert calls[1][0] is kb_b
        assert calls[1][2] == {"k": "b"}
        # 结果格式化包含来源与内容
        assert "内容-KB-A" in result
        assert "内容-KB-B" in result
        assert "KB-A" in result
        assert "标题" in result

    def test_kb_ids_filter(self):
        """传入 kb_ids 时仅检索匹配的知识库。"""
        seen = []

        def fake_search(kb, query, kwargs, score_threshold=0, is_qa=False):
            seen.append(kb.id)
            return [{"content": "x", "score": 0.1, "knowledge_id": 1, "knowledge_title": "t"}]

        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[_make_kb(1, "A"), _make_kb(2, "B"), _make_kb(3, "C")],
            kwargs_map={1: {}, 2: {}, 3: {}},
            search_fn=fake_search,
        )

        tool.invoke({"query": "q", "kb_ids": [2]})
        assert seen == [2]

    def test_kb_ids_filter_accepts_string_ids(self):
        """kb_ids 以字符串形式传入时也能匹配整型知识库 id。"""
        seen = []

        def fake_search(kb, query, kwargs, score_threshold=0, is_qa=False):
            seen.append(kb.id)
            return []

        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[_make_kb(1, "A"), _make_kb(2, "B")],
            kwargs_map={1: {}, 2: {}},
            search_fn=fake_search,
        )
        tool.invoke({"query": "q", "kb_ids": ["1"]})
        assert seen == [1]

    def test_empty_results_returns_placeholder(self):
        """所有知识库均无命中时返回占位提示而非空串。"""
        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[_make_kb(1, "A")],
            kwargs_map={1: {}},
            search_fn=lambda *a, **k: [],
        )
        result = tool.invoke({"query": "q"})
        assert isinstance(result, str)
        assert result.strip() != ""

    def test_qa_mode_formats_question_answer(self):
        """QA 模式下使用 question/answer 字段格式化。"""

        def fake_search(kb, query, kwargs, score_threshold=0, is_qa=False):
            assert is_qa is True
            return [{"question": "如何登录", "answer": "用账号密码", "score": 0.8, "knowledge_id": 3, "knowledge_title": "登录"}]

        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[_make_kb(1, "FAQ")],
            kwargs_map={1: {}},
            search_fn=fake_search,
            is_qa=True,
        )
        result = tool.invoke({"query": "登录"})
        assert "如何登录" in result
        assert "用账号密码" in result

    def test_single_kb_exception_is_isolated(self):
        """某个知识库检索抛错不应中断其它知识库。"""

        def fake_search(kb, query, kwargs, score_threshold=0, is_qa=False):
            if kb.id == 1:
                raise RuntimeError("boom")
            return [{"content": "ok", "score": 0.5, "knowledge_id": 2, "knowledge_title": "t2"}]

        tool = build_knowledge_retrieve_tool(
            knowledge_bases=[_make_kb(1, "bad"), _make_kb(2, "good")],
            kwargs_map={1: {}, 2: {}},
            search_fn=fake_search,
        )
        result = tool.invoke({"query": "q"})
        assert "ok" in result

    def test_default_search_fn_is_knowledge_search_service(self):
        """不注入 search_fn 时显式抛错(原 KnowledgeSearchService 已随知识库功能一起删除,不再兜底 default)。"""
        import pytest as _pytest
        with _pytest.raises(ValueError, match="需要显式 search_fn"):
            build_knowledge_retrieve_tool(
                knowledge_bases=[_make_kb(1, "A")],
                kwargs_map={1: {}},
            )
