## Context

节点管理模块已有：
- `Executor` 类（`apps/rpc/executor.py`）：通过 NATS 远程执行节点命令
- `update_node` API：允许用户编辑节点名称和组织
- Celery 任务机制：用于异步处理

Sidecar 配置文件位置：
- Linux: `/etc/sidecar/sidecar.yaml`
- Windows: `C:\bklite\fusion-collectors\sidecar.yaml`

sidecar.yaml 中相关字段：
- `node_name`: 节点名称
- `tags`: 标签数组，组织使用 `"group:<org_id>"` 格式

## Goals / Non-Goals

**Goals:**
- 用户编辑节点名称/组织后，自动同步到节点 sidecar.yaml
- 异步同步，不阻塞 API 响应
- 同步失败不影响数据库更新（best-effort）

**Non-Goals:**
- 不提供通用配置编辑 API（只同步 name/organizations）
- 不支持批量节点同步
- 不处理反向同步（节点 → 数据库）

## Decisions

### 1. 异步同步 vs 同步

**选择**: 异步（Celery 任务）

**原因**:
- 节点可能离线或响应慢，同步调用会阻塞 API
- DB 更新是主要操作，配置同步是附加操作
- 同步失败不应导致 API 失败

### 2. 组织同步格式

**选择**: 使用 sidecar 现有的 tags 机制

```yaml
tags: ["zone:1", "group:org1", "group:org2", "install_method:auto"]
```

**逻辑**:
1. 读取现有 tags
2. 过滤掉所有 `group:` 前缀的 tag
3. 添加新的 `group:<org_id>` tags
4. 保留其他 tags（zone, install_method, node_type）

### 3. 代码组织

```
server/apps/node_mgmt/
├── services/
│   └── sidecar_config.py     # SidecarConfigService.sync_node_properties()
├── tasks/
│   └── sidecar_config.py     # sync_node_properties_to_sidecar Celery task
└── views/
    └── node.py               # update_node action 触发异步任务
```

### 4. 流程

```
User PATCH /nodes/{id}/update/
  → DB 更新 (node.name, NodeOrganization)
  → API 返回成功
  → Celery 任务异步执行:
      → Executor 读取 sidecar.yaml
      → 更新 node_name 字段
      → 更新 tags 中的 group 项
      → Executor 写回 sidecar.yaml
      → Executor 重启 sidecar 服务
```

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 节点离线导致同步失败 | 记录日志，不影响 DB 更新 |
| 同步延迟 | Celery 任务优先级可调整 |
| DB 和节点配置不一致 | 日志记录失败，便于排查 |

## Rejected Alternatives

### 独立配置编辑 API

初始方案考虑提供 `PATCH /nodes/{id}/sidecar-config/` 允许任意配置编辑。

**放弃原因**: 产品需求明确后，核心需求是 name/organizations 同步，而非通用编辑器。通用编辑器增加复杂度但使用场景有限。
