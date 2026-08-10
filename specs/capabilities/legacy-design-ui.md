# Web 前端 UI 设计规范

> Migrated from `spec/design_ui.md` as legacy capability evidence.

---
applyTo: 'web/src/**/*.{tsx,jsx}'
---

本文档定义 BK-Lite Web 前端的 UI 设计约束，确保各模块视觉风格统一。后续新增或修改页面组件时，请遵循以下准则。

## 1. 卡片（Card）

### 1.1 标准卡片样式

所有列表页的卡片必须使用统一的视觉基础属性：

| 属性 | 值 | 说明 |
|------|-----|------|
| 圆角 | `rounded-xl`（12px） | 禁止使用更大圆角（如 `rounded-[26px]`） |
| 阴影 | `shadow-md` | 禁止使用自定义 `boxShadow` inline style |
| 背景色 | `bg-(--color-bg)` | 跟随主题自动切换，禁止硬编码 `#ffffff` 或 rgba |
| 边框 | 默认无边框 | 如需边框使用 `border-(--color-border-2)` |
| hover | `hover:-translate-y-0.5 transition-all` | 可选，提供微妙上浮反馈 |
| 指针 | `cursor-pointer`（可点击时） | — |
| 溢出 | `overflow-hidden` | 防止子元素溢出圆角 |

标准卡片 class 组合：
```
rounded-xl shadow-md bg-(--color-bg) cursor-pointer overflow-hidden
```

### 1.2 卡片容器实现

优先使用纯 `<div>` + Tailwind 实现卡片容器，而非 Ant Design `<Card>`。原因：
- 避免覆盖 Ant Card 默认样式（`bodyStyle={{ padding: 0 }}`）
- 代码更简洁，样式更可控

```tsx
// ✅ 推荐
<div className="rounded-xl shadow-md bg-(--color-bg) cursor-pointer overflow-hidden p-4">
  {/* content */}
</div>

// ❌ 避免
<Card hoverable bodyStyle={{ padding: 0 }} style={{ background: '...', boxShadow: '...' }}>
  {/* content */}
</Card>
```

### 1.3 卡片装饰元素

允许在卡片内部添加**轻量装饰**（如顶部渐变蒙层），但必须满足：
- 使用 `pointer-events-none` + `absolute` 定位，不影响交互
- 暗色/亮色主题均有对应处理
- 不使用 `blur-3xl` 等重型模糊效果

```tsx
// ✅ 允许：轻量渐变蒙层
<div
  className="pointer-events-none absolute inset-x-0 top-0 h-22"
  style={{
    background: isDark
      ? 'linear-gradient(180deg, rgba(21, 90, 239, 0.14) 0%, transparent 100%)'
      : 'linear-gradient(180deg, rgba(239, 246, 255, 0.95) 0%, transparent 100%)',
  }}
/>
```

### 1.4 卡片网格布局

列表页卡片统一使用 CSS Grid 响应式布局：

```
grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5
```

间距统一 `gap-4`。不同页面可根据内容宽度微调断点列数，但必须使用上述响应式模式。

### 1.5 卡片内元素规范

| 元素 | 规范 |
|------|------|
| 图标容器 | `rounded-xl bg-(--color-fill-1)`，无边框 |
| 标题 | `text-sm font-semibold text-(--color-text-1)`，单行 `truncate` |
| 描述 | `text-xs text-(--color-text-3)`，`line-clamp-1` 或 `line-clamp-3` |
| 分割线 | `border-t border-(--color-border-2)`，禁止渐变分割线 |
| 底部信息 | `text-xs text-(--color-text-2)` 或 `text-(--color-text-4)` |
| 操作按钮 | hover 时显示（`opacity-0 group-hover:opacity-100`） |

## 2. 样式方法论

### 2.1 样式优先级

1. **Tailwind 类名**（首选）
2. **CSS 变量**（主题相关色值，如 `text-(--color-text-1)`）
3. **SCSS Module**（复杂选择器或 Ant 组件样式覆盖）
4. **inline style**（仅限动态计算值或渐变等 Tailwind 无法表达的场景）

### 2.2 禁止事项

- ❌ 硬编码颜色值（`#ffffff`、`rgba(12, 37, 54, 0.96)`）用于背景/文字/边框
- ❌ inline style 定义 `boxShadow`、`border`、`background`（渐变装饰除外）
- ❌ 组件间样式不一致（同类页面的同类元素必须使用相同样式模式）

### 2.3 主题适配

所有颜色必须通过 CSS 变量引用，确保亮色/暗色主题自动切换：

| 用途 | 变量 |
|------|------|
| 主背景 | `--color-bg` |
| 次背景 | `--color-bg-1` |
| 填充色 | `--color-fill-1` |
| 主文字 | `--color-text-1` |
| 次文字 | `--color-text-2`、`--color-text-3` |
| 辅助文字 | `--color-text-4` |
| 边框 | `--color-border-1`、`--color-border-2` |
| 主题色 | `--color-primary` |

## 3. 骨架屏（Skeleton）

骨架屏的容器样式必须与对应的实际卡片保持一致（圆角、边框、背景），确保加载态到渲染态的视觉平滑过渡。

## 4. 参考实现

| 页面 | 文件 | 说明 |
|------|------|------|
| 知识库 | `src/app/opspilot/(pages)/knowledge/page.tsx` | 纯 div 卡片，标准布局 |
| 工作台 | `src/app/opspilot/components/entity-card/index.tsx` | Ant Card + CommonCard SCSS |
| 模型供应商 | `src/app/opspilot/components/provider/vendorCardGrid.tsx` | 纯 div + 渐变装饰 |
