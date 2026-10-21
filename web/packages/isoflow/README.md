# @bk-lite/isoflow

运营分析架构图使用的 Isoflow 内部包。Next 只消费本包 `webpack + tsc` 产出的 `dist/`，不直接编译 `src/`。

## 来源

- npm 包：`x-isoflow-react-19@1.1.1`
- gitHead：`0dd5948c72f2611ded0a15a0a124600305392fb5`（`0dd5948c`）
- 在这份源码上移植了 `x-isoflow-react-19@1.1.1-patch-6` 相对该源码的差异
- 不使用 GitHub `markmanx/isoflow` 的 PR #60

`src/`、`webpack/` 和 `tsconfig.json` 来自上述 npm 包自带的源码与构建配置。许可为 MIT，见 `LICENSE`。

依赖只保留生产构建（`webpack --config ./webpack/prod.config.js && tsc --declaration --emitDeclarationOnly && tsc-alias`）需要的部分。上游的 lint、测试和 dev server 工具链没有装进工作区，避免把 `date-fns`、`prettier` 等可选 peer 注入到应用的 antd / Storybook。
