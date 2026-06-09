## Context

当前 `DistributionFile` 模型没有 `team` 字段，导致文件上传后无法追踪归属团队。删除接口只校验 `file_id + file_key`，任何持有有效 API Secret 的用户都可以删除任意文件。

现有代码库中，其他模型（如 `Script`、`Playbook`、`ScheduledTask`）都有 `team` 字段，并在操作时进行组校验。

## Goals / Non-Goals

**Goals:**
- 为 `DistributionFile` 添加 `team` 字段，记录文件归属
- 上传时自动记录当前用户的 team（取 `user.group_list[0]`）
- 删除时校验文件的 team 与当前用户的 team 一致

**Non-Goals:**
- 不迁移历史数据（`team=None` 的记录保持原样）
- 不支持文件跨组共享
- 不修改内部 `DistributionFileViewSet`（仅修改 open API）

## Decisions

### 1. team 字段类型：IntegerField (nullable)

**选择**: `team = models.IntegerField(null=True, blank=True)`

**理由**:
- 与 `UserAPISecret.team` 类型一致（IntegerField）
- 允许 null 以兼容历史数据
- 简单直接，不需要 JSONField（文件只属于一个 team）

**备选方案**:
- JSONField（支持多 team）- 过度设计，当前需求不需要

### 2. team 来源：user.group_list[0]

**选择**: 从 `request.user.group_list[0]` 获取

**理由**:
- `APISecretAuthBackend` 已将 `UserAPISecret.team` 设置到 `user.group_list`
- 与其他接口保持一致的取值方式

### 3. 删除校验失败的响应：404

**选择**: 文件不存在或 team 不匹配时返回 404

**理由**:
- 不泄露文件是否存在的信息（安全考虑）
- 与当前行为一致（文件不存在时 continue，最终返回 deleted=0）

### 4. 历史数据处理：不迁移

**选择**: `team=None` 的历史记录保持原样，新记录必须有 team

**理由**:
- 用户明确要求不处理旧数据
- 历史文件可能已被使用或清理，迁移意义不大

**影响**: 历史文件（`team=None`）无法被任何人通过 open API 删除（因为 team 校验会失败）

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 历史文件无法通过 open API 删除 | 可通过内部 admin 或定时清理任务处理 |
| `user.group_list` 为空时上传失败 | 在上传接口添加校验，返回明确错误 |
