# 01 — 聚合层规则文档与 ADR

Status: done

Blocked by: None（总顺序上排在 `rum-session-end-records`、`apm-policy-merged-queries` 之后）

**What to build:** 运维拿到一份文档，就能独立部署聚合库、配置两个写入进程、接好告警，并按其中的验收清单判定合格；
仓库里的架构决定与长期规范不再写“APM 禁止 VictoriaMetrics / Span Metrics”。

- [x] 新增运维规则文档（`docs/operations/` 下）：部署要求（独立单节点、≥35 天保留、只走内网、可选基础认证）、
      环境变量（`AGG_VICTORIAMETRICS_WRITE_URL`、`AGG_VICTORIAMETRICS_QUERY_URL`、认证变量、`APM_AGG_SHARD`、`RUM_AGG_SHARD`）、
      写入规则（spec「聚合库」一节）、标签禁区、告警（磁盘 70%/85%、序列数异常、remote write 失败/丢弃）、容量参考、
      两个镜像新增组件与稳定性等级、启动不依赖、验收清单（对应 p398_930 验收 1–7）
- [x] 新 ADR（编号顺延）：部分替代 ADR 0006，内容见 spec「架构决定」；ADR 0006 头部注明被部分替代
- [x] 同步长期规范：APM 架构与功能清单 capability、产品决策文档（apm-data-plane、apm-inferred-downstream）中的相关表述；
      基础设施清单 capability 增加聚合库一行
- [x] 文档内链接有效；不改任何代码与部署文件（`deploy/apm` 的验收清单与配置测试在 02 改）

## Notes

- 运维文档面向人，写清“必须满足的硬约束”和“编排自选”的边界，沿用 `deploy/apm` 的“契约硬、编排软”写法。

## Completion evidence

- 新增 `docs/operations/aggregate-metrics-store.md` 与 `docs/adr/0011-apm-rum-aggregate-metrics-store.md`。ADR 0006 只在 Status 下增加一行部分替代说明，正文未改。
- 长期规范改为：入口 RED 与可用性 SLO 允许读独立聚合库；明细、策略、慢请求、Apdex、延迟 SLO、下钻与拓扑仍以 VictoriaTraces 为准。写法标明目标契约见 ADR 0011，落地见聚合层变更，当前尚未部署。
- 未改代码、`deploy/apm`、`deploy/rum` 和 `server/apps/apm/tests/test_data_plane_config.py`。
- 链接检查在仓库根目录执行。扫描本次新增和修改的 8 份文档，去掉代码围栏后提取 Markdown 相对链接和 `[[wiki]]` 链接，按文件所在目录解析。外链忽略。wiki 锚点允许标题以片段开头，用来兼容能力文档标题上的「【已实现】」后缀。结果：`ok=37 broken=0`。

```bash
python3 - << 'PY'
import re
from pathlib import Path
root = Path(".").resolve()
files = [
    "docs/operations/aggregate-metrics-store.md",
    "docs/adr/0011-apm-rum-aggregate-metrics-store.md",
    "docs/adr/0006-apm-regional-nats-victoriatraces-pipeline.md",
    "specs/capabilities/apm-architecture.md",
    "specs/capabilities/apm-function-list.md",
    "specs/capabilities/legacy-ard-modules-infra-deployment.md",
    "docs/design/product-decisions/apm-data-plane.md",
    "docs/design/product-decisions/apm-inferred-downstream.md",
]
link_re = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')
wiki_re = re.compile(r'\[\[([^\]|#]+)(#[^\]]+)?\]\]')
fence = re.compile(r"```.*?```", re.S)

def slug(text):
    text = text.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")

def headings(text):
    return [m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.*)$", text, re.M)]

def heading_ok(fragment, hs):
    want = slug(fragment)
    for h in hs:
        base = re.split(r"[【\[]", h, maxsplit=1)[0].strip()
        if fragment in {h, base} or want in {slug(h), slug(base)} or h.startswith(fragment):
            return True
    return False

broken = ok = 0
for rel in files:
    path = root / rel
    raw = path.read_text()
    body = fence.sub("", raw)
    items = [(m.group(1).strip(), False, m.start()) for m in link_re.finditer(body)]
    items += [(m.group(1).strip() + (m.group(2) or ""), True, m.start()) for m in wiki_re.finditer(body)]
    for url, is_wiki, _start in items:
        if not is_wiki and url.startswith(("http://", "https://", "mailto:", "#")):
            continue
        frag = ""
        target = url
        if is_wiki:
            name, _, frag = url.partition("#")
            dest = (path.parent / name).resolve()
        else:
            if "#" in url:
                target, frag = url.split("#", 1)
            dest = path if target == "" else (path.parent / target).resolve()
        if not dest.exists() or (frag and dest.suffix.lower() in {".md", ".markdown"} and not heading_ok(frag, headings(dest.read_text()))):
            broken += 1
            print("BROKEN", rel, url)
        else:
            ok += 1
print(f"ok={ok} broken={broken}")
PY
```
