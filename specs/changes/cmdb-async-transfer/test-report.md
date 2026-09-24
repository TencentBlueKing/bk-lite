# CMDB 异步导入导出实施测试记录

日期：2026-09-21；最近回归：2026-09-22。对应 [设计与验收矩阵](./spec.md)。

## 实施范围

- 资产页实例导入/导出改为 HTTP 202 接纳、个人任务抽屉与后台执行；模板和旧同步接口保留。
- 用户稳定主键隔离，导入导出跨模型合计 5 条、7 天；本人 1 个活动任务、全局 2 个执行占用、同模型导入串行。
- MinIO 复用 `cmdb-config-file`，仅管理 `transfer/` 前缀；每日 03:00 清理，维护/补发每分钟运行。
- 新增数据库迁移 `0056_async_transfer_tasks`；导入和导出直接使用现有 Celery 默认队列和 Worker。
- 导入按 200 行匹配候选、实例操作账本与审计 Outbox、受控错误报告；导出延续 500 行游标查询和顺序写 Excel。
- 文件下载同源鉴权；检查生成授权及当前实例/关联对端权限，文件传输端点独立使用 300 秒代理预算。

## 自动化验证

| 范围 | 结果与证据 |
|---|---|
| 后端任务 + 既有导出/导入相关回归 + 启动顺序 | 127 passed、5 deselected；包括默认队列补发、首次上传初始化、存储错误诊断和重提替换旧记录回归 |
| 新增 10 个后端服务/任务/HTTP 模块覆盖率 | 92%；包括状态机、授权、文件、校验、导入、执行、清理、后台发布、Celery 入口和 HTTP View |
| 前端轮询/抽屉/文件代理预算 | 7 passed，包含当前页提交、接纳前打开抽屉、失败恢复配置及复用幂等键 |
| Web 类型检查 | `pnpm type-check` 退出 0 |
| 本次 Web 文件定向 ESLint | 退出 0 |
| 真实图库/MinIO 导出压测 | 10,000 台主机，30,000 / 90,000 条关系；每档预热 1 次 + 正式 3 次，全部成功并清理，见压测报告 |
| Python 新增模块 Black/isort/Flake8 | 通过，使用仓库 150 字符规则；只格式化本次新增文件 |
| 新库迁移 | 独立 `/tmp/cmdb-transfer-migration-check.sqlite3` 执行 `manage.py migrate cmdb` 成功，0056 已应用 |
| 重复迁移 | 再执行 `migrate cmdb`：No migrations to apply |
| 模型/迁移一致性 | `makemigrations cmdb --check --dry-run`：No changes detected |

后端主要命令（server 目录，开发环境变量通过命令注入，不使用真实凭据）：

```sh
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
.venv/bin/python -m pytest \
  apps/cmdb/tests/test_transfer*.py \
  apps/cmdb/tests/test_instance_export_service.py \
  apps/cmdb/tests/test_export_helpers.py \
  apps/cmdb/tests/test_instance_service_import_export.py \
  apps/core/tests/test_release_startup_service.py \
  -k 'not test_check_asso_mapping_1n_existing and not test_check_asso_mapping_1n_ok and not test_check_asso_mapping_n1_existing and not test_check_asso_mapping_11_ok and not test_check_asso_mapping_invalid_mapping' \
  -o addopts='' --nomigrations --no-cov -q
```

覆盖率另对 `apps.cmdb.services.transfer_{service,authorization,files,validation,import,execution,maintenance,dispatch}`、
`apps.cmdb.tasks.transfer` 及 `apps.cmdb.views.transfer_task` 启用 `--cov`，不是整个 CMDB 的覆盖率。

前端命令（web 目录，Node 24）：

```sh
pnpm exec vitest run src/app/cmdb/hooks/__tests__/useTransferTasks.test.tsx \
  src/app/cmdb/components/transfer/__tests__ \
  src/utils/__tests__/transferProxyTimeout.test.ts
pnpm type-check
```

关键场景：

