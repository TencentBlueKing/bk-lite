## Context

当前 `DistributionFile` 模型仅记录 `original_name`、`file_key`、`created_at`，所有文件统一在 7 天后被 `cleanup_expired_distribution_files_task` 清理。第三方应用需要上传永久保存的文件（如补丁包、配置文件），当前机制无法满足。

**现有代码位置**：
- Model: `server/apps/job_mgmt/models/distribution_file.py`
- Upload API: `server/apps/job_mgmt/views/open_api.py` → `OpenFileUploadView`
- Cleanup Task: `server/apps/job_mgmt/tasks.py` → `cleanup_expired_distribution_files_task`

## Goals / Non-Goals

**Goals:**
- 仅对外 API 支持上传时指定文件永久保存
- 永久文件不被定时清理任务删除
- 向后兼容，现有调用方无需修改

**Non-Goals:**
- 不实现文件过期时间自定义（如 30 天、90 天）
- 不实现永久文件的配额限制
- **不修改内部文件上传接口**（`DistributionFileViewSet` 等）- 内部统一使用临时保存策略

## Decisions

### 1. 使用布尔字段 `is_permanent` 而非过期时间字段

**选择**: `is_permanent: BooleanField(default=False)`

**备选方案**:
- `expires_at: DateTimeField(null=True)` - null 表示永久

**理由**:
- 需求明确只需要"永久/临时"两种状态
- 布尔字段语义清晰，查询简单
- 避免过度设计，后续如需自定义过期时间可再扩展

### 2. API 参数使用 `permanent` 而非 `is_permanent`

**选择**: 请求参数名为 `permanent`（布尔值）

**理由**:
- API 参数命名习惯不带 `is_` 前缀
- 与内部字段名 `is_permanent` 区分，保持各层命名惯例

### 3. 参数通过 form-data 传递而非 query string

**选择**: `permanent` 作为 multipart/form-data 的一部分

**理由**:
- 与现有 `file` 字段保持一致的传递方式
- 避免 URL 参数与 body 混用

### 4. 仅对外 API 提供永久保存参数

**选择**: 只在 `OpenFileUploadView`（对外 API）添加 `permanent` 参数

**备选方案**:
- 所有上传接口统一支持 `permanent` 参数

**理由**:
- 内部使用场景（如 Playbook 执行临时文件）无需永久保存
- 限制永久文件入口，降低存储滥用风险
- 内部接口保持简单，减少维护成本

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 永久文件无限增长占用存储 | 保留手动删除接口；后续可增加配额/告警 |
| 误设为永久导致无法清理 | 默认 `permanent=false`，需显式指定 |
| 数据库迁移影响线上 | 新增字段有默认值，迁移无锁表风险 |
| 内部接口无法使用永久保存 | 设计如此，内部场景无此需求 |
