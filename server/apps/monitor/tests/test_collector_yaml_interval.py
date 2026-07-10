"""锁定 K8s / webhookd collector yaml 的 Telegraf [agent] interval 必须 = "60s" 的回归测试。

业务规则：监控采集频率统一为 60s（见 PR #4044 commit 5be4782774）。
两个 ConfigMap 中的 telegraf.conf 内嵌配置里，[agent] section 的 interval
值如果被改回 10s 或其它高频值，新部署的 collector 会对目标端发起高频采集，
导致拉端/拉后端。该测试锁住 yaml 内 [agent].interval = "60s"。
"""
import re
from pathlib import Path

# pytest 在 server/ 目录运行,test 文件位于 server/apps/monitor/tests/,
# __file__.parents[3] 指向 server/, parents[4] 指向仓库根。
REPO_ROOT = Path(__file__).resolve().parents[4]
EXPECTED_INTERVAL = "60s"

# 每个 yaml 可能包含多个 [agent] section (例如 deploy 这份 collector
# ConfigMap + 同文件中的 webhookd ConfigMap),全部都必须命中。
COLLECTOR_YAML_PATHS = [
    REPO_ROOT / "deploy/dist/bk-lite-kubernetes-collector/bk-lite-metric-collector.yaml",
    REPO_ROOT / "agents/webhookd/bk-lite-metric-collector.yaml",
]

# 匹配 "[agent]" 行之后、紧随其后的 "interval = "60s"" 行。
# yaml 中 [agent] 通常嵌在 literal block (|) 内,前面会有 yaml 缩进;
# 该缩进层级比 interval 的缩进浅 2 格,因此捕获时只关心同 block 内紧邻
# 的下一行配置。
_AGENT_INTERVAL_RE = re.compile(
    r"^\s*\[agent\][^\n]*\n[ \t]+interval[ \t]*=[ \t]*\"([^\"]+)\"",
    re.MULTILINE,
)


def _extract_agent_intervals(yaml_text):
    """提取 yaml 中每个 [agent] section 的 interval 值列表(按出现顺序)。"""
    return _AGENT_INTERVAL_RE.findall(yaml_text)


def test_collector_yaml_files_exist():
    """两个 collector yaml 必须存在;不存在即视为回归(被误删)。"""
    missing = [str(p) for p in COLLECTOR_YAML_PATHS if not p.exists()]
    assert not missing, (
        "以下 collector yaml 缺失,无法守护 [agent] interval 契约:\n"
        + "\n".join(f"  {p}" for p in missing)
    )


def test_collector_yaml_agent_interval_is_60s():
    """每个 collector yaml 的所有 [agent] section 中,interval 必须 = "60s"。"""
    violations = []
    for path in COLLECTOR_YAML_PATHS:
        assert path.exists(), f"yaml 缺失: {path}"
        text = path.read_text(encoding="utf-8")
        intervals = _extract_agent_intervals(text)
        assert intervals, f"{path} 中未找到 [agent] interval 配置"

        for idx, value in enumerate(intervals, start=1):
            if value != EXPECTED_INTERVAL:
                violations.append((str(path), idx, value))

    assert not violations, (
        "以下 [agent] section 的 interval 不为 "
        f"{EXPECTED_INTERVAL!r},违反 60s 采集频率契约:\n"
        + "\n".join(f"  {p} [agent#{i}]: interval = {v!r}" for p, i, v in violations)
    )