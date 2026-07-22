# 2026 06 05 Provider Card Style Unify

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-provider-card-style-unify/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

模型供应商页面（`/opspilot/provider`）的卡片使用了独立设计的视觉风格——26px 超大圆角、蓝色渐变背景、模糊光晕装饰、大阴影，与工作台（EntityCard）和知识库等页面的标准卡片风格（12px 圆角、`shadow-md`、纯色背景、CSS 变量）严重不一致，影响产品的视觉统一性。

## What Changes

- 将 `VendorCardGrid` 卡片的圆角从 `rounded-[26px]` 改为 `rounded-xl`（12px），与全局保持一致
- 移除蓝色渐变背景、顶部渐变蒙层、模糊光晕等装饰性元素
- 将背景色改为 `var(--color-bg)`，阴影改为 `shadow-md`
- 移除蓝色边框，与知识库/工作台卡片无边框风格一致
- 将大量 inline style 替换为 Tailwind + CSS 变量，遵循项目现有模式
- 保留卡片的功能性内容：供应商图标、名称、类型 Tag、模型数量、启用开关、编辑/删除操作

## Capabilities

### New Capabilities

- `provider-card-restyle`: 重新设计模型供应商卡片样式，使其与工作台/知识库卡片风格保持一致

### Modified Capabilities

（无已有 spec 需要修改）

## Impact

- `web/src/app/opspilot/components/provider/vendorCardGrid.tsx`：主要改动文件，重写卡片样式
- `web/src/app/opspilot/components/provider/skeleton.tsx`：骨架屏需同步调整圆角和布局
- 暗色主题需验证：移除 inline 渐变后确保 `var(--color-bg)` 在暗色模式下表现正常

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-22
```

## Capability Deltas

### provider-card-restyle

## ADDED Requirements

### Requirement: 供应商卡片视觉风格与全局一致
供应商卡片 SHALL 使用与知识库/工作台卡片相同的视觉基础属性：`rounded-xl` 圆角、`shadow-md` 阴影、`var(--color-bg)` 背景色，不使用渐变装饰或硬编码颜色值。

#### Scenario: 亮色主题下卡片外观
- **WHEN** 用户在亮色主题下查看模型供应商页面
- **THEN** 卡片 SHALL 显示为白色背景（`var(--color-bg)`）、12px 圆角、标准阴影，无蓝色渐变或光晕装饰

#### Scenario: 暗色主题下卡片外观
- **WHEN** 用户在暗色主题下查看模型供应商页面
- **THEN** 卡片 SHALL 使用 `var(--color-bg)` 自动适配暗色背景，无硬编码的 rgba 渐变色

### Requirement: 供应商卡片功能内容完整保留
卡片 SHALL 保留所有现有功能元素：供应商图标、名称、类型 Tag、描述文本、模型数量、启用/禁用开关、hover 时的编辑/删除操作按钮。

#### Scenario: 卡片内容展示
- **WHEN** 供应商卡片渲染完成
- **THEN** SHALL 显示供应商图标、名称、类型标签、模型数量和启用开关

#### Scenario: hover 操作按钮
- **WHEN** 用户 hover 到卡片上
- **THEN** SHALL 在卡片右上角显示编辑和删除操作按钮

### Requirement: 骨架屏与卡片风格一致
加载骨架屏 SHALL 使用与卡片相同的圆角和布局，确保加载态到渲染态的视觉平滑过渡。

#### Scenario: 骨架屏圆角
- **WHEN** 供应商列表处于加载状态
- **THEN** 骨架屏卡片 SHALL 使用 `rounded-xl` 圆角，与实际卡片一致

### Requirement: 样式实现使用 Tailwind + CSS 变量
卡片样式 SHALL 使用 Tailwind 类名和 CSS 变量实现，不使用 inline style 定义背景色、阴影、边框等视觉属性。

#### Scenario: 无 inline style 硬编码
- **WHEN** 审查 VendorCardGrid 组件代码
- **THEN** 卡片容器 SHALL 不包含 `background: linear-gradient(...)` 或 `boxShadow: '0 14px ...'` 等 inline style

## Work Checklist

## 1. 重写卡片容器样式

- [x] 1.1 将 `VendorCardGrid` 中的 Ant `<Card>` 替换为纯 `<div>`，使用 `rounded-xl shadow-md bg-(--color-bg) cursor-pointer` 基础样式
- [x] 1.2 移除所有卡片容器的 inline style（渐变 background、boxShadow、border 的硬编码值）
- [x] 1.3 移除卡片内部的蓝色渐变蒙层（`h-22` 渐变 div）和模糊光晕装饰（`blur-3xl` div）
- [x] 1.4 保留 `hover:-translate-y-0.5 transition-all` 微妙上浮效果

## 2. 调整内容元素样式

- [x] 2.1 将供应商图标容器的 inline style（渐变背景、蓝色边框）替换为 Tailwind + CSS 变量（`bg-(--color-fill-1) border-(--color-border-2)`）
- [x] 2.2 将底部分割线从渐变 `bg-[linear-gradient(...)]` 改为简单的 `border-t border-(--color-border-2)`
- [x] 2.3 将 Tag 的 inline style（borderColor、background、color）移除，直接使用 Ant Tag `color="blue"` 默认样式

## 3. 同步骨架屏

- [x] 3.1 将 `ProviderGridSkeleton` 的卡片容器圆角从 `rounded-lg` 改为 `rounded-xl`，与实际卡片一致

## 4. 验证

- [x] 4.1 亮色主题下查看供应商页面，确认卡片风格与知识库页面一致
- [x] 4.2 暗色主题下查看供应商页面，确认背景/文字/边框正常
- [x] 4.3 `pnpm type-check && pnpm lint` 通过
