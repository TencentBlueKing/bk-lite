# 控制台 iframe 屏显模式（screen）

Status: implemented

本阶段交付：**壳层基础 + 运营分析牵头**。不是全站通用 iframe 嵌入闭环，也不做默认只读。从 OA 跳到其它模块后若丢失 `screen`，以及屏显下部分页未铺满/裁切/露底，记为已知限制，二期按反馈补。

## Completion Evidence

- 2026-09-10 本地：`cd web && ./node_modules/.bin/vitest run src/console-layout/__tests__/screenMode.test.ts src/console-layout/__tests__/resolve.test.ts src/console-layout/__tests__/appTopOverflow.test.ts src/app/(core)/components/global-webchat/__tests__/visibility.test.ts src/app/(core)/components/global-webchat/__tests__/global-webchat.test.tsx src/app/(core)/components/top-menu/__tests__/topMenu.layout.test.tsx src/app/(core)/components/app-top-side-nav/__tests__/appTopSideNav.test.tsx src/app/ops-analysis/utils/__tests__/viewHref.test.ts src/app/ops-analysis/(pages)/view/__tests__/screenMode.view.test.ts src/app/(core)/auth/signin/__tests__/page.test.tsx src/app/(core)/auth/signin/__tests__/screenMode.redirect.test.ts src/app/(core)/auth/signin/__tests__/LegacyThirdLoginAuthorizeBridge.test.tsx` → **12 files, 67 passed**
- 同次：`pnpm exec tsx scripts/ops-analysis-dashboard-share-test.ts` → `ops-analysis dashboard share contracts passed`；`pnpm exec tsx scripts/apm-menu-route-test.ts` → `APM menu route checks passed`
- 用法说明：`docs/operations/console-iframe-screen-mode.md`

## 本阶段合同

1. `screen=true|1` 时不出现平台顶栏、一级导航、应用二级壳层菜单、全局 AI；与分享/沉浸路径独立可叠加；无参 URL 日常壳层不变。
2. 从登录页带 `screen=true` 进入也保持屏显。屏显下部分业务页可能未铺满或底部裁切/露底，**高度对齐延期**，本阶段不保证；不要套用分享页整页 `overflow-hidden` 锁死。
3. `/ops-analysis/view` 屏显下隐藏目录侧栏与折叠钮；`/ops-analysis/settings` 屏显下不包分段菜单。深链 `type/id` 仍打开对应画布；view 内改路由必须透传 `screen`。其它 app 自挂二级菜单本阶段不藏。
4. 透传成功标准：运营分析屏显会话里点来点去，壳层不回流。其它 app 内部 `router.push` 全量透传延期。
5. 不改分享链路 / 订阅 Render；不做只读、framing、水印开关、其它模块业务侧栏隐藏。

## Problem Statement

客户或第三方门户需要把 Control Console（WeOpsX / BK-Lite Web）嵌进自己的页面（iframe）。现在打开平台地址会带完整壳层（顶栏、一级导航、应用业务二级侧栏、全局 AI 助手），与宿主页面抢导航，无法当「纯内容」使用。蓝鲸已有同类语义：普通地址为完整产品；带 `screen=true` 则隐藏导航，只留业务页。本平台缺少等价的全站屏显能力。

## Solution

为 Control Console 增加 URL 驱动的屏显模式：访问任意业务地址并带上约定查询参数后，隐藏平台壳层导航与全局 AI 入口，只保留当前路由的业务内容。普通无参访问行为不变。刷新、深链与登录回跳后仍保持屏显。提供简短使用说明，供门户用 iframe 引用。

## User Stories

