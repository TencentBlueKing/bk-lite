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
