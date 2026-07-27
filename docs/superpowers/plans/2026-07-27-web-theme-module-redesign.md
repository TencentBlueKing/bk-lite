# Web 系统主题模块重构实施计划

## 交付目标

在不修改 Server、不改变现有 Light/Dark 视觉的前提下，将 Control Console 主题行为收口到 `web/src/theme`，建立类型化语义 Token、CSS/AntD Adapter、首帧初始化和稳定 React 接口。

## 实施顺序

### 1. 建立可验证的主题契约

- 从 `web/src/styles/globals.css` 盘点 Light/Dark 变量和值。
- 建立 `ThemeMode`、完整语义 Token、主题元数据和解析后主题类型。
- 将当前 Light/Dark 值迁入 TypeScript 默认主题。
- 增加完整性测试，确保两套模式具有相同字段且能生成所有兼容变量。

### 2. 建立纯函数 Adapter

- 实现默认主题与覆盖项合并。
- 实现语义 Token 到规范 CSS Variables、旧变量别名的映射。
- 实现语义 Token 到 Ant Design `ThemeConfig` 的映射。
- 将纯函数作为主要测试接缝，不在测试中依赖 React 或浏览器。

### 3. 接入首帧主题

- 在根布局 `<head>` 输出内置默认主题的 Light/Dark CSS。
- 增加首帧前初始化脚本，仅读取合法的 `localStorage.theme`。
- 在 hydration 前设置 `<html>` 的 `.dark` class 与 `color-scheme`。
- 删除 `globals.css` 中手工维护的 Light/Dark 颜色真值，保留非主题结构样式。

### 4. 重构 React Provider

- 建立 `useThemeMode()` 与 `useThemeTokens()`。
- Provider 统一负责模式状态、存储、DOM 应用和 AntD ThemeConfig。
- 将 AntD locale/dayjs locale 责任移到独立的 locale 配置层。
- 保留临时兼容导出仅用于一次迁移；迁移完成后删除旧 Context。

### 5. 迁移业务调用

- 主题开关改用 `useThemeMode()`，删除重复实现。
- `themeName` 消费者迁移为 `mode`。
- 图表、拓扑和 Canvas 迁移到 `useThemeTokens()` 或显式模式参数。
- 清除主题模块外的 localStorage 和 `.dark` 直接访问。
- 更新 Storybook 唯一主题切换契约到根壳实现。

### 6. 增加治理门禁

- 增加主题契约测试脚本。
- 增加架构扫描，禁止主题模块外直接访问主题存储、DOM 模式和内部配置。
- 将定向测试命令登记到 `web/package.json`。

### 7. 新鲜验证

- 运行主题定向测试和 ESLint。
- 运行 `pnpm type-check`。
- 运行组件所有权 audit/check。
- 运行可行的 Storybook 定向或构建验证；遇到既有基线错误保留原始证据。
- 检查 git diff，确保不包含现有无关工作区改动。

## 回滚

本次没有数据库变化。代码回滚时恢复原 ThemeProvider、AntD 配置和 `globals.css` 主题块即可；现有 `localStorage.theme=light|dark` 数据格式保持不变，无需迁移或清理。
