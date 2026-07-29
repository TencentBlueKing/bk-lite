## Purpose

定义许可管理能力的主规格，涵盖许可页面入口、许可治理、提醒配置与受控资源许可校验。

## ADDED Requirements

### Requirement: 许可管理页面必须通过稳定设置路由加载企业版实现

系统 MUST 保留 `/system-manager/settings/license` 作为稳定访问路径，并由该路径加载企业版许可管理页面实现。

#### Scenario: 公共设置页访问许可页
- **WHEN** 用户访问 `/system-manager/settings/license`
- **THEN** 系统 MUST 通过公共路由壳加载 enterprise 许可管理页面，而不是在公共页内直接实现许可业务

#### Scenario: 许可页使用统一弹窗组件
- **WHEN** 页面展示“添加许可”或“设置许可提醒”弹窗
- **THEN** 系统 MUST 使用仓库现有 `OperateModal` 组件承载弹窗交互

### Requirement: 许可管理必须支持当前许可与历史许可治理

系统 MUST 支持注册码读取、许可导入、生效许可列表、历史许可列表、许可停用与模块授权摘要展示。

#### Scenario: 管理员读取注册码并添加许可
- **WHEN** 管理员打开“添加许可”弹窗并提交有效许可码
- **THEN** 系统 MUST 返回当前注册码展示值、完成许可验签和导入，并在成功后刷新许可列表

#### Scenario: 管理员停用当前许可
- **WHEN** 管理员对生效许可执行停用操作
- **THEN** 该许可 MUST 从生效列表移除，并出现在历史许可列表中

#### Scenario: 页面展示模块授权摘要
- **WHEN** 许可管理页面加载模块摘要
- **THEN** 系统 MUST 返回免激活、已激活、未激活模块状态及数量汇总

### Requirement: 许可卡片风险样式必须跟随服务端提醒状态

系统 MUST 由服务端返回的提醒状态驱动许可卡片风险展示，而不是仅依赖页面本地剩余天数推断。

#### Scenario: 许可进入提醒窗口
- **WHEN** 许可剩余有效期小于等于当前提醒天数
- **THEN** 许可列表项中的 `reminder.status` MUST 返回 `warning`，页面 MUST 使用预警样式展示卡片和剩余天数标签

#### Scenario: 许可未进入提醒窗口
- **WHEN** 许可剩余有效期大于当前提醒天数
- **THEN** 许可列表项中的 `reminder.status` MUST 返回 `healthy`，页面 MUST 使用健康样式展示卡片和剩余天数标签

### Requirement: 提醒配置必须统一支持默认、单许可、节点和日志容量场景

系统 MUST 提供统一的通知渠道、通知人员、提醒时间或阈值配置能力，并在不同提醒场景中按既定模式回显。

#### Scenario: 修改默认提醒
- **WHEN** 管理员在默认提醒面板修改通知渠道、通知人员或默认提醒时间
- **THEN** 系统 MUST 保存全局默认提醒并在后续跟随默认的场景中使用该结果

#### Scenario: 单许可切换到单独配置
- **WHEN** 管理员在许可提醒弹窗选择 `custom`
- **THEN** 系统 MUST 允许维护该许可独立的渠道、人员和提醒时间，并在保存后按独立配置回显

#### Scenario: 单许可保持跟随默认
- **WHEN** 管理员在许可提醒弹窗选择 `follow`
- **THEN** 系统 MUST 展示默认提醒摘要，并忽略该许可上的独立渠道、人员和提醒时间值

#### Scenario: 节点提醒维护默认阈值和对象覆盖
- **WHEN** 管理员保存模块节点提醒配置
- **THEN** 系统 MUST 保存模块级阈值，并允许按 `object_type` 保存专用节点覆盖项

#### Scenario: 日志容量提醒切换模式
- **WHEN** 管理员在日志容量提醒中切换 `follow/custom`
- **THEN** 系统 MUST 在 `follow` 模式展示默认摘要，在 `custom` 模式保存日志独立通知渠道、通知人员和容量阈值

