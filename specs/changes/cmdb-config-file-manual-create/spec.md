# Cmdb Config File Manual Create

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/cmdb-config-file-manual-create/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

CMDB 配置文件功能当前只支持通过采集任务（Stargazer 远程读取）获取配置文件版本。用户无法在页面上手动录入配置文件内容，导致以下问题：

- 没有远程采集条件的主机（如网络隔离、未部署 Agent）无法管理配置文件
- 用户想要备份或登记一份配置文件，必须先创建采集任务再触发采集，流程繁琐
- 权限模型挂在采集任务上，逻辑间接且不直觉——配置文件是实例的附属物，权限应该跟实例走

## What Changes

- 在主机实例详情页的"配置文件" Tab 表格上方新增"手动新增"入口
- 用户填写文件路径和文件内容（粘贴或上传文本文件），提交后直接创建一个配置文件版本记录
- 手动新增的记录与采集记录共存于同一版本列表，支持 diff 对比
- 通过 `collect_task` 是否为空区分来源（手动/采集），前端表格新增"来源"列展示
- 配置文件权限模型从"采集任务维度"改为"实例维度"：对实例有 View 权限即可查看其所有配置文件

## Capabilities

### New Capabilities

- `cmdb-config-file-manual-create`: 支持在主机实例详情页手动新增配置文件，填写文件路径和内容直接创建版本记录。

### Modified Capabilities

- 配置文件权限控制从采集任务维度改为实例 View 权限维度。

## Impact

- **后端 Model**:
  - `server/apps/cmdb/models/config_file_version.py` — `collect_task` 改为可空
- **后端 API**:
  - `server/apps/cmdb/views/config_file.py` — 新增 `create_manual` action；权限逻辑从 `filter_queryset_by_task_permission` 改为校验实例 View 权限
  - `server/apps/cmdb/services/config_file_service.py` — 新增手动创建逻辑；去掉或改造 `filter_queryset_by_task_permission`
- **前端页面**:
  - `web/src/app/cmdb/(pages)/assetData/detail/configFiles/page.tsx` — 新增按钮、手动新增抽屉表单、来源列
  - `web/src/app/cmdb/api/configFile.ts` — 新增 `createManualConfigFile` API 方法
  - `web/src/app/cmdb/types/configFile.ts` — 补充类型定义
- **不在本次范围**:
  - 不扩展配置文件功能到非 host 模型
  - 不做手动编辑已有版本功能（只新增，不修改）
  - 不改变采集任务本身的逻辑

## Implementation Decisions

## Overview

在现有配置文件版本管理体系上，新增"手动创建"通道。手动记录和采集记录共用同一张表、同一套版本管理和 diff 能力，仅通过 `collect_task` 是否为空区分来源。权限统一改为基于实例 View 权限。

## Architecture

```
┌─────────────┐                    ┌─────────────┐
│  前端表单    │  POST create_manual │   Django    │
│  (Drawer)   │───────────────────▶│   ViewSet   │
└─────────────┘                    └──────┬──────┘
                                          │
                        ┌─────────────────┼─────────────────┐
                        ▼                 ▼                 ▼
                 校验实例权限      计算hash/去重      存内容到MinIO
                        │                 │                 │
                        └─────────────────┼─────────────────┘
                                          ▼
                                  ConfigFileVersion
                                  (collect_task=NULL)
```

## Key Decisions

### 1. 不新增 source 字段

通过 `collect_task` 是否为空判断来源，不额外加字段：
- `collect_task` 有值 → 采集来源
- `collect_task` 为 NULL → 手动来源

理由：减少 migration 复杂度，现有字段已可区分。

### 2. 权限模型改为实例维度

**之前**：通过 `collect_task.team` + task 级别权限规则过滤
**改后**：校验用户对 `instance_id` 对应实例的 View 权限

理由：
- 配置文件 Tab 本身在实例详情页内，用户能进来就有实例权限
- 手动记录没有 collect_task，无法走旧权限逻辑
- 实例维度更直觉："看到主机 = 看到它的配置文件"

实现：去掉 `filter_queryset_by_task_permission`，在每个接口入口处调用现有的 `check_instance_permission(request, instance, VIEW)` 校验。

### 3. 同路径版本合并策略

手动和采集记录按 `instance_id + file_path` 聚合为同一个文件的版本历史：
- 同路径 + 同内容（content_hash 相同）→ 拒绝，返回"内容无变化"
- 同路径 + 不同内容 → 创建新版本，追加到版本列表
- 全新路径 → 创建新文件记录

### 4. collect_task 改为可空

`ConfigFileVersion.collect_task` 从 `NOT NULL FK` 改为 `NULL=True, blank=True, on_delete=SET_NULL`。现有采集逻辑不受影响（仍然传入 task）。

## API Design

### 新接口：手动创建配置文件版本

```
POST /cmdb/api/config_file_versions/create_manual/
```

