# isoflow

运营分析架构图使用的 Isoflow 源码目录。它不是 npm 包：`package.json` 没有 `name`，也不在 pnpm workspace 里。Next 用相对路径引用本目录，只消费 `webpack + tsc` 产出的 `dist/`（`main` / `types` 指向 `dist`），不直接编译 `src/`。

构建依赖在 `web/package.json` 的 `devDependencies`。webpack 会把除 `react` / `react-dom` 以外的依赖打进 `dist`。在 `web/` 执行 `pnpm run build:isoflow`；`predev`、`prebuild` 和 `type-check` 会先跑它。

zustand 固定为 4.4.3，只放在 web 的 devDependencies，供本目录构建。CMDB 继续在自己的 workspace 包里依赖 zustand 5.0.9。pnpm 默认 `node-linker=isolated` 且 `public-hoist-pattern` 为空，两份不会提升到同一层。

## 来源

- npm 包：`x-isoflow-react-19@1.1.1`
- gitHead：`0dd5948c72f2611ded0a15a0a124600305392fb5`（`0dd5948c`）
- 在这份源码上移植了 `x-isoflow-react-19@1.1.1-patch-6` 相对该源码的差异
- 不使用 GitHub `markmanx/isoflow` 的 PR #60

`src/`、`webpack/` 和 `tsconfig.json` 来自上述 npm 包自带的源码与构建配置。许可为 MIT，见 `LICENSE`。

依赖只保留生产构建（`webpack --config ./webpack/prod.config.js && tsc --declaration --emitDeclarationOnly && tsc-alias`）需要的部分。上游的 lint、测试和 dev server 工具链没有装进工作区，避免把 `date-fns`、`prettier` 等可选 peer 注入到应用的 antd / Storybook。