- 同幂等键重放、内容冲突；源文件上传失败不淘汰旧记录；来源文件摘要检查。
- 同域他人/跨域同名隔离、用户停用、功能权限/组织/规则拒绝、模型隐藏、模板变化。
- 权限规则仅顺序变化不使任务失效；自由标签新增候选项不误判模板变化，严格模式仍检查候选项。
- 全局和个人配额、同模型导入互斥、重复领取、领取后取消拒绝、过期令牌不能更新/完成。
- Broker 失败补发、排队超时、失联占用保护、管理员显式解除、中断导入不重放。
- 文件删除失败保留对象键、孤儿年龄与活动任务保护、配置文件桶和前缀隔离。
- 真实 Excel 读回、行数/列数/公式/重复表头/坏 ZIP、文件写入字节预算、字符串不能成为公式。
- 导入新增/更新/文件内重复、全部行无效、部分成功审计、源行号、实例与关联分别计数。
- 重复导入已有关系单独计数，不重复写边；异步关系检查使用有界查询，不回退全模型扫描。
- 导出后实例组织变化拒绝旧文件下载；内部对象键与授权快照不出现在任务列表。
- 前端接纳状态、轮询终止、页面隐藏与 KeepAlive 切离暂停、重新可见刷新、取消调用和当前页 UUID 提交。
- 受控日志完整渲染不含敏感哨兵，保留原异常与 traceback；外部存储故障不改变任务接纳事实。

## 基线与环境限制

1. 全仓 `pnpm lint` 未通过：首次检查 32 errors、94 warnings，其中本次 Drawer 的 1 处缩进已修复并通过定向检查。
   剩余错误来自既有 APM 类型别名、日志抽取页面等无关文件，未修改它们。
2. 完整相关后端回归首次出现 5 条旧 `test_check_asso_mapping_*` 失败：测试替身没有隔离当前关系校验的图库访问，
   尝试外部 FalkorDB 时连接不可用。相关生产方法和旧用例不属于本次修改；保留失败证据后定向排除，未将其计为通过。
3. pytest 全量历史迁移存在既有 SQLite 兼容问题，因此功能回归使用 `--nomigrations`；本次另外对 CMDB 迁移链执行了真正的新库与重复迁移验证。
4. 最初没有隔离的真实图库、MinIO、Broker 和多副本 Worker 验证环境。单元回归使用真实 Django ORM、真实 Excel、真实 HTTP View/执行编排，
   外部身份/图库和对象存储使用替身，实例写入在现有公开服务边界验证调用与账本；不能据此声称已证明生产数据库行锁竞争或大文件性能。
   2026-09-22 另外使用现有 MinIO 完成临时 Excel 写入/读回/删除验证，并通过随机隔离图完成真实 FalkorDB/MinIO 的
   1 万台主机关联导出单任务压测，见 [压测报告](./benchmark-report.md)；仍不等同于真实队列和多 Worker 部署联调。

本机原始输出位于 `/tmp/cmdb-transfer-*.log`；这是本次验证证据，不提交包含运行环境信息的原始日志。

## 2026-09-21 用户反馈回归

- 工具栏顺序调整为「新增、导出、更多、导入导出记录、数据订阅」，同步修正响应式宽度测量。
- **接纳慢的已复现原因**：`on_commit` 回调同步调用 Celery 发布，仍阻塞 HTTP。
  回归在真实 HTTP 提交及提交回调处注入 400ms 发布等待，修复前接纳耗时 404ms，修复后通过 `<200ms` 断言，
  并确认后台发布实际启动。现在仅在提交成功后启动最多 2 个发布线程，不积压内存任务；持久化补发兜底。
- **建连重试**：仅指定 `retry=False` 未关闭 Kombu 建连重试。故障注入修复前实际尝试 2 次、耗时约 2 秒，
  修复后只尝试 1 次。连接/套接字/发布设置 2 秒预算，不把它宣传为含 DNS 和授权查询的端到端硬超时。
- **补发放大**：Broker 故障时原维护循环会逐条尝试最多 500 次；现在首次发布失败后停止本轮发送，
  继续处理排队超时。回归验证第二条任务不被错误标成已尝试、旧任务仍正常超时失败。
- **排队与最终队列方案**：旧实现投递到 `cmdb_transfer`，普通 Worker 收不到。按用户最新要求，
  已取消专用路由、Worker 配置和启动入口，直接投递默认 `celery` 队列。
  真实 Celery 发布 + Kombu memory transport 验证普通队列收到任务、旧专用队列不再收到新消息。
  导入/导出两类旧排队记录均通过维护入口补发，消息复用原任务 ID，并可进入现有注册任务的执行入口。
- 原端到端回归在测试事务中未执行提交回调，并直接调用执行入口，遗漏了请求线程发布阻塞和开发队列接线。
  本轮补齐提交回调、真实消息路由、慢发布背压、发布失败释放容量、敏感日志和启动入口测试。
