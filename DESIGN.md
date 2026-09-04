# DESIGN.md

> 设计的总入口。本文只做导航；稳定原则进入 capability，跨会话设计进入 change spec，避免多份文档漂移。

## 设计真相源在哪

| 你要找的 | 去这里 |
|----------|--------|
| 颜色 / 圆角 / 间距 / 排版 / 基础组件 token / 布局样式写法 | [web/DESIGN.md](web/DESIGN.md)（唯一真相源）。气质：**浅色、克制的企业控制台**，见该文 Overview |
| Web 组件所有权与治理执行 | [web/COMPONENT_GOVERNANCE.md](web/COMPONENT_GOVERNANCE.md) |
| 前端工程约定(栈/包管理/i18n/门禁) | [前端工程规则](specs/capabilities/frontend-engineering.md) |
| 产品侧 UI / 交互规范 | [specs/capabilities/legacy-design-ui.md](specs/capabilities/legacy-design-ui.md) |
| 算法服务设计原则 | [algorithms/DESIGN_GUIDE.md](algorithms/DESIGN_GUIDE.md) |
| 产品与工程原则 | [PRODUCT.md](PRODUCT.md) · [能力规格](specs/capabilities/) |
| 设计决策 / ADR 归档 | [docs/adr/](docs/adr/) |
| 系统结构与模块边界 | [系统架构](specs/capabilities/engineering-architecture.md) |
| OpsPilot 页面内容对话（其它 app 把当前页接到悬浮机器人） | 按 [对接规范](specs/changes/webchat-page-context/app-integration.md) 开发，不要改业务页展示、不要改 GlobalWebchat / 后端注入。参考实现：[监控仪表盘 pilot](web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts) · 产品说明 [spec.md](specs/changes/webchat-page-context/spec.md) |

## OpsPilot 页面内容对话（给 Agent）

开发或评审「悬浮机器人能看见当前页」时，**只读并对齐** [app-integration.md](specs/changes/webchat-page-context/app-integration.md)。不要通读 `web/DESIGN.md`，也不要改监控仪表盘等业务组件。

- 规范：[specs/changes/webchat-page-context/app-integration.md](specs/changes/webchat-page-context/app-integration.md)
- 参考实现（Pilot 旁路、图表截图与按问题收窄）：[web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts](web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts)
- 登记路由：[web/src/components/ai-page-context/pilots.ts](web/src/components/ai-page-context/pilots.ts)

## 改设计前的三条规矩

1. **token 不硬编码**:前端任何颜色取自语义 token（`globals.css` / `web/DESIGN.md`）；布局与间距优先 Tailwind `className`，不以大段行内 `style` 表达。
2. **决策要留痕**:跨会话设计写入 `specs/changes/<feature>/spec.md`；长期且难回滚的决定才写 ADR。
3. **一致性优先**:复用既有组件与规范，新范式需符合 [产品原则](PRODUCT.md)；Web 组件放置与治理见 [COMPONENT_GOVERNANCE.md](web/COMPONENT_GOVERNANCE.md)。