### Requirement: 提醒配置的用户和渠道必须限制在当前可见范围

系统 MUST 在提醒配置保存前校验通知渠道和通知人员是否处于当前用户可见范围内。

#### Scenario: 提交不可见渠道
- **WHEN** 请求中包含当前用户不可见的 `channel_ids`
- **THEN** 系统 MUST 拒绝保存该提醒配置

#### Scenario: 提交不可见用户
- **WHEN** 请求中包含当前用户不可见的 `user_ids`
- **THEN** 系统 MUST 拒绝保存该提醒配置

### Requirement: 受控新增资源入口必须经过许可校验

系统 MUST 对命中 `LICENSE_APP_PERMISSIONS` 的新增资源请求执行统一许可校验。

#### Scenario: 许可校验未启用
- **WHEN** `LICENSE_MGMT_ENABLED` 为 `False`
- **THEN** 许可校验中间件 MUST 直接放行请求

#### Scenario: 请求命中受控新增入口且无有效许可
- **WHEN** 请求命中 `LICENSE_APP_PERMISSIONS` 中定义的新增入口，且校验返回 `allowed=False`
- **THEN** 中间件 MUST 返回 403，并附带拒绝原因

#### Scenario: 请求命中受控新增入口且许可有效
- **WHEN** 请求命中 `LICENSE_APP_PERMISSIONS` 中定义的新增入口，且校验返回 `allowed=True`
- **THEN** 中间件 MUST 放行请求

#### Scenario: 许可校验必须使用本地服务调用
- **WHEN** 中间件执行许可校验
- **THEN** 中间件 MUST 直接调用 `LicenseService.is_module_allowed_for_create()`，而不是通过 NATS RPC 间接调用

### Requirement: CE/EE 代码分离架构

系统 MUST 将企业版代码（license_mgmt 等）与社区版代码分离存储，通过目录链接机制在开发时透明整合。

#### Scenario: 后端 EE 模块链接
- **GIVEN** EE 仓库位于独立目录（如 `WeOpsX-Enterprise/`）
- **WHEN** 开发者需要在 CE 仓库中使用 `license_mgmt` 模块
- **THEN** 系统 MUST 通过 Windows Junction（`mklink /J`）将 `server/apps/license_mgmt/` 链接到 EE 仓库对应目录
- **AND** CE 的 `.gitignore` MUST 忽略该目录，防止 CE 仓库跟踪 EE 代码

#### Scenario: 前端 EE 模块自动集成
- **GIVEN** CE 仓库 `web/enterprise/` 通过 Junction 链接到 EE 仓库的 `web/` 目录
- **WHEN** 执行 `pnpm prepare-enterprise`（由 `dev`/`build` 自动触发）
- **THEN** 脚本 MUST 执行以下操作：
  1. 扫描 `enterprise/src/app/` 下所有顶级目录，在 `src/app/(enterprise)/` 下创建 Junction（提供 api/types 等非路由模块）
  2. 读取 `enterprise/manifests/routes.json`，将 EE 页面源码复制到 CE 路由树 `{appName}/(pages)/(enterprise)/...`
  3. 复制时自动重写 import 路径：仅当 `@/app/{appName}/xxx` 在 EE 中存在且 CE 中不存在时，重写为 `@/app/(enterprise)/{appName}/xxx`

#### Scenario: EE 菜单注入
- **GIVEN** EE 仓库 `web/manifests/menus.json` 定义了菜单补丁
- **WHEN** 前端加载菜单配置
- **THEN** 系统 MUST 将 `zh_patches`/`en_patches` 中的子菜单项注入到目标菜单（如 `Setting`）的 `children` 中

#### Scenario: 不使用 Symbolic Link
- **WHEN** 在 Windows 环境创建目录链接
- **THEN** 系统 MUST 使用 `mklink /J`（Junction）而非 `mklink /D`（Symbolic Link），因为 Turbopack 会拒绝指向项目根目录外部的 Symbolic Link

## Implementation Notes

### 文件位置

