# Design Docs —— 设计文档索引

> 「为什么这样设计」的归档处。每个重要的、不可从代码直接推断的设计决策都应在此留痕。

## 全局
- [core-beliefs.md](core-beliefs.md) —— 工程信条(最小变更、证据优先、渐进式设计……)
- [learnings.md](learnings.md) —— 经验与决策记录(认证 Cookie 处理……)

## 模块级设计(现存,分布在各模块就近维护)
| 主题 | 位置 |
|------|------|
| 前端视觉/组件 token | [web/DESIGN.md](../../web/DESIGN.md) |
| 算法服务设计原则 | [algorithms/DESIGN_GUIDE.md](../../algorithms/DESIGN_GUIDE.md) |
| UI 设计规范(产品侧) | [spec/design_ui.md](../../spec/design_ui.md) |
| 单点登录(SSO/NATS)接入 | [docs/readme.md](../readme.md) |

## 技术评审归档
进行中/历史的技术评审在 [docs/reviews/](../reviews/)(如日志权限链评审、监控对象上线评审)。

## 决策记录(ADR)约定
重大决策按以下骨架新增 `docs/design-docs/adr-<编号>-<短标题>.md`:

```markdown
# ADR-001: <决策标题>
- 状态: 提议 / 采纳 / 废弃 / 被取代(指向新 ADR)
- 日期: YYYY-MM-DD
## 背景
## 决策
## 取舍与备选方案
## 影响
```

> 规格(spec)与执行计划不放这里 —— 那是 [openspec/](../../openspec/) 与 [PLANS.md](../../PLANS.md) 的职责。本目录只放「设计意图与决策」。
