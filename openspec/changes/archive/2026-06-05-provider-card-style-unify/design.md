## Context

模型供应商页面卡片（`VendorCardGrid`）使用了独立设计的高装饰风格，与项目中工作台（`EntityCard`）、知识库等页面的标准卡片风格不一致。

当前标准卡片风格特征（知识库/工作台）：
- `rounded-xl`（12px 圆角）
- `shadow-md` 标准阴影
- `var(--color-bg)` 纯色背景
- 无边框或 `var(--color-border)` 主题边框
- Tailwind + CSS 变量，无 inline style

当前供应商卡片问题：
- `rounded-[26px]` 超大圆角
- 蓝色渐变背景 + 模糊光晕装饰
- `0 14px 28px` 超大阴影
- 蓝色硬编码边框
- 大量 inline style（渐变、阴影、边框色）

## Goals / Non-Goals

**Goals:**
- 卡片视觉风格与知识库/工作台保持一致（圆角、阴影、背景、边框）
- 用 Tailwind + CSS 变量替代 inline style，遵循项目模式
- 保留供应商卡片的功能性内容（图标、名称、Tag、模型数、开关、编辑/删除）
- 暗色主题下正常工作（依赖 CSS 变量自动适配）

**Non-Goals:**
- 不改变卡片的交互逻辑（点击跳转、开关启停、编辑删除）
- 不改变 grid 布局列数
- 不引入 EntityCard 组件复用（供应商卡片内容结构与智能体/知识库不同，不适合强行复用）
- 不改动其他页面的卡片

## Decisions

1. **直接修改 VendorCardGrid，不抽取公共组件**
   - 供应商卡片的内容结构（图标+名称+Tag / 模型数+开关）与 EntityCard（Banner图+图标 / 描述+Tag+归属）差异较大
   - 强行抽取公共组件会增加不必要的抽象层。只需统一视觉属性即可

2. **使用纯 div 替代 Ant Design Card**
   - 知识库页面已使用纯 `<div>` + Tailwind 实现卡片，效果良好
   - 减少 Ant Card 的样式覆盖（`bodyStyle={{ padding: 0 }}`），代码更简洁

3. **保留 hover 上浮效果但降低幅度**
   - `hover:-translate-y-0.5` + `transition-shadow` 提供微妙反馈，不会过于突兀
   - 与知识库的纯 cursor-pointer 相比略有差异，但供应商卡片有编辑/删除操作需要 hover 提示

## Risks / Trade-offs

- [样式回归] 移除所有 inline style 后暗色主题可能出现背景色不匹配 → 使用 `var(--color-bg)` 已在知识库/工作台验证过暗色适配
- [视觉降级感] 用户可能觉得卡片变"朴素"了 → 统一性优先，必要时可后续全局升级卡片风格