**后端（EE 仓库 → CE Junction）**：
- `server/apps/license_mgmt/` — 整个 app 为 EE 代码，通过 Junction 链接

**前端 EE 源码**（位于 EE 仓库 `web/` 下）：
- `src/app/system-manager/settings/license/page.tsx` — 许可管理页面（~2385 行）
- `src/app/system-manager/settings/portal/page.tsx` — 门户设置页面
- `src/app/system-manager/api/license_mgmt/index.ts` — 许可 API 函数
- `src/app/system-manager/types/license.ts` — 类型定义
- `manifests/menus.json` — 菜单补丁（许可 + 门户）
- `manifests/routes.json` — 路由映射

**前端生成产物**（由 `prepare-enterprise.mjs` 自动生成，不入库）：
- `src/app/(enterprise)/system-manager/` — Junction，提供 api/types
- `src/app/system-manager/(pages)/(enterprise)/settings/license/page.tsx` — 复制的页面（含 import 重写）
- `src/app/system-manager/(pages)/(enterprise)/settings/portal/page.tsx` — 复制的页面

**CE 配置变更**：
- `web/next.config.mjs` — 新增 `outputFileTracingRoot`（扩展到 CE/EE 共同父目录）
- `web/scripts/prepare-enterprise.mjs` — EE 集成脚本
- `web/src/app/system-manager/constants/menu.json` — zh 部分补充"许可" tab

### 关键设计决策

1. **许可校验直接调用**：`LicenseCreateGuardMiddleware` 直接调用 `LicenseService.is_module_allowed_for_create()`，不经过 NATS RPC，因为中间件和服务在同一进程内
2. **Import 重写策略**：脚本复制 EE 页面到 CE 路由树时，仅重写指向 EE 独有模块的 import（通过检查路径在 CE/EE 中的存在性判断），避免误改指向 CE 公共模块的 import
3. **Junction vs Symlink**：Windows 上必须使用 Junction，Turbopack 对 Symbolic Link 有文件系统根限制检查
## Requirements
### Requirement: 许可缓存必须在多 Worker 环境下保持一致

系统 MUST 使用共享缓存（Redis）存储许可模块缓存，确保任意 Worker 进程的缓存变更对所有 Worker 立即可见。

#### Scenario: 多 Worker 环境下新增许可后缓存一致
- **WHEN** Worker A 执行 `add_license()` 并调用 `invalidate_license_cache()`
- **THEN** Worker B 的后续 `get_licensed_modules()` 调用 MUST 返回包含新许可的数据

#### Scenario: 多 Worker 环境下禁用许可后缓存一致
- **WHEN** Worker A 执行 `disable_license()` 并调用 `invalidate_license_cache()`
- **THEN** Worker B 的后续 `get_licensed_modules()` 调用 MUST 不再包含被禁用许可的模块

#### Scenario: 许可过期同步后缓存一致
- **WHEN** `sync_expired_licenses()` 将许可状态更新为 expired
- **THEN** 系统 MUST 调用 `invalidate_license_cache()` 清除缓存

### Requirement: 许可缓存必须保持日期级失效策略

系统 MUST 在缓存中记录数据对应的日期，跨天时自动刷新缓存。

#### Scenario: 同一天内缓存命中
- **WHEN** 缓存中的日期等于当前日期
- **THEN** 系统 MUST 直接返回缓存数据，不查询数据库

#### Scenario: 跨天缓存自动刷新
- **WHEN** 缓存中的日期不等于当前日期
- **THEN** 系统 MUST 从数据库重新加载许可数据并更新缓存

### Requirement: 许可缓存必须容忍 Redis 故障

系统 MUST 在 Redis 不可用或缓存数据损坏时降级为直接查询数据库。

#### Scenario: Redis 连接失败
- **WHEN** Redis 连接不可用
- **THEN** 系统 MUST 从数据库加载许可数据，不抛出异常

#### Scenario: 缓存数据格式损坏
- **WHEN** 缓存中的数据无法反序列化
- **THEN** 系统 MUST 视为缓存未命中，从数据库重新加载
