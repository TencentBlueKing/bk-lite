"""LATS Agent 同步决策与树搜索单元测试 (metis/llm/agent/lats_agent.py)。

mock 边界:
- LatsAgentNode 不调用真实 setup(),直接实例化并注入伪 structured_output_parser
  (AsyncMock 返回结构化 MultiDimensionalReflection),只测同步树/评分/决策逻辑及
  异步评估的入参契约与降级分支。不连真实 LLM / 不跑 LangGraph 流式。

断言: MCTS 节点统计(backpropagate/UCB/best_child/height/tree_size)、
MultiDimensionalReflection 派生(normalized_score/as_message/create_default)、
解决方案标记与回溯、剪枝、should_continue 全部分支、select_node_for_expansion 选择、
候选并行评估的降级与早停。
"""

import asyncio
import math
from unittest.mock import AsyncMock

import pydantic.root_model  # noqa
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from apps.opspilot.metis.llm.agent.lats_agent import (
    LATSConfig,
    LATSTreeNode,
    LatsAgentNode,
    MultiDimensionalReflection,
    SearchPhase,
)


def make_reflection(score=6.0, confidence=0.7, found_solution=False):
    return MultiDimensionalReflection(
        accuracy=score, completeness=score, relevance=score, clarity=score,
        creativity=score, actionability=score, overall_score=score,
        confidence=confidence, strengths=["a"], weaknesses=["b"], suggestions=["c"],
        found_solution=found_solution, needs_tools=False,
    )


# ============================ MultiDimensionalReflection ============================
class TestReflection:
    def test_normalized_score(self):
        assert make_reflection(8.0).normalized_score == 0.8

    def test_as_message_renders_dimensions(self):
        r = make_reflection(7.0, confidence=0.55)
        msg = r.as_message()
        assert isinstance(msg, HumanMessage)
        assert "置信度: 0.55" in msg.content
        assert "7.0/10" in msg.content
        # 优点/不足/建议被拼接
        assert "a" in msg.content and "b" in msg.content and "c" in msg.content

    def test_create_default_derives_fields(self):
        r = MultiDimensionalReflection.create_default(8.0)
        assert r.overall_score == 8.0
        # creativity = score*0.8, actionability = score*0.9
        assert r.creativity == pytest.approx(6.4)
        assert r.actionability == pytest.approx(7.2)
        assert r.confidence == 0.6
        # basic_score>=7 -> found_solution True
        assert r.found_solution is True
        assert r.needs_tools is False

    def test_create_default_low_score_not_solution(self):
        r = MultiDimensionalReflection.create_default(4.0)
        assert r.found_solution is False