1. As a 门户集成方, I want 用普通 Control Console URL 放进 iframe, so that 仍看到带导航的完整产品。
2. As a 门户集成方, I want 用带 `screen=true` 的同一业务 URL 放进 iframe, so that 无顶栏、无一二级导航、无全局 AI，只剩当前页内容。
3. As a 运营分析用户, I want 在屏显模式下打开仪表盘、大屏与拓扑, so that 画布可正常展示、可滚动、可刷新。
4. As a 任意已登录用户, I want 在浏览器直接打开带屏显参数的 URL, so that 效果与 iframe 内一致。
5. As a 普通用户, I want 未带屏显参数时现有导航与菜单完全不变, so that 日常使用不受影响。
6. As a 屏显会话中的用户, I want 刷新、深链进入、登录回跳后仍保持屏显, so that 内嵌体验不会突然恢复完整壳层。
7. As a 实施/文档读者, I want 看到 iframe 用法与参数含义说明, so that 能正确配置宿主门户。

## Implementation Decisions

### 对外契约

- 查询参数名：`screen`。真值：大小写不敏感的 `true` 或 `1` 视为开启；缺省或其它值视为关闭。
- 不引入第二套别名（如 `embed`），避免门户配置分裂。
- `screen` 只改变壳层展示，不放宽登录、菜单权限或数据权限。

### 持久化与透传

- URL 查询参数是唯一对外契约与权威来源。
- 站内官方导航出口（顶栏、一级侧/顶侧导航、应用业务二级侧栏等壳层生成的链接）在当前为屏显时必须透传 `screen`。
- 登录回跳可能丢 query：同标签页用 `sessionStorage` 做短时备份，回站后写回 URL。从登录页自身带 `screen=true` 进入也须能恢复。不得做成「一旦开过就永久屏显」的长期偏好。登录成功跳转（`SigninClient` / 已登录 `redirect`）若当前登录页含 `screen`，目标 URL 须带上该参数。
- 透传覆盖面（本阶段）：URL 权威 + 刷新仍屏显；登录回跳短时恢复；壳层链接生成带 `screen`；`/no-permission`、`/no-found` 带 `screen`；**运营分析 view 内全部路由变更**带 `screen`。监控 / CMDB / 日志及其它 app 内部 `router.push`、以及从 OA 跳到其它模块后丢参，本阶段不做，文档写明二期边界。

### 藏壳范围

- 屏显时隐藏：平台顶栏、一级导航（classic 分段栏或 app-top 侧栏）、应用业务二级侧栏、全局 AI 助手入口。
- 运营分析牵头：屏显下另隐藏 `/ops-analysis/view` 左侧目录/侧栏及折叠钮，以及 `/ops-analysis/settings` 管理分段菜单。深链 `type/id` 仍打开对应画布。其它模块业务自挂的二级菜单本阶段不藏。
- 保留：当前路由业务内容及其页内工具条（筛选、编辑、画布控件等）；合规水印默认保留。不做默认只读、不强制藏编辑/分享。
- 与既有「按路径藏壳」目的地（如运营分析分享页、OpsPilot 沉浸聊天）独立可叠加：统一「路径例外 **或** `screen` 为真则藏壳」；不强制分享/聊天 URL 必须带 `screen`。

### 布局与滚动

- 屏显主内容区去掉平台内边距（`p-0`）且保持可滚；不套用分享/沉浸路径的整页 `overflow-hidden` 锁视口。
- 屏显下部分业务页可能未铺满视口，或出现底部裁切 / 露底。**高度对齐延期**，本阶段不保证，也不再叠加壳层满高实验（`h-screen` / `--custom-height: 100vh` 等）。
- 大屏、拓扑等页面若自身需要锁视口或内部缩放，仍由页面自己控制。
- 屏显时取消平台级最小宽度地板（现网桌面壳层的 1280 约束）；业务页自带的最小宽度约束保留。文档建议宿主 iframe 给够宽度。

### 安全与部署边界

- MVP 不改 framing 策略（`frame-ancestors` / `X-Frame-Options` 等）；能嵌与否保持与现网一致。若需白名单，另立项，不塞进 `screen` 语义。
- 本需求默认同站或现网已能在 iframe 内维持登录的嵌套场景。跨站第三方 Cookie / SSO 免打扰登录不在本变更范围；文档写明前提。

