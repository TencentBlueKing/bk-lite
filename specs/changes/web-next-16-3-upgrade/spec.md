# Web Next.js 16.3 升级

Status: approved-design

## 问题

Control Console 当前使用 Next.js 16.0.10、React 19.2.3、Node 24 和 pnpm
9.15.4。框架、React 类型、Next 配套工具与 ESLint 主版本不一致；Docker、
本地工作区和生成脚本对 pnpm 工作区配置的处理也不一致。现有生产构建虽已使用
Turbopack，但没有跨构建持久缓存。

升级基线还暴露出两组历史质量债务：TypeScript 5 全量检查有 27 个诊断，涉及
9 个源码文件；排除生成产物后，ESLint 8 有 107 个错误，涉及 56 个源码文件。
现有 `next.config.mjs` 使用 `typescript.ignoreBuildErrors: true`，生产构建无法
阻止新的类型错误。当前 lint 还会误扫 `storybook-static`，产生大量无意义错误。

本次变更需要把框架升级与工程基线治理一起完成，使后续 Next、React 和包管理器
升级能够在可靠门禁下小步进行。

## 目标

- 将 Control Console 升级到 Next.js 16.3 稳定线，并同步 React/ReactDOM、React
  类型、`eslint-config-next` 和 `@next/bundle-analyzer` 等直接配套依赖。
- 保持 Node 24，升级并精确锁定 pnpm 11.20.0，统一本地、Docker 和项目声明。
- 将 ESLint 8 legacy config 迁移到 ESLint 9 flat config，保留现有有效规则语义。
- 清零现有 TypeScript 和 ESLint 源码错误，删除
  `typescript.ignoreBuildErrors`，让类型和 lint 失败阻断交付。
- 继续使用 Turbopack 生产构建，并完整启用可跨 Docker/CI 构建复用的生产构建
  持久缓存。
- 增加最小 Playwright 冒烟测试，为框架升级提供运行时回归保护。
- 保持生产行为、路由语义和现有业务功能不变。

## 非目标

- 不在本次升级 TypeScript 7；继续使用兼容 Next 16.3 生态的 TypeScript 5。
- 不启用 Instant Navigations、`cacheComponents` 或 partial prefetching，不迁移
  页面到新的缓存/预取模型。
- 不启用 React Compiler，不为 `import.meta.glob` 等新能力改写业务代码。
- 不建设完整端到端测试体系；Playwright 只覆盖框架升级所需的代表性冒烟路径。
- 不借清理 lint/type 错误进行无关重构、视觉改版或业务行为变更。
- 不修改根 `AGENTS.md`/`CLAUDE.md` 的仓库规则。Next 版本匹配文档若需要落地，
  只能以不覆盖现有规则的受控方式加入 `web/` 范围。

## 依赖与版本策略

- `next`、`eslint-config-next`、`@next/bundle-analyzer` 使用 `~16.3.0`，只自动
  接受 16.3 patch，不自动进入新的 minor。
- React、ReactDOM、`@types/react`、`@types/react-dom` 使用相互兼容的 19.2
  稳定 patch 线；实现时依据 Next 16.3 peer contract 选择同一兼容组合。
- `packageManager` 精确声明 `pnpm@11.20.0`；Docker 构建和运行阶段使用相同版本。
- 保持 `web/.nvmrc` 的 Node 24，并在 `package.json` 声明与 Docker 一致的 Node
  engine 下限。
- 生产和 CI 安装必须使用 `pnpm install --frozen-lockfile`。lockfile 是实际交付
  版本的唯一解析结果，不允许构建期间漂移。
- Next/React patch 至少每月检查一次；安全公告要求的 patch 立即处理。

## 实现设计

### 1. 先建立干净质量基线

- 在旧依赖基线上修复全部 27 个 TypeScript 诊断和 107 个源码 lint 错误。
- `storybook-static`、`.next`、构建产物、生成资源和依赖目录必须通过配置忽略，
  不得修改生成产物来让 lint 通过。
- 类型和 lint 修复以最小、行为保持为原则。删除无用代码前核对真实使用方；类型
  收窄、单位枚举、测试全局类型和渲染返回类型必须按实际契约修复，不使用
  `any`、批量 disable 或无依据断言隐藏问题。
- 基线清零后删除 `typescript.ignoreBuildErrors`，确保 `next build` 恢复类型失败
  即失败的默认行为。

### 2. 统一 pnpm 安装链路

- 将本地声明、Docker builder、生产镜像统一到 pnpm 11.20.0。
- 保留并规范 `pnpm-workspace.yaml` 中的 workspace packages 与 pnpm 11 安装策略。
  `generate-workspace.js` 和 Docker 不得再覆盖并丢失 `allowBuilds` 等设置。
- 保持当前构建脚本安全策略：依赖生命周期脚本默认受控，仅允许构建必需的原生
  依赖。对 `esbuild`、`sharp`、`unrs-resolver` 等实际需要项进行冷安装验证。
