# Historical Superpowers change: 2026-06-12-job-mgmt-file-ttl

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-12-job-mgmt-file-ttl-design.md

> 日期：2026-06-12
> 范围：`server/apps/job_mgmt`

## 背景

`job_mgmt` 开放接口的文件上传（`POST /api/v1/job_mgmt/api/open/upload_file`）原先用
`permanent` 布尔参数区分「永久文件」与「7 天后清理的临时文件」，7 天为硬编码，且清理任务
每天 02:00 才扫描一次。需求是：

1. 让调用方可以**按天配置过期时间**，而不是固定 7 天。
2. **取消「永久保留」选项**——所有上传文件都必须有过期时间。
3. 后台任务**每天 00:00 扫描，删除已过期文件**。

## 决策

- 过期粒度：**按天**（`expire_days`，整数）。
- 不再有永久文件：`is_permanent` 字段移除。
- 清理时效：每天 00:00 一次全量扫描即可（无需精确到秒的即时删除）。
- 存量数据迁移：**统一回填**，所有现存记录 `expire_at = created_at + 7 天`，无宽限期。

## 方案

### 1. 数据模型与迁移

`DistributionFile`（`models/distribution_file.py`）：

- **移除** `is_permanent`。
- **新增** `expire_at = DateTimeField(db_index=True)`，**非空**。过期时间的唯一来源。
  加索引，供清理任务高效过滤。
- 更新 docstring，去掉永久/临时的描述。

迁移 `0009_distributionfile_expire_at`，按顺序：

1. `AddField` `expire_at`，先 `null=True`。
2. `RunPython` 回填：所有现存记录 `expire_at = created_at + timedelta(days=7)`；反向为 no-op。
3. `AlterField` `expire_at` → `null=False`。
4. `RemoveField` `is_permanent`。

### 2. 上传接口契约

`OpenFileUploadView.post`（`views/open_api.py`）：

- **移除** `permanent` 参数。
- **新增** `expire_days`（可选）。解析为 int，默认 **7**。校验：整数且 `1 <= expire_days <= 365`，
  否则返回 `400 {"detail": "expire_days 非法"}`。
- 计算 `expire_at = timezone.now() + timedelta(days=expire_days)`，落库。
- 响应不变：`{file_id, file_key}`。
- 历史调用方若仍传 `permanent`，静默忽略（内部第三方集成，可接受）。

### 3. 清理任务与调度

`cleanup_expired_distribution_files_task`（`tasks.py`）：

- 过滤条件由 `created_at__lt=threshold, is_permanent=False` 改为 `expire_at__lte=timezone.now()`。
- S3 删除 + DB 删除循环、日志、成功/失败计数不变。

调度（`config.py`）：`crontab(hour="2", minute="0")` → `crontab(hour="0", minute="0")`（每天 00:00）。

### 4. 测试与文档

- 重写 `tests/test_open_upload.py` 中受影响的 3 个用例：删除 `permanent` 相关，新增
  (a) 默认 `expire_days` → `expire_at ≈ now+7d`；(b) 显式 `expire_days=30`；(c) 非法 `expire_days` → 400。
- 新增清理任务测试：已过期记录被删除、未到期记录保留。
- 更新 `docs/open_api.md` §4：用 `expire_days`（可选，默认 7，范围 1–365）替换 `permanent`，
  并说明所有文件都会过期、无永久选项。

## 边界情况

- `expire_days` 非整数 / 0 / 负数 / 超过 365 → 400。
- 移除参数属于向后不兼容的删除，但仅影响传 `permanent` 的调用方，且会被静默忽略，可接受。

## 受影响文件

- `models/distribution_file.py`
- `migrations/0009_distributionfile_expire_at.py`（新增）
- `views/open_api.py`
- `tasks.py`
- `config.py`
- `tests/test_open_upload.py`
- `docs/open_api.md`
