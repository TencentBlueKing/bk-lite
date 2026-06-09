## 1. Model 层变更

- [x] 1.1 JobExecution model 新增 `callback_url` 字段（CharField, max_length=512, null=True, blank=True）
- [x] 1.2 生成并执行 migration（`python manage.py makemigrations job_mgmt && python manage.py migrate`）

## 2. 回调机制

- [x] 2.1 新建 `apps/job_mgmt/services/callback_service.py`，实现 `send_callback(execution: JobExecution)` 方法：检查 callback_url 是否存在，POST 回调数据，3 次指数退避重试（1s → 2s → 4s）
- [x] 2.2 在 `ExecutionTaskBaseService.finalize_execution()` 末尾调用 `send_callback`（sidecar/节点管理 同步执行路径）
- [x] 2.3 在 `ansible_task_callback()` 任务完成更新状态后调用 `send_callback`（Ansible 异步执行路径）

## 3. NATS 接口实现

- [x] 3.1 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_script_execute`：参数校验、高危命令检测、创建 JobExecution（trigger_source=api）、调用 execute_script_task，返回 task_id
- [x] 3.2 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_file_distribute`：校验 file_ids、高危路径检测、创建 JobExecution（trigger_source=api）、调用 distribute_files_task，返回 task_id
- [x] 3.3 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_status_batch_query`：根据 task_ids 批量查询 JobExecution 状态，不存在的 ID 返回 status=not_found
- [x] 3.4 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_detail_query`：根据 task_id 查询单个 JobExecution 完整信息含 execution_results

## 4. REST 文件上传接口

- [x] 4.1 新建 `apps/job_mgmt/views/open_api.py`，实现 `OpenFileUploadView`：使用 `APISecretAuthBackend` 鉴权（`Authorization: Token <api_secret>`），接收 multipart/form-data，存储到 JetStream Object Store，创建 DistributionFile 记录，返回 file_id、file_key、original_name
- [x] 4.2 在 `apps/job_mgmt/urls.py` 注册路由 `POST /api/job_mgmt/open/upload_file`

## 5. 测试

- [x] 5.1 为 4 个 NATS handler 编写单元测试（mock NATS 调用和 task 执行）
- [x] 5.2 为文件上传 REST 接口编写单元测试（mock JetStream 和 APISecretAuthBackend）
- [x] 5.3 为 callback_service 编写单元测试（mock requests.post，验证重试逻辑）
- [x] 5.4 运行 `make test` 确保全量测试通过

## 6. 调用文档

- [x] 6.1 编写接口调用文档，包含：5 个接口的请求/响应 schema、鉴权方式说明、回调机制说明、调用流程示例
