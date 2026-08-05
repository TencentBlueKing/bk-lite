# Web 构建进度、性能与类型校验修复

状态：已实现并通过生产构建验证

## 背景

`pnpm build` 原有三个问题：

1. `package.json` 和 `next.config.mjs` 都执行资产准备，而 Next 16.3 的 Turbopack 主进程与 Worker 会重复加载配置，导致企业资源准备和复制日志重复出现。
2. Next 在长时间编译与类型检查期间没有新日志，无法区分仍在构建和进程卡住。
3. 生产构建被 12 个 Monitor TypeScript 错误阻塞，涉及 React 19.2 `Key` 的 `bigint` 分支、动态配置的 `unknown`、插件 ID 类型和 dashboard 配置返回类型。

性能调查还确认：原 `outputFileTracingRoot` 超出了 `bk-lite` 仓库；生产类型检查包含 Storybook、测试、E2E 与开发期生成类型等非生产输入。

## 目标

- 每次生产构建只准备一次企业模块、locale、menu 和 public 资产。
- `next.config.mjs` 保持无文件写入的纯配置模块。
- 构建静默时每 10 秒输出阶段、已用时间和仍在运行状态。
- 将 Turbopack 与输出追踪根目录限制在 `bk-lite` 仓库。
- 生产构建只检查会进入产物的 TypeScript 源码，不启用 `ignoreBuildErrors`。
- 修复 12 个 Monitor 类型错误，使完整 `pnpm type-check` 和 `pnpm build` 都退出 0。
- 保留 Next 原始输出、退出码与中断语义；任一资源准备步骤或编译失败时构建必须失败。

## 方案

### 单一构建入口

构建编排脚本顺序执行：

1. 调用一次资产准备函数。
2. 准备成功后启动本地 Next CLI，默认使用 `build --turbopack`。
3. 子进程运行期间每 10 秒输出一次已用时间。
4. 子进程结束后清理计时器和信号监听，传播原始非零退出码或信号。

`build` 和 `analyze` 共用该入口；开发命令继续使用现有 `prepare-enterprise` 行为。

### 资产准备边界

无导入副作用的准备模块集中调用：

- `prepareEnterpriseRoutes()`
- `combineLocales()`
- `combineMenus()`
- `copyPublicDirectories()`

`next.config.mjs` 不再包含这些模块的导入或顶层 `await`。locale、menu 或 public 资产读取/复制失败时记录原始错误并重新抛出，禁止生成部分资产后继续构建。

### 构建范围与进度

- `outputFileTracingRoot` 和 Turbopack root 使用 Web 与 Enterprise 的共同仓库根 `bk-lite/`。
- `tsconfig.build.json` 继承现有严格度、路径别名和 Next 插件，包含生产 `src/` 与 `.next/types/`，排除 Storybook、测试、E2E、脚本和 `.next/dev/types/`。
- 心跳只报告真实阶段和已用时间，不伪造完成百分比。

### Monitor 类型契约

- 策略页插件 ID 的真实类型为 `string | number`，`SegmentedItem.value` 与采集模板切换回调统一使用该类型。
- 插件缓存接受 `React.Key | null | undefined`，在单一入口通过 `String()` 归一化缓存键。
- 动态配置边界声明明确的对象配置、手动插件配置和 dashboard 展示项类型，不向调用方暴露 `unknown`。
- 手动插件默认配置必须提供 `formItems`、`defaultForm`、`getParams` 和 `getConfigText` 的安全空实现。
- dashboard 配置兼容标准对象和 Kafka 历史字符串指标名；字符串在边界转换为 `{ indexId, displayDimension: [] }`。

## 测试与验证

回归测试覆盖：

- 导入 `next.config.mjs` 不触发资源准备或文件写入。
- 单一构建入口只准备一次资源。
- 10 秒心跳、成功退出、非零退出和信号传播。
- locale、menu 或 public 资产错误会中止构建。
- 构建根目录、生产 TypeScript 输入范围与 Enterprise 路径关系。
- dashboard 历史字符串归一化、标准对象保持不变、手动模式默认配置字段完整。
- 快速生产 TypeScript 门禁、完整 `pnpm type-check` 和真实 `pnpm build`。

## 非目标

- 不跳过生产源码的 TypeScript 检查。
- 不伪造构建百分比。
- 不修改 Next、Turbopack 或 TypeScript 依赖版本。
- 除上述类型契约外，不改变应用行为、路由内容或资产覆盖规则。
- 不借本次优化清理其他工作区改动。

## 验证结果（2026-08-05）

- 构建管线与 Monitor 配置契约测试全部通过。
- 本次涉及文件 ESLint 检查为 0 错误；全仓 lint 仍被 `.history/` 和任务外工作区文件的既有错误阻塞。
- 快速生产 TypeScript 门禁退出 0，原有 12 个 Monitor 类型错误全部消除；完整 `pnpm type-check` 退出 0。
- 清理缓存后的真实 `pnpm build` 退出 0，总耗时 8 分 31 秒。
- 最终代码在暖缓存下再次执行真实 `pnpm build`，退出 0，总耗时 1 分 24 秒：资源准备 2.8 秒、Turbopack 编译 28.1 秒、TypeScript 23.5 秒、静态生成 200 个页面耗时 16.6 秒。