Request:
```json
{
  "instance_id": "host-xxx",
  "model_id": "host",
  "file_path": "/etc/nginx/nginx.conf",
  "content": "server {\n  listen 80;\n  ...\n}"
}
```

Response (success):
```json
{
  "result": true,
  "data": {
    "id": 123,
    "version": "1716854400000",
    "file_name": "nginx.conf",
    "file_path": "/etc/nginx/nginx.conf"
  }
}
```

Response (内容无变化):
```json
{
  "result": false,
  "message": "该文件内容与最新版本相同，无需重复上传"
}
```

### 现有接口改造

所有配置文件接口（list、content、diff、file_list、destroy）：
- 去掉 `get_filtered_queryset` 中的 `filter_queryset_by_task_permission`
- 改为在入口处校验实例 View 权限
- `file_list` 不再按 `visible_paths` 做二次过滤

## Frontend Design

### 入口

配置文件 Tab 表格上方右侧新增"手动新增"按钮。

### 抽屉表单

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| 文件路径 | Input | 是 | 非空，以 `/` 开头 |
| 文件内容 | Textarea + Upload | 是 | 非空，≤5MB |

上传文件时使用 `FileReader` 读取文本内容填入 textarea。

### 表格改动

新增"来源"列，基于接口返回的 `collect_task_id` 判断：
- 有值 → Tag: "采集"
- 无值 → Tag: "手动"

## Migration

一次 migration：`ConfigFileVersion.collect_task` 加 `null=True, blank=True`，`on_delete` 改为 `SET_NULL`。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-28
```

## Work Checklist

## Tasks

### 1. 后端 Model 改造

- [x] `server/apps/cmdb/models/config_file_version.py`：`collect_task` 字段改为 `null=True, blank=True, on_delete=models.SET_NULL`
- [ ] 生成并应用 migration：`python manage.py makemigrations cmdb && python manage.py migrate`（需在有依赖环境中执行）

### 2. 后端权限改造

- [x] `server/apps/cmdb/views/config_file.py`：去掉 `get_filtered_queryset` 方法中对 `filter_queryset_by_task_permission` 的调用
- [x] 新增实例权限校验工具方法：根据 `instance_id` + `model_id` 调用现有的 `check_instance_permission` 校验 View 权限
- [x] 在 `list`、`content`、`diff`、`file_list`、`destroy` 接口入口处加入实例权限校验
- [x] `file_list` 接口去掉 `visible_paths` 二次过滤逻辑，直接返回 `ConfigFileService.get_file_list(instance_id)` 结果

### 3. 后端新增手动创建接口

- [x] `server/apps/cmdb/views/config_file.py`：新增 `create_manual` action（`POST`）
- [x] 接口逻辑：
  - 校验实例权限（Edit 或 Operate）
  - 校验 `file_path` 非空
  - 从 `file_path` 提取 `file_name`（复用 `extract_file_name`）
  - 生成 `version`（当前时间戳毫秒）
  - 计算 `content_hash`（SHA256）
  - 查重：同 `instance_id + file_path` 最新成功版本 hash 相同则返回"无变化"
  - 存储内容到 MinIO（复用 `save_content` + `build_object_key`）
  - 创建 `ConfigFileVersion` 记录：`collect_task=None, status="success"`
  - 返回新记录信息
- [x] `server/apps/cmdb/services/config_file_service.py`：新增 `create_manual_version` 类方法封装上述逻辑

### 4. 后端 file_list 接口适配

- [x] `ConfigFileService.get_file_list` 确认对 `collect_task=None` 的记录正常返回
- [x] 接口返回字段中补充 `collect_task_id`（已有），前端用来判断来源

### 5. 前端 API 层

- [x] `web/src/app/cmdb/api/configFile.ts`：新增 `createManualConfigFile` 方法，调用 `POST /cmdb/api/config_file_versions/create_manual/`

### 6. 前端页面改造

- [x] `web/src/app/cmdb/(pages)/assetData/detail/configFiles/page.tsx`：
  - 表格上方右侧新增"手动新增"按钮
  - 新增手动新增 Drawer 组件（文件路径 Input + 文件内容 Textarea + 上传文件按钮）
  - 表单校验：文件路径必填且以 `/` 开头，内容必填且 ≤5MB
  - 提交成功后刷新列表
  - 表格 columns 新增"来源"列（根据 `collect_task_id` 是否有值显示 Tag）
  - 空状态文案修改："当前实例暂无配置文件采集记录" → "当前实例暂无配置文件记录"

### 7. 前端类型补充

- [x] `web/src/app/cmdb/types/configFile.ts`：补充 `CreateManualConfigFileParams` 接口类型

### 8. 测试验证

- [x] 后端：手动创建接口单测（正常创建、内容重复、权限拒绝）
- [x] 前端：手动新增 → 列表刷新 → 查看内容 → 版本对比，端到端验证
