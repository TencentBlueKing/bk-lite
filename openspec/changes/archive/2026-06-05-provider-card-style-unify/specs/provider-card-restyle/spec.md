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
