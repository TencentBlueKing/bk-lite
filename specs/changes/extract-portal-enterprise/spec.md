# Extract Portal Enterprise

Status: done

## Migration Context

- Legacy source: `openspec/changes/extract-portal-enterprise/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前系统管理中的“设置 / 门户”直接实现在社区版模块内，导致社区版和商业版在同一套菜单、页面和构建入口上耦合。随着后续还会有更多“社区版不展示、商业版追加”的能力，如果不先把门户抽成一层 enterprise overlay，双仓开发和后续维护都会持续放大冲突成本。

## What Changes

- 将系统管理中的“门户”从社区版默认菜单中移除，社区版保留稳定路由入口但不默认展示该能力。
- 在仓库根目录新增 `enterprise/` 扩展层，并按 `enterprise/web`、`enterprise/server` 分离商业版前后端增量实现。
- 为系统管理菜单引入 enterprise patch 注入方式，使商业版可以在不改写社区版基础菜单文件的前提下，将“门户”菜单追加到“设置”下。
- 将 `/system-manager/settings/portal` 调整为稳定的 overlay 入口页：有 enterprise 实现时加载商业版页面，没有实现时回退到受控 stub。
- 保持现有门户配置读写接口和页面 URL 不变，避免商业版功能抽离后影响已有数据和访问路径。

## Capabilities

### New Capabilities
- `portal-enterprise-overlay`: 定义系统管理门户能力如何从社区版主干中抽离，并通过 enterprise overlay 方式注入菜单和页面实现。

### Modified Capabilities

## Impact

- **Web 前端**:
  - `web/src/app/system-manager/constants/menu.json`
  - `web/src/app/system-manager/(pages)/settings/portal/page.tsx`
  - `web/src/app/(core)/api/menu/route.ts` 消费 enterprise 菜单 patch
  - `web/tsconfig.json`、`web/tsconfig.lint.json`、`web/src/lib/enterpriseStub.ts`
  - 新增 `enterprise/web/src/app/system-manager/` 作为商业版页面与菜单 patch 目录
- **构建与装配**:
  - 使用现有 `NEXTAPI_INSTALL_APP` 扫描机制，将根目录 `enterprise/web` 下的菜单来源接入社区版构建
- **后端/数据**:
  - 复用现有 portal settings 接口与配置项，无需新增数据库迁移
  - 预留 `enterprise/server` 作为后续商业版后端扩展目录

## Implementation Decisions

## Context

当前“设置 / 门户”页面、菜单项和默认实现都直接放在 `web/src/app/system-manager/` 下，社区版和商业版共享同一份菜单定义。这导致一旦某个能力只想在商业版出现，就只能继续把差异写进社区版主干，或者维护两份接近重复的页面与菜单文件。

本次变更先以“门户”作为第一个抽离对象，在当前项目内引入一个 `enterprise` 扩展层，验证后续“社区主干 + 商业 overlay”模式是否能在 BK-Lite 的现有 Next.js 应用结构中工作。约束包括：

- 现有 `/api/menu` 已支持从各 app 的 `menu.json` 读取菜单并应用 patch
- `NEXTAPI_INSTALL_APP` 已用于控制前端 app 扫描范围
- `/system-manager/settings/portal` 已经是既有访问路径，不能随意修改
- 现有 portal settings API 和数据项已经在线上使用，不宜迁移

## Goals / Non-Goals

**Goals:**
- 将“门户”从社区版默认菜单中抽离，使社区版默认不再展示该菜单项
- 保留 `/system-manager/settings/portal` 作为稳定路由入口，避免已存在链接和配置失效
- 在当前项目目录下新增 `enterprise` 扩展层，承载门户菜单 patch 和页面实现
- 让社区版在没有 enterprise 实现时仍能安全构建和运行
- 为后续其它“挂载到既有模块下的商业功能”复用同一扩展模式

**Non-Goals:**
- 本次不处理独立一级商业模块（如独立图表系统）的接入模式
- 本次不拆分后端 portal settings API；仍复用现有 system settings 接口
- 本次不建设完整双仓装配流水线；仅在当前仓库中落地 overlay 目录结构
- 本次不泛化为所有模块的统一插件系统，仅覆盖 system-manager/portal 这一路径

## Decisions

### 1. 在当前仓库根目录新增 `enterprise/`，并按 `enterprise/web`、`enterprise/server` 作为 overlay 根目录

将商业版增量实现收敛到仓库根目录的 `enterprise/` 下，而不是继续散落在 `web/` 或 `system-manager` 主目录中。这样可以让当前仓库里的 `enterprise/` 直接对齐未来商业版 submodule 的挂载位置：前端增量位于 `enterprise/web`，后端增量位于 `enterprise/server`。

备选方案：
- 继续把商业实现放在 `web/src/app/system-manager/enterprise/`：接入简单，但企业增量仍然与社区模块目录强耦合
- 直接新建独立仓库：长期更干净，但当前改造成本更高，不适合先验证模式

### 2. 社区版保留稳定路由页，实际页面通过 alias + stub 加载 enterprise 实现

`/system-manager/settings/portal` 继续保留在社区版目录中，但改为轻量入口页，只负责加载 enterprise 实现。若 enterprise 页面不存在，则回退到受控 stub，而不是让构建时报模块缺失错误。

这样既保留既有 URL，又把真实实现从社区版主干中挪出。

备选方案：
- 直接删除社区路由：会破坏既有链接和权限映射
- 让社区路由里保留完整页面实现，再在企业版覆盖：仍然保留了重复实现和主干耦合

### 3. 菜单采用“基础菜单 + enterprise patch”合并，而不是修改社区版菜单文件

`system-manager` 的基础菜单继续由社区版 `menu.json` 定义，但去掉 `portal` 子菜单。enterprise 目录额外提供 patch 文件，将 `portal_settings` 插入到“设置”分组下。

这样社区版菜单保持干净，商业能力通过增量 patch 接入，不需要长期维护两份基础菜单。

备选方案：
- 在社区版菜单里加 `if enterprise`：会把商业条件判断扩散到主干
- 商业版直接复制完整 `menu.json`：后续合并社区更新时冲突会持续增加

### 4. 继续复用现有 portal 配置接口和数据键

页面抽离只影响前端菜单与页面实现的组织方式，不调整现有 `portal_name`、`portal_logo_url`、`portal_favicon_url`、`watermark_*` 的读取和写入路径。

这样可以把这次改造的变量控制在“前端结构拆分”层面，避免把后端与数据迁移混在同一次变更中。

## Risks / Trade-offs

- **[Risk] overlay 目录扫描规则新增后，菜单加载逻辑更复杂** → 仅对 enterprise 目录增加单一入口和明确命名约定，避免引入通用插件系统
- **[Risk] stub 回退策略如果过于宽松，可能掩盖企业页面缺失问题** → 社区版允许安全回退，但企业版构建和测试需要显式校验 portal overlay 是否存在
- **[Risk] 现有权限过滤依赖 `portal_settings` 名称，菜单抽离后若命名变化会导致菜单被过滤掉** → 保持 `portal_settings` 作为稳定菜单名，不改已有权限映射
- **[Trade-off] 当前先在单仓中引入 `enterprise/` 目录并模拟 submodule 边界，而不是直接接入真实商业仓库** → 短期验证成本更低，但后续仍需把该目录替换为实际 submodule

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-17
```

