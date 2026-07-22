# DESIGN.md

> 设计的总入口。本文只做导航；稳定原则进入 capability，跨会话设计进入 change spec，避免多份文档漂移。

## 设计真相源在哪

| 你要找的 | 去这里 |
|----------|--------|
| 颜色 / 圆角 / 间距 / 排版 / 基础组件 token | [web/DESIGN.md](web/DESIGN.md)(唯一真相源) |
| 前端工程约定(栈/包管理/i18n/门禁) | [前端工程规则](specs/capabilities/frontend-engineering.md) |
| 产品侧 UI / 交互规范 | [specs/capabilities/legacy-design-ui.md](specs/capabilities/legacy-design-ui.md) |
| 算法服务设计原则 | [algorithms/DESIGN_GUIDE.md](algorithms/DESIGN_GUIDE.md) |
| 产品与工程原则 | [PRODUCT.md](PRODUCT.md) · [能力规格](specs/capabilities/) |
| 设计决策 / ADR 归档 | [docs/adr/](docs/adr/) |
| 系统结构与模块边界 | [系统架构](specs/capabilities/engineering-architecture.md) |

## 改设计前的三条规矩

1. **token 不硬编码**:前端任何颜色/圆角/间距取自 `web/DESIGN.md`,改设计先改 token。
2. **决策要留痕**:跨会话设计写入 `specs/changes/<feature>/spec.md`；长期且难回滚的决定才写 ADR。
3. **一致性优先**:复用既有组件与规范，新范式需符合 [产品原则](PRODUCT.md)。
