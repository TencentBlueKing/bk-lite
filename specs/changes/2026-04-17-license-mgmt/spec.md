# 2026 04 17 License Mgmt

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-17-license-mgmt/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

系统管理已经落地许可管理能力，但 `openspec/changes/license-mgmt` 仍停留在早期规划文档形态，未转换为当前仓库使用的 spec-driven 变更结构，导致 OpenSpec 无法识别该变更已经实现完成，也无法进入归档流程。

## What Changes

- 将 `license-mgmt` 变更整理为当前仓库可识别的 spec-driven 结构，补齐 `proposal.md`、`design.md`、`specs/**` 与可解析的 `tasks.md`。
- 以当前实际实现为准，明确许可管理已经覆盖的能力范围：企业版许可页入口、许可列表与历史许可、注册码读取与许可导入、默认/单许可/节点/日志提醒、许可剩余时间状态展示、资源新增许可拦截。
- 将前端提醒面板与许可提醒弹窗内容区继续收敛到原型结构，统一使用现有 `OperateModal` 与原型样式语义。

## Capabilities

### New Capabilities

- `license-management-page`: 系统管理设置中的企业版许可管理页面，包含许可列表、默认提醒、历史许可、平台模块与提醒配置交互。
- `license-reminder-governance`: 全局提醒、单许可提醒、节点提醒与日志容量提醒的统一配置与回显能力。
- `license-create-guard`: 基于 `LICENSE_APP_PERMISSIONS` 与 RPC 校验的新增资源许可拦截能力。

### Modified Capabilities

- `license-management-page`: 许可卡片状态与提醒配置内容区改为按当前提醒状态和原型结构展示。

## Impact

- **Web 前端**
  - `web/src/app/system-manager/(pages)/settings/license/page.tsx`
  - `web/src/app/system-manager/enterprise/(pages)/settings/license/page.tsx`
  - `web/src/app/system-manager/enterprise/api/license_mgmt/index.ts`
- **Server 后端**
  - `server/apps/license_mgmt/services/license_service.py`
  - `server/apps/license_mgmt/services/reminder_service.py`
  - `server/apps/license_mgmt/services/license_decode_service.py`
  - `server/apps/license_mgmt/middleware/license_guard.py`
  - `server/apps/license_mgmt/tasks.py`
- **OpenSpec artifacts**
  - `openspec/changes/license-mgmt/design.md`
  - `openspec/changes/license-mgmt/specs/license-management/spec.md`
  - `openspec/changes/license-mgmt/tasks.md`

## Implementation Decisions

## Overview

`license-mgmt` 采用“系统管理公共路由壳 + 企业版真实页面实现 + 独立后端领域服务”的方式落地。社区版路由 `system-manager/(pages)/settings/license/page.tsx` 仅作为稳定入口，真实页面实现位于 `web/src/app/system-manager/enterprise/(pages)/settings/license/page.tsx`。后端能力由 `server/apps/license_mgmt` 承接，负责许可主数据、提醒配置、注册码读取、许可验签与新增资源校验。

## Key Decisions

### 1. 保持稳定入口，企业版承载真实页面

- Web 入口路径保持 `/system-manager/settings/license` 不变。
- 公共页面仅动态加载 enterprise 页面，避免把企业版业务代码直接放回公共设置页。
- 许可弹窗统一使用仓库现有 `OperateModal`，避免继续维护额外的自定义 modal 壳。

### 2. 提醒配置使用统一配置模型

- 全局默认提醒保存 `default_channel_ids`、`default_user_ids`、`default_remind_days`。
- 单许可提醒使用 `follow/custom` 模式切换；`custom` 时保存独立通知渠道、通知人员和提醒天数。
- 节点提醒保存模块级阈值和专用节点覆盖项；日志容量提醒保存 `follow/custom` 模式与阈值。
- 用户和渠道都以 ID 列表存储，保存前按当前用户可见范围校验。

### 3. 许可卡片状态直接由服务端提醒窗口判断驱动

- `LicenseService.serialize_license` 在返回 `reminder` 时同时输出 `warning` 与 `status`。
- `status=warning` 表示当前许可已进入提醒窗口；`status=healthy` 表示未进入提醒窗口。
- 前端许可卡片、剩余天数 badge 与提醒配置入口全部按该状态切换样式，不在页面层重复推导风险状态。

### 4. 资源新增拦截通过中间件 + RPC 完成

- `LicenseCreateGuardMiddleware` 先检查 `LICENSE_MGMT_ENABLED`，避免未启用环境误拦截。
- `PermissionGuardService` 根据 `LICENSE_APP_PERMISSIONS` 判断当前请求是否属于受控新增入口。
- 命中受控入口后，通过 `apps.rpc.license_mgmt.LicenseMgmt().validate_module_create_access(...)` 获取放行结果；拒绝时返回 403。

## Constraints

- 设计以当前仓库实际实现为准，不再保留旧的“待实现目录/阶段”描述。
- OpenSpec 归档前只记录已经存在的行为，不扩展尚未落地的新接口或新模块。
- 许可提醒页面样式以 `spec/prototype/系统管理/设置/许可.html` 为对齐基准，优先复用原型结构和仓库内现有组件。

## Capability Deltas

### license-management

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
- **WHEN** 请求命中 `LICENSE_APP_PERMISSIONS` 中定义的新增入口，且 RPC 校验返回 `allowed=False`
- **THEN** 中间件 MUST 返回 403，并附带拒绝原因

#### Scenario: 请求命中受控新增入口且许可有效
- **WHEN** 请求命中 `LICENSE_APP_PERMISSIONS` 中定义的新增入口，且 RPC 校验返回 `allowed=True`
- **THEN** 中间件 MUST 放行请求

## Work Checklist

## 1. License domain and route entry

- [x] 1.1 保留 `/system-manager/settings/license` 作为稳定入口，并将真实页面实现放到 enterprise 许可页中。
- [x] 1.2 建立 `server/apps/license_mgmt` 独立领域模型、服务与中间件基础结构。

## 2. License data flow

- [x] 2.1 支持注册码读取、许可导入、当前许可列表、历史许可列表和许可停用。
- [x] 2.2 提供模块授权摘要、CMDB/监控节点额度聚合、日志容量聚合结果供前端展示。
- [x] 2.3 在许可列表返回中补充提醒状态字段，供前端直接渲染健康/预警样式。

## 3. Reminder governance

- [x] 3.1 支持全局默认提醒配置的读取、保存与页面内联编辑。
- [x] 3.2 支持单许可提醒的 `follow/custom` 模式切换、回显与保存。
- [x] 3.3 支持节点提醒阈值、专用节点覆盖项和日志容量提醒的读取与保存。
- [x] 3.4 对提醒配置中的通知渠道和通知人员执行可见范围校验。

## 4. Guard and scheduled behaviors

- [x] 4.1 支持根据 `LICENSE_APP_PERMISSIONS` 匹配新增资源请求，并通过中间件触发统一许可校验。
- [x] 4.2 支持通过 RPC 返回模块新增资源是否允许的校验结果。
- [x] 4.3 提供许可到期、日志容量、节点阈值的后台提醒任务入口。

## 5. UI alignment and verification

- [x] 5.1 许可列表卡片、默认提醒面板、添加许可弹窗和许可提醒弹窗按当前原型结构收敛实现。
- [x] 5.2 许可提醒相关弹窗统一使用 `OperateModal`。
- [x] 5.3 执行 OpenSpec 状态检查，确认变更目录可被 spec-driven 流程识别。
- [ ] 5.4 执行 `cd web && pnpm lint && pnpm type-check`，确认当前前端实现通过最小门禁。
