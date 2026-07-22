# Enterprise Submodule Route Shims

Status: done

## Migration Context

- Legacy source: `openspec/changes/enterprise-submodule-route-shims/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当商业版代码通过 submodule 挂在仓库根目录 `enterprise/` 下时，菜单、页面、语言包和静态资源不再与社区版 `web/` 同目录。若继续依赖社区版手写页面 loader 或静态 import 商业页面，社区版构建会被商业页面反向污染，也无法支撑后续商业版独立扩展。

## What Changes

- 定义 `web/enterprise` 作为社区版前端对商业代码的统一消费入口，约定其通过 manifest 描述菜单 patch 和页面路由来源。
- 为商业版页面引入 build-time route shim 机制：社区版构建前根据 `web/enterprise` 的路由 manifest 自动生成 Next App Router 所需的 page shim。
- 保留现有社区版菜单/语言包/静态资源合并流程，并扩展为可直接扫描 `web/enterprise` 的菜单、locales 和 public 资源。
- 明确社区版单独构建时的行为：当 `web/enterprise` 不存在时，构建必须跳过商业版装配，不得因为缺少商业代码而失败。
- 为后续根目录 submodule 下的商业前端功能提供统一接入协议，避免每新增一个商业页面就要求社区版手写对应 loader。

## Capabilities

### New Capabilities
- `enterprise-submodule-route-assembly`: 定义 `web/enterprise` 如何通过 manifests、资源扫描和 build-time route shims 接入社区版前端构建。

### Modified Capabilities

## Impact

- **Web 构建与装配**:
  - `web/scripts/prepare-enterprise.mjs` 或同类构建前脚本
  - `web/src/utils/dynamicsMerged.mjs`
  - `web/src/app/(core)/api/menu/route.ts`
  - Next 构建输入目录与生成的 route shim 目录
- **商业版 submodule 协议**:
  - `web/enterprise/manifests/routes.json`
  - `web/enterprise/manifests/menus.json`
  - `web/enterprise/src/app/**`
  - `web/enterprise/public/**`
- **开发与发布流程**:
  - 社区版单独构建流程
  - 商业版 submodule 已拉取时的前端构建流程

## Implementation Decisions

## Context

BK-Lite 计划让商业版代码独立维护在另一个仓库中，并通过 submodule 挂载到社区版仓库根目录 `enterprise/`。社区版前端通过 `web/enterprise -> ../enterprise/web` 软链接消费商业版前端代码，而社区版前端构建入口仍然固定在 `web/`。

现有社区版前端已经具备一定的菜单、语言包和静态资源合并能力，但页面路由仍依赖 Next App Router 的文件系统约束：最终参与构建的页面必须在社区版 `web` 的路由树里可见。如果继续让社区版手写每个商业页面 loader，不仅会污染社区版源码，也无法随着商业功能扩展而稳定维护。

## Goals / Non-Goals

**Goals:**
- 支持商业版前端代码通过 `web/enterprise` 接入社区版前端构建
- 让社区版单独构建时在没有 `web/enterprise` 的情况下仍然正常完成
- 用统一 manifest + build-time route shim 机制替代手写商业页面 loader
- 复用并扩展现有菜单、locales、public 资源合并机制，使其能从 `web/enterprise` 读取增量内容

**Non-Goals:**
- 本次不定义商业版后端 submodule 的完整装配协议
- 本次不要求把已有所有商业页面一次性迁移到 manifest 模式
- 本次不设计通用插件运行时；仍以构建期装配为主
- 本次不改变既有商业页面的最终访问 URL 约定

## Decisions

### 1. 商业版前端通过 `web/enterprise` 软链接接入

社区版构建脚本以 `web/` 为当前工作目录，通过 `web/enterprise -> ../enterprise/web` 软链接读取商业版前端输入。这样商业代码在社区版前端工程内有稳定入口，同时仍保留商业仓库的独立边界。

备选方案：
- 直接把商业版页面逐个软链接到 `web/src/app`：本地直观，但新增页面要单独挂载，长期维护成本更高
- 把商业页面继续散落到 `web/src/app`：最简单，但违反商业版独立仓库目标

### 2. 商业页面路由通过 build-time generated shim 接入 Next App Router

商业版 submodule 提供 `manifests/routes.json`，声明 URL 到商业页面源文件的映射。社区版在构建前根据该 manifest 自动生成 page shim，再由 Next 正常参与构建。

这样可以保留 `/system-manager/settings/portal` 这类原始 URL，同时避免社区版手写每个商业页面入口。

备选方案：
- 社区版手写页面 loader：实现简单，但每个商业页面都会反向污染社区主干
- 用统一 catch-all runtime router：实现更动态，但会改变现有 URL 和权限模型

### 3. 菜单、语言包、静态资源继续采用扫描式合并

商业版前端通过 `web/enterprise` 提供 `manifests/menus.json` 以及常规 `src/**/locales`、`public/**` 目录。社区版构建与运行时接口直接扫描这些输入并合并，不为每个商业资源再单独设计加载器。

这样把复杂度集中在“页面路由必须生成 shim”这一点，其它资源沿用已有的聚合模型。

### 4. 社区版构建时必须显式容忍 submodule 缺失

所有读取 `web/enterprise` 的逻辑都必须先检查目录是否存在。不存在时：
- 菜单 patch 不注入
- route shim 不生成
- locales/public 不合并
- 整体构建继续完成

这样社区版单独出包时不会因为商业版 submodule 没拉取而失败。

## Risks / Trade-offs

- **[Risk] route manifest 与真实源文件不一致会导致生成的 shim 无效** → 在构建前脚本中增加 manifest 校验和明确错误输出
- **[Risk] 生成 shim 会让调试路径多一层跳转** → 当前实现改为在构建前物化路由文件内容，避免 Next/Turbopack 对跨根目录 route import 的解析限制，同时保留 manifest 驱动和无手写 loader 的目标
- **[Trade-off] 页面路由需要生成中间文件，而菜单/locales/public 可直接扫描** → 接受两种接入方式并存，以适配 Next 的文件系统路由限制
- **[Risk] 社区构建和商业构建路径不一致可能带来遗漏** → 统一由 `prepare-enterprise` 脚本控制，社区/商业 build 都走同一装配入口

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-17
```

## Capability Deltas

### enterprise-submodule-route-assembly

## ADDED Requirements

### Requirement: 社区版构建必须支持 web/enterprise 缺失

系统 MUST 在 `web/enterprise` 不存在时继续完成社区版前端构建，而不能因为缺少商业版前端入口而失败。

#### Scenario: 社区版单独构建
- **WHEN** 前端构建启动且 `web/enterprise` 不存在
- **THEN** 系统 MUST 跳过商业版菜单、路由、语言包和静态资源装配，并继续完成社区版构建

#### Scenario: 商业版 submodule 已拉取时构建
- **WHEN** 前端构建启动且 `web/enterprise` 存在
- **THEN** 系统 MUST 读取商业版 manifests 和资源输入，并将其纳入构建装配流程

### Requirement: 商业页面路由必须通过 manifest 驱动的 build-time shim 接入

系统 MUST 支持商业版通过 `web/enterprise/manifests/routes.json` 声明页面路由来源，并在构建前生成 Next App Router 所需的 route shim。

#### Scenario: 为商业页面生成 shim
- **WHEN** `routes.json` 声明 `/system-manager/settings/portal` 对应的商业页面源文件
- **THEN** 系统 MUST 在社区版前端构建输入中生成对应的 page shim，并将该 URL 路由到商业页面实现

#### Scenario: 社区版不再手写商业页面 loader
- **WHEN** 新增一个商业版页面并在 `routes.json` 中注册
- **THEN** 系统 MUST 允许该页面通过构建期 shim 生效，而不要求社区版源码手写新的页面 loader

### Requirement: 商业菜单必须通过 manifest 注入社区菜单树

系统 MUST 支持商业版通过 `web/enterprise/manifests/menus.json` 声明菜单 patch，并将其合并到社区版基础菜单树中。

#### Scenario: 商业菜单 patch 被注入
- **WHEN** `menus.json` 声明向 `Setting` 节点追加 `portal_settings` 菜单项
- **THEN** 系统 MUST 在商业版构建或运行时菜单加载中，将该菜单项注入到基础菜单树

#### Scenario: 社区版不显示商业菜单
- **WHEN** `web/enterprise` 不存在或 `menus.json` 未提供对应 patch
- **THEN** 系统 MUST 不显示商业菜单项

### Requirement: 商业语言包与静态资源必须支持直接扫描合并

系统 MUST 支持从 `web/enterprise` 直接扫描并合并商业版 locales 与 public 资源。

#### Scenario: 合并商业语言包
- **WHEN** `web/enterprise/src` 下存在商业页面对应的 locale 文件
- **THEN** 系统 MUST 将这些 locale 内容合并到社区版最终语言包输出中

#### Scenario: 合并商业静态资源
- **WHEN** `web/enterprise/public` 下存在商业版静态资源
- **THEN** 系统 MUST 将这些资源纳入社区版构建输出，使商业页面可在构建产物中访问它们

## Work Checklist

## 1. Enterprise input contract

- [x] 1.1 Define the `web/enterprise` manifest contract, including route manifest shape, menu manifest shape, and expected source/public directory locations.
- [x] 1.2 Add build-time checks so the community build can detect whether `web/enterprise` exists and branch cleanly between community-only and enterprise-enabled assembly.

## 2. Build-time route assembly

- [x] 2.1 Implement a pre-build script that reads `web/enterprise/manifests/routes.json` and generates the required Next App Router page shims for each declared enterprise route.
- [x] 2.2 Ensure generated route files are recreated or skipped deterministically for community-only versus enterprise-enabled builds, without requiring hand-maintained community loaders.

## 3. Shared resource aggregation

- [x] 3.1 Extend menu aggregation to read `web/enterprise/manifests/menus.json` and merge enterprise menu patches into the community menu tree only when the enterprise link is present.
- [x] 3.2 Extend locale and static asset aggregation to scan `web/enterprise/src/**/locales` and `web/enterprise/public/**`, while preserving successful community-only builds when those inputs are absent.
