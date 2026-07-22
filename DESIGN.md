# DESIGN.md

> 设计的「总入口」。本文不放具体 token / 规则,只做导航 —— 各设计真相源就近维护,避免漂移(见 [core-beliefs §5](docs/design-docs/core-beliefs.md))。

## 设计真相源在哪

| 你要找的 | 去这里 |
|----------|--------|
| 颜色 / 圆角 / 间距 / 排版 / 基础组件 token | [web/DESIGN.md](web/DESIGN.md)(唯一真相源) |
| 前端工程约定(栈/包管理/i18n/门禁) | [前端工程规则](docs/engineering/frontend.md) |
| 产品侧 UI / 交互规范 | [specs/capabilities/legacy-design-ui.md](specs/capabilities/legacy-design-ui.md) |
| 算法服务设计原则 | [algorithms/DESIGN_GUIDE.md](algorithms/DESIGN_GUIDE.md) |
| 工程信条(为什么这样设计) | [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md) |
| 设计决策 / ADR 归档 | [docs/design-docs/index.md](docs/design-docs/index.md) |
| 系统结构与模块边界 | [系统架构](docs/engineering/architecture.md) |

## 改设计前的三条规矩

1. **token 不硬编码**:前端任何颜色/圆角/间距取自 `web/DESIGN.md`,改设计先改 token。
2. **决策要留痕**:非显而易见的设计选择写进 `docs/design-docs/`(必要时建 ADR)。
3. **一致性优先**:复用既有组件与规范，新范式需符合 [产品原则](PRODUCT.md)。
