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