## Capability Deltas

### portal-enterprise-overlay

## ADDED Requirements

### Requirement: 社区版默认不得展示门户菜单

系统管理基础菜单 MUST 在社区版默认构建中不包含 `portal_settings` 菜单项。

#### Scenario: 社区版仅加载基础菜单
- **WHEN** 系统仅加载社区版 `system-manager` 基础菜单源
- **THEN** “设置”分组下 MUST 不出现 `/system-manager/settings/portal` 菜单项

#### Scenario: enterprise patch 被注入后显示门户菜单
- **WHEN** 系统同时加载基础菜单和 enterprise portal 菜单 patch
- **THEN** “设置”分组下 MUST 追加名称为 `portal_settings`、URL 为 `/system-manager/settings/portal` 的菜单项

### Requirement: 门户页面必须通过稳定路由加载 enterprise overlay

系统 MUST 保留 `/system-manager/settings/portal` 作为稳定访问路径，并由该路径加载 enterprise overlay 中的真实页面实现。

#### Scenario: enterprise 页面存在时加载真实实现
- **WHEN** 用户访问 `/system-manager/settings/portal` 且 enterprise overlay 中存在门户页面实现
- **THEN** 系统 MUST 渲染 enterprise overlay 提供的门户设置页面

#### Scenario: enterprise 页面缺失时安全回退
- **WHEN** 用户访问 `/system-manager/settings/portal` 但当前构建中不存在 enterprise 门户页面实现
- **THEN** 系统 MUST 回退到受控 stub，而不能因为模块缺失导致构建失败

### Requirement: enterprise overlay 必须有明确的目录约定

系统 MUST 在当前仓库根目录提供明确的 `enterprise/` overlay 目录，并按 `enterprise/web`、`enterprise/server` 分离商业版增量实现。

#### Scenario: 页面实现位于 enterprise 目录
- **WHEN** 开发者为商业版提供门户页面实现
- **THEN** 该实现 MUST 放在当前项目约定的 enterprise 目录下，而不是继续放在社区版 `system-manager` 默认页面目录中

#### Scenario: 菜单 patch 位于 enterprise 目录
- **WHEN** 开发者为商业版追加门户菜单
- **THEN** 菜单 patch MUST 放在当前项目约定的 enterprise 目录下，并通过菜单加载流程合并到基础菜单树中

### Requirement: 门户抽离不得改变既有访问路径和配置键

系统 MUST 在门户抽离到 enterprise overlay 后保持现有门户访问路径和 portal settings 配置键不变。

#### Scenario: 已有入口链接继续可用
- **WHEN** 用户通过现有链接访问 `/system-manager/settings/portal`
- **THEN** 系统 MUST 继续使用该路径访问门户能力，而不能要求切换到新 URL

#### Scenario: 既有配置键继续生效
- **WHEN** enterprise 门户页面读取或保存门户配置
- **THEN** 系统 MUST 继续使用现有 portal settings 数据键，而不能引入新的迁移型配置键

## Work Checklist

## 1. Overlay scaffolding

- [x] 1.1 Create the root-level `enterprise/{web,server}` overlay directory structure and add TypeScript alias/stub support so community builds can resolve optional enterprise portal modules safely.
- [x] 1.2 Extend the menu loading flow to read and merge enterprise menu patch sources alongside existing community menu definitions.

## 2. Portal extraction

- [x] 2.1 Remove `portal_settings` from the community `system-manager` base menu and add an enterprise patch that injects the portal menu under the existing settings group.
- [x] 2.2 Move the current portal settings page implementation into the enterprise overlay and convert `/system-manager/settings/portal` into a stable loader entry that renders the enterprise implementation or a controlled fallback.

## 3. Compatibility and validation

- [x] 3.1 Preserve the existing portal URL and portal settings data contract so the extracted enterprise page continues using current settings keys and APIs unchanged.
- [x] 3.2 Verify community behavior (no portal menu, safe fallback) and enterprise behavior (portal menu injected, portal page renders) through the existing web lint/type-check flow.