# ============================ LATSTreeNode ============================
class TestTreeNode:
    def test_root_backpropagate_on_init(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        # __init__ 末尾调用一次 backpropagate(normalized_score=0.6)
        assert root.visits == 1
        assert root.total_reward == pytest.approx(0.6)
        assert root.average_reward == pytest.approx(0.6)
        assert root.depth == 1
        assert root.is_terminal is True

    def test_child_depth_and_backpropagate_to_parent(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        child = LATSTreeNode(messages=[AIMessage(content="a")], reflection=make_reflection(8.0), parent=root)
        root.children.append(child)
        assert child.depth == 2
        # 子节点 init 时 backpropagate(0.8) 回溯到 root: root.visits=2
        assert child.visits == 1
        assert root.visits == 2
        assert root.total_reward == pytest.approx(0.6 + 0.8)

    def test_solved_reflection_marks_tree(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        # 已解决的子节点会把父链标记为 solved
        child = LATSTreeNode(
            messages=[AIMessage(content="a")],
            reflection=make_reflection(9.0, found_solution=True),
            parent=root,
        )
        assert child.is_solved is True
        assert root.is_solved is True

    def test_ucb_unvisited_is_inf_and_root_raises(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        with pytest.raises(ValueError):
            root.upper_confidence_bound()
        child = LATSTreeNode(messages=[AIMessage(content="a")], reflection=make_reflection(7.0), parent=root)
        # 手动制造未访问状态
        child.visits = 0
        assert child.upper_confidence_bound() == float("inf")

    def test_ucb_formula(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        child = LATSTreeNode(messages=[AIMessage(content="a")], reflection=make_reflection(7.0, confidence=0.5), parent=root)
        root.children.append(child)
        # root.visits=2 (init 0.6 + child 回溯 0.7), child.visits=1, avg=0.7
        ucb = child.upper_confidence_bound(exploration_weight=1.414)
        expected = 0.7 + 1.414 * math.sqrt(math.log(root.visits) / child.visits) + 0.5 * 0.1
        assert ucb == pytest.approx(expected)

    def test_best_child_prefers_solved(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        low = LATSTreeNode(messages=[AIMessage(content="lo")], reflection=make_reflection(9.0), parent=root)
        solved = LATSTreeNode(
            messages=[AIMessage(content="hi")],
            reflection=make_reflection(5.0, found_solution=True), parent=root,
        )
        # 避免 solved 的 _mark_tree 影响 low 的判定:children 手动构建
        root.children = [low, solved]
        # solved 加 100 权重应胜出, 即便其 avg_reward 更低
        assert root.best_child is solved

    def test_best_child_none_when_no_children(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        assert root.best_child is None

    def test_height_and_tree_size(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        c1 = LATSTreeNode(messages=[AIMessage(content="c1")], reflection=make_reflection(6.0), parent=root)
        c2 = LATSTreeNode(messages=[AIMessage(content="c2")], reflection=make_reflection(6.0), parent=c1)
        root.children = [c1]
        c1.children = [c2]
        assert root.height == 3
        assert root.tree_size == 3
        assert c2.height == 1

    def test_get_trajectory_root_to_leaf(self):
        root = LATSTreeNode(messages=[HumanMessage(content="root")], reflection=make_reflection(6.0))
        child = LATSTreeNode(messages=[AIMessage(content="child")], reflection=make_reflection(7.0), parent=root)
        root.children.append(child)
        traj = child.get_trajectory(include_reflections=False)
        # 从根到叶: root.messages + child.messages
        contents = [m.content for m in traj]
        assert contents == ["root", "child"]

    def test_get_messages_with_reflection(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        msgs = root.get_messages(include_reflections=True)
        # 追加了 reflection.as_message()
        assert len(msgs) == 2
        assert isinstance(msgs[-1], HumanMessage)
        # 不含反思时返回副本
        plain = root.get_messages(include_reflections=False)
        assert len(plain) == 1

    def test_get_all_descendants_bfs(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        a = LATSTreeNode(messages=[AIMessage(content="a")], reflection=make_reflection(6.0), parent=root)
        b = LATSTreeNode(messages=[AIMessage(content="b")], reflection=make_reflection(6.0), parent=a)
        root.children = [a]
        a.children = [b]
        desc = root.get_all_descendants()
        assert set(id(n) for n in desc) == {id(a), id(b)}

    def test_get_best_solution_node_picks_terminal_solved(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        # 终端已解决, 评分较低
        sol1 = LATSTreeNode(messages=[AIMessage(content="s1")],
                            reflection=make_reflection(8.0, found_solution=True), parent=root)
        sol2 = LATSTreeNode(messages=[AIMessage(content="s2")],
                            reflection=make_reflection(9.0, found_solution=True), parent=root)
        root.children = [sol1, sol2]
        best = root.get_best_solution_node()
        # 综合评分(overall*10)更高的 sol2 胜出
        assert best is sol2

    def test_get_best_solution_node_none_when_no_solution(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        child = LATSTreeNode(messages=[AIMessage(content="c")], reflection=make_reflection(6.0), parent=root)
        root.children = [child]
        # root 终端但未 solved -> None
        assert root.get_best_solution_node() is None

    def test_prune_low_quality_children(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        good = LATSTreeNode(messages=[AIMessage(content="g")], reflection=make_reflection(8.0), parent=root)
        bad = LATSTreeNode(messages=[AIMessage(content="b")], reflection=make_reflection(1.0), parent=root)
        # 强制 average_reward 反映质量
        good.average_reward = 0.8
        bad.average_reward = 0.1
        root.children = [good, bad]
        pruned = root.prune_low_quality_children(threshold=0.3)
        assert pruned == 1
        assert root.children == [good]

    def test_prune_keeps_solved_even_if_low(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        solved_low = LATSTreeNode(messages=[AIMessage(content="s")],
                                  reflection=make_reflection(5.0, found_solution=True), parent=root)
        solved_low.average_reward = 0.05
        root.children = [solved_low]
        pruned = root.prune_low_quality_children(threshold=0.3)
        # 已解决节点豁免剪枝
        assert pruned == 0
        assert solved_low in root.children


# ============================ should_continue 决策 ============================
class TestShouldContinue:
    def _node(self):
        return LatsAgentNode()

    def _state(self, root, search_config=None, start=None):
        import time
        return {
            "root": root,
            "search_config": search_config or LATSConfig(),
            "search_start_time": start if start is not None else time.time(),
        }

    def test_solved_root_goes_final(self):
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        root._is_solved = True
        assert self._node().should_continue(self._state(root)) == "generate_final_answer"

    def test_max_depth_goes_final(self):
        cfg = LATSConfig(max_tree_depth=2)
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        c1 = LATSTreeNode(messages=[AIMessage(content="c")], reflection=make_reflection(6.0), parent=root)
        root.children = [c1]
        # root.height == 2 >= max_tree_depth 2
        assert self._node().should_continue(self._state(root, cfg)) == "generate_final_answer"

    def test_max_time_goes_final(self):
        cfg = LATSConfig(max_search_time=0.0, max_tree_depth=99)
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        # 时间已超 -> final
        st = self._state(root, cfg, start=0.0)
        assert self._node().should_continue(st) == "generate_final_answer"

    def test_low_quality_early_stop(self):
        import time
        cfg = LATSConfig(max_tree_depth=99, max_search_time=9999)
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(3.0))
        c1 = LATSTreeNode(messages=[AIMessage(content="c")], reflection=make_reflection(3.0), parent=root)
        root.children = [c1]
        # height==2, best_score 3.0<5.0 -> 提前结束
        st = {"root": root, "search_config": cfg, "search_start_time": time.time()}
        assert self._node().should_continue(st) == "generate_final_answer"

    def test_continue_expand(self):
        import time
        cfg = LATSConfig(max_tree_depth=99, max_search_time=9999)
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(7.0))
        st = {"root": root, "search_config": cfg, "search_start_time": time.time()}
        # 未解决/未超深/未超时/质量足够 -> 继续扩展
        assert self._node().should_continue(st) == "expand"


# ============================ select_node_for_expansion ============================
class TestSelectNode:
    def test_returns_root_when_no_children(self):
        node = LatsAgentNode()
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        assert node.select_node_for_expansion(root, LATSConfig()) is root

    def test_descends_when_fully_expanded(self):
        node = LatsAgentNode()
        cfg = LATSConfig(max_tree_depth=5, max_candidates=3)
        root = LATSTreeNode(messages=[HumanMessage(content="q")], reflection=make_reflection(6.0))
        # 构造 5+ 子节点使 root 视为 fully_expanded, 且 root.visits>=3
        children = []
        for i in range(5):
            c = LATSTreeNode(messages=[AIMessage(content=f"c{i}")],
                             reflection=make_reflection(6.0 + i * 0.1, confidence=0.5), parent=root)
            children.append(c)
        root.children = children
        # root.visits 已因子节点回溯 >=3; should_expand 为 False 且 fully_expanded -> 下钻
        selected = node.select_node_for_expansion(root, cfg)
        # 选中的是某个子节点(UCB 最高), 至少不是 root 本身
        assert selected in children


# ============================ 异步评估(注入伪 parser) ============================
class TestAsyncEvaluation:
    def _node_with_parser(self, reflection):
        node = LatsAgentNode()
        parser = AsyncMock()
        # parse_with_structured_output 被调用两次(评估标准 + 评估), 返回不同类型
        node.structured_output_parser = parser
        return node, parser

    def test_evaluate_candidate_marks_solution_above_threshold(self):
        node = LatsAgentNode()
        parser = AsyncMock()
        # 第一次返回评估标准(任意有 .criteria 的对象), 第二次返回 reflection
        criteria = type("C", (), {"criteria": "准确性"})()
        reflection = make_reflection(9.0)  # > solution_threshold 8.0
        parser.parse_with_structured_output = AsyncMock(side_effect=[criteria, reflection])
        node.structured_output_parser = parser

        cfg = LATSConfig()
        result = asyncio.run(node._evaluate_candidate(
            "用户问题", [AIMessage(content="候选回答")], {}, cfg))
        assert result.overall_score == 9.0
        # 超过 solution_threshold -> found_solution 被置 True
        assert result.found_solution is True
        assert result.needs_tools is False
        # parser 被调用了两次(标准 + 评估)
        assert parser.parse_with_structured_output.await_count == 2
        # 第二次调用的 pydantic_class 契约为 MultiDimensionalReflection
        second_call = parser.parse_with_structured_output.await_args_list[1]
        assert second_call.kwargs["pydantic_class"] is MultiDimensionalReflection

    def test_evaluate_candidate_falls_back_on_parser_error(self):
        node = LatsAgentNode()
        parser = AsyncMock()
        # 两次调用都失败 -> 走最外层 except 返回默认评估(6.0)
        parser.parse_with_structured_output = AsyncMock(side_effect=RuntimeError("llm down"))
        node.structured_output_parser = parser
        result = asyncio.run(node._evaluate_candidate(
            "问题", [AIMessage(content="ans")], {}, LATSConfig()))
        # 注意: 标准获取失败被内层 try 吞掉用默认标准, 评估调用失败被外层捕获 -> create_default(6.0)
        assert result.overall_score == 6.0

    def test_process_candidates_early_stop_and_fallback(self):
        node = LatsAgentNode()
        cfg = LATSConfig(early_stop_threshold=9.0)

        calls = {"n": 0}

        async def fake_eval(user_input, messages, config, search_config):
            calls["n"] += 1
            # 第一个候选评估抛错 -> 降级 default(4.0); 第二个返回高分触发早停
            if calls["n"] == 1:
                raise RuntimeError("eval fail")
            return make_reflection(9.5)

        node._evaluate_candidate = fake_eval
        candidates = [AIMessage(content="c1"), AIMessage(content="c2")]
        msg_lists, reflections = asyncio.run(
            node._process_candidates_with_evaluation(candidates, "问题", {}, cfg))

        assert len(reflections) == 2
        # 失败候选降级为 create_default(4.0)
        assert reflections[0].overall_score == 4.0
        # 高分候选(9.5 >= 9.0 早停阈值) -> found_solution 被置 True
        assert reflections[1].found_solution is True
        # 每个候选包成单消息列表
        assert msg_lists == [[candidates[0]], [candidates[1]]]


# ============================ 配置/枚举 健全性 ============================
class TestConfigDefaults:
    def test_lats_config_defaults(self):
        cfg = LATSConfig()
        assert cfg.max_candidates == 3
        assert cfg.max_tree_depth == 3
        assert cfg.solution_threshold == 8.0
        assert cfg.early_stop_threshold == 9.0
        assert cfg.enable_pruning is True

    def test_search_phase_enum(self):
        assert SearchPhase.INITIALIZATION.value == "initialization"
        assert SearchPhase.COMPLETED.value == "completed"