- 接受 pnpm 11 的供应链保护默认值；若新包发布时间策略阻止刚发布的受信任框架
  patch，只允许添加最小、带原因的包级例外，不全局关闭保护。
- 审核 lockfile diff，禁止无关依赖整体漂移；确认现有 Webpack patch 是否仍有
  真实引用，无引用则单独删除孤儿 patch。

### 3. 升级 Next/React/ESLint 生态

- 同步升级 Next、React/ReactDOM、React 类型、Next ESLint preset 和 bundle
  analyzer，避免不同主次版本混装。
- 将 `.eslintrc` 与 `.eslintignore` 迁移为 ESLint 9 flat config；保留项目现有
  Next、TypeScript、Storybook 与自定义规则语义，并用 flat config ignores 统一
  排除生成目录。
- 保持 `next build --turbo`。Next 16 默认使用 Turbopack，但显式参数暂时保留，
  便于审查构建器选择；后续可作为无行为变更清理。
- 检查并迁移 Next 16.3 已废弃或移除的配置/API。仓库没有采用 Instant
  Navigations，因此不得为通过构建而打开相关实验开关。
- Next/React 类型升级产生的所有新增诊断必须修复到零，不能恢复忽略开关。

### 4. 生产构建持久缓存

- 启用 Next 16.3 的 Turbopack production filesystem cache。
- Docker builder 使用 BuildKit cache mount 保存 Turbopack 构建缓存；缓存不得被
  复制进最终运行镜像。
- CI/远程 builder 需要配置可复用缓存；缓存键至少关联 pnpm lockfile、Next
  版本、构建配置和影响编译的环境配置。无法提供远程缓存时，必须明确只有同一
  builder 的热构建可复用。
- 缓存命中失败必须退化为正确的冷构建，不能阻断发布；任何缓存优化都不能牺牲
  构建可复现性。
- 验收同时记录冷构建和代码小改动后的热构建耗时；不预设虚构百分比，要求热构建
  有可重复的正收益且产物一致。

### 5. 最小 Playwright 冒烟层

- 增加 Playwright 测试与单一 `test:e2e:smoke` 入口，不扩展成完整业务 E2E。
- 使用确定性 API/session fixture，避免依赖完整 server 或共享测试账号。
- 至少覆盖：生产服务启动、`/auth/signin` 渲染、`/cmdb`、`/monitor`、
  `/ops-analysis` 三个代表路由可进入或按既有认证契约跳转、客户端导航可用、
  关键静态资源成功加载、浏览器没有未处理异常。
- 若历史业务错误修复改变可观察行为，必须增加对应的 Vitest 回归测试；纯格式化
  修复不新增无效测试。

## 交付拆分

同一个升级任务/PR 按以下顺序形成四个可独立审查和回退的提交：

1. 清零 TypeScript/ESLint 历史基线，修正生成物忽略并启用质量门禁。
2. 升级 pnpm 11，统一 workspace、lockfile、本地与 Docker 安装链路。
3. 升级 Next 16.3、React 配套依赖并迁移 ESLint 9 flat config。
4. 启用 Turbopack 持久缓存并加入 Playwright 冒烟验证。

每个提交必须在自己的依赖状态下通过适用门禁。后续提交失败时应能定位到单一
迁移阶段，不通过混合修改掩盖原因。

## 验证与验收

- Node 24 + pnpm 11.20.0 下执行冻结 lockfile 的全新安装成功。
- `pnpm lint`：源码零错误、生成目录不参与扫描。
- `pnpm type-check`：TypeScript 5 全量检查零诊断。
- `pnpm exec vitest run`：全部现有 Vitest 与新增回归测试通过。
- `pnpm test:e2e:smoke`：最小浏览器冒烟测试通过。
- `pnpm build`：Next 16.3 Turbopack 冷构建成功，且类型错误会阻断构建。
- Docker 冷构建、热构建均成功；记录耗时并确认热构建复用缓存。
- 运行最终镜像，确认 `next start` 正常监听、健康响应和静态资源可访问。
- bundle analyzer 与 Storybook 配置至少完成配置加载验证；受升级影响的现有测试
  脚本全部保持可运行。
- `git diff` 不包含生成产物、凭据、无关格式化或用户现有 `enterprise` 子模块修改。

## 回滚

- 四个提交可按逆序独立回退。缓存提交回退只损失构建加速，不改变运行时行为。
- Next/React 提交回退时同时回退配套类型、ESLint preset、bundle analyzer 和
  lockfile，禁止只降 Next 形成混装。
- pnpm 提交回退时同时回退 `packageManager`、Docker 版本、workspace 策略和
  lockfile。
- 历史质量修复提交原则上保留；若发现行为回归，只回退有问题的最小源码修复并
  补回归测试，不重新启用全局错误忽略。

## 完成定义

所有验证项有新鲜退出码或运行证据；冷/热构建数据已记录；生产镜像可启动；
TypeScript 与 ESLint 均为零错误；Next/React/pnpm 版本与 lockfile 一致；没有启用
Instant Navigations、TypeScript 7 或其他未批准实验能力。