### 代码边界

- 必改：Web 控制台壳层（屏显解析、藏壳判断、导航透传、登录短备份写回、屏显下不挂载全局 AI、屏显下取消平台最小宽度）。
- 配合：运营分析 view 藏目录侧栏 + view 内路由透传；短文档（含本阶段透传边界）。
- 不改：后端 API、权限模型、分享专用链路、订阅 Render、大屏/拓扑渲染逻辑（除非验收发现屏显回归再修）。

### 文档

- 短说明即可，建议落在现有 Web/实施可见文档并在变更说明中链接。固定四块之外，写明：本阶段仅保证运营分析会话内透传；其它模块按反馈二期补。不要写成「通用 iframe 嵌入已完工」。
- 用户文档不写 `sessionStorage` key 等实现细节。

## Testing Decisions

- 只测外部行为：给定 URL/导航输入，壳层控件是否出现、参数是否保留、滚动与无参回归是否成立；不锁内部存储 key 名或组件私有结构，除非契约本身需要稳定。
- 最高优先缝：控制台「是否藏壳」解析（路径例外与 `screen` 组合）+ 根布局对顶栏/一级导航/二级侧栏/全局 AI 的挂载决策。优先扩展现有 console-layout 解析测试与全局 AI 可见性测试，而不是新开平行规则引擎。
- 导航透传：对壳层链接生成做行为断言（屏显下 href 含 `screen`；非屏显下不加）。
- 登录回跳：用可控的 callback URL / storage 替身验证「丢 query 后能恢复到带 `screen` 的地址」，以及「冷开 `/auth/signin?screen=true` 再落到无 screen 业务 path 仍能 restore」；登录成功 redirect 目标须带 `screen`。不测真实 IdP。
- 布局回归：屏显下不施加平台 1280 最小宽度；非屏显桌面路由行为不变。不测、不锁屏显满高。
- 运营分析：屏显下不展示目录侧栏/折叠钮；settings 屏显不渲染 `WithSideMenuLayout`；view 导航 href 含 `screen`；无参不误加。
- 验收手工重点：OA 仪表盘、大屏、拓扑可展示、切画布/刷新后仍屏显；无参 URL 壳层不变。不把列表页铺满视口作为本阶段验收。
- 不要求本变更为每一个业务 app 的裸跳转补测试。

## Out of Scope

- 修改谁可以嵌本站（CSP `frame-ancestors` / 网关 framing 白名单）。
- 跨站 iframe 下的第三方 Cookie、SameSite、免打扰 SSO 改造。
- 将运营分析分享链路或订阅 Render 专用 layout 改造成依赖 `screen`。
- 用 iframe 打开全页冒充「组件级嵌入」（既有关联拓扑等能力仍走组件声明，不改为本模式）。
- 全仓清扫业务页每一处 `router.push` 的 query 透传（监控 / CMDB / 日志及其它 app 内部跳转本阶段不做）。
- 从运营分析跳到其它模块后丢失 `screen`（已知限制，二期补）。
- 屏显业务区视口高度对齐（铺满 / 露底 / 裁切；已知限制，二期补）。
- 后端 API、鉴权、菜单权限模型变更。
- 屏显模式下隐藏或关闭水印（默认保留）。
- 默认只读 / 强制藏编辑·分享。
- 其它模块业务侧栏屏显隐藏。
- 营销长文，或把文档写成通用 iframe 嵌入已完工。

## Further Notes

- 产品对外称呼可为 WeOpsX；仓库领域词为 BK-Lite Control Console。本能力挂在控制台壳层，运营分析牵头验收，平台壳层配合实现。
- 现网已有按路径藏壳先例（分享目的地、沉浸聊天），本阶段是壳层 + OA 基础可用，而不是新建第二套布局树，也不是全站嵌入完工。
- 对齐参考：蓝鲸 `?screen=true` 语义；参数名与真值已按共识固定，写入文档后即对外契约。