- 尚未收到现场 Worker 启动参数，也未访问现场 Broker 或数据库；不能把队列配置缺口当作现场排队原因的最终证明。
  更新后如仍排队，按开发说明检查默认队列消费者、注册任务、环境配置与未解除的执行占用。

## 2026-09-22 首次上传失败回归

- 用户日志表明默认 Worker 已接收任务，Excel 生成完成（1 行、约 1.07 秒），随后 `put_object` 抛出 S3Error。
  本机以用户同一 Python 环境只读检查既定 `cmdb-config-file` 桶，确认不存在。
- 流式上传复用了 MinIO 客户端，却绕过 `MinioBackend._save` 的 `MINIO_BUCKET_CHECK_ON_SAVE` 行为。
  先用缺桶客户端复现 NoSuchBucket，再补回运行期首次保存检查：只初始化 `cmdb-config-file`，每个存储实例检查一次，
  不修改启动流程、不增加额外桶或公开策略；并发创建仅接受 `BucketAlreadyOwnedByYou`，权限失败仍原样抛出。
- 实际 MinIO 验证：通过修复后的 `TransferFiles.put` 初始化既定桶，写入随机临时路径下的 4,828 字节 Excel，
  读回字节一致，随后删除该测试对象。没有操作业务对象，桶保留用于正常配置文件和导入导出。
- S3 错误记录固定白名单错误码、对象存储阶段和原始 traceback；不记录响应正文、对象路径或签名信息。
  导出失败状态向用户区分缺桶、权限、认证和签名问题；未知错误码统一归类，保留导入中断的待核对语义。
- 7 项新增回归覆盖首次初始化、重复上传不重复创建、并发已创建、创建权限失败及恢复、关闭保存检查、
  已知与未知 S3 错误日志、原始异常身份和敏感哨兵不泄露。Black/isort/Flake8 与相关后端完整回归通过。
- Celery 的 `succeeded … None` 表示执行包装函数返回，业务成功以 `CmdbTransferTask.status` 为准；
  已捕获并持久化的文件存储失败不应被该 Celery 日志误解成文件已保存。

## 2026-09-22 重新提交替换旧记录

- 点击失败导出的“重新提交”后，新任务持久化接纳（202）与旧记录标记待清理处于同一事务；旧记录立即从列表移除，旧文件沿用日清。
- 提交校验、配额或归属检查失败时保留旧记录；替换发生在 5 条历史淘汰之前，不误删另一条历史。
- 新任务保留内部来源 ID，同一幂等键重复请求返回同一新任务；旧记录日清后仍支持重放，同键不能替换另一条失败任务。
- HTTP 回归覆盖接纳后旧记录不可见、响应丢失后的重放、字段校验失败保留原记录；服务回归覆盖历史上限、旧文件清理引用、跨用户拒绝和请求冲突。

## 部署环境完整验收（尚未执行）

1. 在独立验收环境应用迁移；确认已有 `cmdb-config-file` 私有桶可用，无需建新桶；更新并重启现有 Worker 和 Beat，无需新增 Worker。
2. 确认当前 Beat 中维护任务每分钟、清理任务每日 03:00；两者与导入导出共享默认 Worker，验证忙碌时调度延迟和协作截止检查。
3. 两个同域用户和两个跨域同名用户分别提交/查询/下载。并发提交同用户请求、部署两个默认 Worker 副本，断言导入导出总占用不超过 2、同模型导入不重叠。
4. 通过真实 UI 导入有合法/非法行及关联的文件，核对图库、操作账本、变更审计和错误报告；确认刷新浏览器仍能找到任务。
5. 在导入写入后中断 Worker；确认显示待核对、不重跑、不释放占用、不清理活动文件。默认 threads 池不能按单任务强杀；核对执行确已停止和副作用后执行文档中的 reconcile_transfer 命令。
6. 模拟 Broker/MinIO 短时不可用，恢复后检查待派发补偿与下一次文件删除补偿。预置同桶配置文件，确认日清没有删除它。
7. 以 1 千/1 万/10 万实例、0/多关联及宽字段组合测量生成耗时、下载耗时、峰值 RSS、临时磁盘与图查询数。超限应整体失败，无截断文件。
8. 检查外层网关上传限制（至少容纳 20 MiB 文件与 multipart 开销）及文件端点传输超时；慢速网络上传/下载测试须超过 60 秒。
9. 校验 7 天边界即时不可见、创建第 6 条淘汰最早终态、日清删除所有过期终态关联文件。孤儿扫描每次最多 1000 个，保存游标跨日推进。

这些验收步骤属于上线条件；尚未把实现部署到生产环境。
