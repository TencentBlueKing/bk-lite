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
