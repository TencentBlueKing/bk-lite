# MLOps 模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/mlops/`，以及直接相连的 MinIO、MLflow、Webhookd、训练/Serving 容器与 Celery 边界。
> 分析方式：按“数据集—发布制品—训练运行—模型事实—服务部署—在线推理”完整模块分析。六种算法是同一生命周期的能力变体，不按大文件或单个 tech-debt 拆成六份报告。

## 1. 结论摘要

MLOps 当前已经不是算法配置 CRUD，而是一个跨 Django、对象存储、运行时控制器、训练容器和 MLflow 的生命周期控制面。模块支持异常检测、时序预测、日志聚类、文本分类、图片分类和目标检测六类算法，每类都复制了一套 Dataset、TrainData、DatasetRelease、TrainJob、Serving、ViewSet 和任务代码。

当前实现有可继续深化的可靠性基础：团队 scope 与 dataset version scope 校验；训练状态条件更新；流式下载训练文件和模型制品；TrainData 文件引用保护与清理重试；不可变 DatasetRelease；TimeSeries 已引入 runtime generation、查询 token、清理 intent 和孤儿对账。这些机制证明正确方向是统一生命周期协议，而不是简单删除状态或把所有外部调用塞进 View。

最需要优先处理的结构性问题有两类：

- **不受控制品与执行边界**：图片 ZIP 直接 `extractall`，没有路径、文件数、展开字节、压缩比和文件类型预算；算法镜像允许 tag 且默认 `latest`，训练容器同时获得共享 MinIO 长期凭据。
- **生命周期没有稳定运行身份**：DatasetRelease 重试复用同一行且没有 generation；TrainJob 没有 TrainingRun/attempt，靠 MLflow 最新 run 和数量启发式关联；Serving 直接同步控制容器；旧 worker、超时请求和部分成功无法可靠 fencing 或对账。

短期不建议拆微服务。先在同一 Django app 内建立 `AlgorithmCapabilityRegistry`、`DatasetPublishRun`、`TrainingRun`、`ServingDeployment`、`RuntimeWorkCoordinator`、`ArchiveSandboxBudget` 和 `InferenceBudgetGateway`，让六类算法只提供 schema、packager 和 train/serve/predict adapter，共享一套持久生命周期协议。

## 2. 模块规模与职责边界

本次统计生产 Python 约 21,345 行（排除 migrations/tests），测试相关 Python 文件 44 个，HTTP/NATS router 36 个。六个 ViewSet 主文件分别约 1,300—2,100 行，规模本身不是根因；真正的维护成本来自相同生命周期在 models、serializers、views、tasks 和 MLflow/Webhook 适配中被复制六遍。

| 能力域 | 当前实现 | 应拥有的事实 |
|---|---|---|
| 算法目录 | AlgorithmConfig + 六套常量/映射 | capability id、schema、image digest、资源策略 |
| 数据集 | 六套 Dataset / TrainData / Release | typed dataset revision、source digest、团队 scope |
| 发布 | Celery task + 本地临时目录 + ZIP/CSV/JSON | DatasetPublishRun、lease/token、制品 digest、预算结果 |
| 训练 | TrainJob status + Webhook container | TrainingRun、attempt、输入 digest、runtime identity |
| 模型事实 | MLflow experiment/run/model | MLflow run id、model version、artifact digest 投影 |
| 服务 | 六套 Serving ViewSet + container_info JSON | ServingDeployment、desired/observed generation |
| 推理 | 同步 HTTP proxy | endpoint lease、团队并发/字节/deadline 预算 |
| 清理 | signals、View 删除分支、TimeSeries cleanup intent | effect intent、token outcome、reconciler/GC |

模块 Interface 应围绕“有版本的数据与算法能力”和“可对账的运行”建立，而不是继续暴露六套相似但语义不同的资源控制器。

## 3. 现状架构图

- [MLOps 现状架构（Archify HTML）](./mlops-current.architecture.html)
- [MLOps 现状架构规格](./mlops-current.architecture.json)
- [MLOps 现状架构静态图](./mlops-current.architecture.light.png)

当前主路径是：

```text
HTTP / NATS → 六套算法 ViewSet → 六套资源模型
                               ├→ Dataset Publish Task → Worker Temp FS → MinIO
                               ├→ WebhookClient → Webhookd → Train/Serving Container
                               └→ MLflow Client/Poller → Experiment/Run/Model
```

Django status、Webhookd 容器状态和 MLflow run/model 都保存了部分运行事实，但没有一个本地、不可变的 run/deployment identity 把三者绑定起来。这使“请求超时但容器已创建”“旧轮询观察到新 run”“部分 runtime 删除成功”等情况只能靠补偿代码猜测。

## 4. 应保留并深化的设计

### 4.1 Scope 校验与状态条件更新是正确基础

训练数据和任务已有团队 scope 与 dataset version 归属检查；训练状态领取与最终更新使用条件更新，能够阻止一部分重复启动和终态覆盖。后续应把条件从单一 `status=running` 深化为 `(run_id, generation, token)`，而不是退回无条件保存。

### 4.2 流式文件处理与引用保护应成为共享制品协议

普通数据集发布按块下载到临时文件，避免全量载入内存，见 [base.py:371](../../server/apps/mlops/tasks/base.py#L371)；TrainData 文件删除还经过引用 guard 和重试清理。目标架构应在此基础上补齐磁盘/字节预算、内容 digest、token 提交和孤儿 GC，而不是为统一代码牺牲现有流式行为。

### 4.3 TimeSeries 的 generation 与 cleanup intent 可作为迁移样板

TimeSeries 已比其他算法多出 runtime generation、查询 token、永久操作 guard、RuntimeCleanupIntent 和 orphan reconciliation。它说明服务生命周期需要显式运行身份与持久清理意图。应抽取协议并迁移其他五类算法，不能继续让可靠性修复只落在一个 ViewSet 中。

## 5. 制品安全与供应链边界

### P0：上传 ZIP 被直接解压，没有安全沙箱与展开预算

图片分类在 [image_classification.py:109](../../server/apps/mlops/tasks/image_classification.py#L109) 下载三个 split ZIP，并在 [image_classification.py:125](../../server/apps/mlops/tasks/image_classification.py#L125) 直接 `extractall`；目标检测在 [object_detection.py:300](../../server/apps/mlops/tasks/object_detection.py#L300) 使用相同做法，并在 [object_detection.py:316](../../server/apps/mlops/tasks/object_detection.py#L316) 直接解压。没有验证成员路径是否逃出目标目录，也没有限制成员数、单文件/总展开字节、压缩比、嵌套归档、symlink 或特殊文件。长时 Celery task 最多可在本地同时保留下载 ZIP、展开目录和重打包制品，恶意或异常输入会造成路径写入和磁盘耗尽。

短期必须建立唯一 `SafeArchiveExtractor`：先只读扫描 central directory；拒绝绝对路径、`..`、symlink/device/FIFO、重复或大小写冲突路径；限制归档字节、成员数、单文件字节、总展开字节、压缩比和目录深度；每次写入前校验 resolved path 仍位于 sandbox；使用独立受限临时卷并统计实时预算。图片分类与目标检测必须共享同一套契约测试和失败终态。

### P0：可变镜像获得共享长期 MinIO 凭据

AlgorithmConfig 只校验容器镜像引用格式，见 [algorithm_config.py:21](../../server/apps/mlops/serializers/algorithm_config.py#L21)，未要求 registry allowlist、digest pinning、签名或 provenance；默认镜像全部使用 `:latest`，见 [algorithm_config_service.py:21](../../server/apps/mlops/services/algorithm_config_service.py#L21)。训练配置从进程环境读取共享 `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` 和固定 `munchkin-public` bucket，见 [config_helpers.py:29](../../server/apps/mlops/services/config_helpers.py#L29)，随后传给训练容器，见 [timeseries_predict.py:223](../../server/apps/mlops/views/timeseries_predict.py#L223)。

这把“可编辑算法配置”提升为“选择获得共享对象存储凭据的代码”。短期应只允许管理员登记的 registry/repository，创建训练前解析为不可变 digest 并写入 TrainingRun；使用短期、最小 prefix 权限的凭据或预签名输入/输出；禁用 `latest` 回退。中期增加镜像签名/证明验证、漏洞策略和训练 run 级网络/资源策略。

## 6. 数据发布、训练与服务数据流

- [MLOps 生命周期数据流（Archify HTML）](./mlops-lifecycle.dataflow.html)
- [MLOps 生命周期数据流规格](./mlops-lifecycle.dataflow.json)
- [MLOps 生命周期数据流静态图](./mlops-lifecycle.dataflow.light.png)

### P1：DatasetRelease 不是可 fencing 的发布运行

通用发布任务仅在 `published/failed` 时跳过，`processing` 的重复 delivery 会继续执行，见 [base.py:327](../../server/apps/mlops/tasks/base.py#L327)；图片分类和目标检测分别在 [image_classification.py:53](../../server/apps/mlops/tasks/image_classification.py#L53)、[object_detection.py:216](../../server/apps/mlops/tasks/object_detection.py#L216) 复制相同行为。任务使用 `acks_late`/worker-lost 重投时，重复 worker 可能同时打包和上传。失败重试又复用同一 Release 行并重置状态，没有 generation；旧 worker 可在新重试后提交陈旧结果。

新增 `DatasetPublishRun(release, generation, token, lease_until, heartbeat_at, retry_at, source_digest, artifact_digest)`。只有 `PENDING + expected generation` 可条件领取；上传键包含内容或 run digest；成功写回校验 token；reaper 只回收过期 lease，旧 worker 永远不能完成新 generation。DatasetRelease 保持不可变业务版本，PublishRun 记录每次执行事实。

### P1：TrainJob 不是 TrainingRun，MLflow 最新记录不能代替 attempt identity

训练启动前先读取实验全部 runs 并计算 `expected_run_count`，启动容器后再投递 poll task，见 [timeseries_predict.py:193](../../server/apps/mlops/views/timeseries_predict.py#L193)。轮询器读取最新 run，并通过数量判断是否出现新 run，见 [poll_train_job_status.py:74](../../server/apps/mlops/tasks/poll_train_job_status.py#L74)；最终 CAS 只约束 TrainJob 仍为 RUNNING，见 [poll_train_job_status.py:106](../../server/apps/mlops/tasks/poll_train_job_status.py#L106)。

这个启发式无法区分重训 attempt、旧 poll task、容器重启和并发注册。Webhook 超时不等于副作用未发生，但异常分支会恢复旧状态；训练成功启动后若 `poll_train_job_status.delay` 失败，通用异常分支同样恢复状态，而容器可能继续运行。

建立不可变 `TrainingRun`：run id/generation、dataset release digest、config digest、image digest、runtime request id、MLflow run id、lease/token、observed status 和终态原因。先持久创建 run 与 start intent，再由 worker 幂等启动；容器通过 run token/tag 回报确定的 MLflow run id；poller 只能更新相同 run/token。TrainJob 仅表达训练定义与当前 run 投影，不再承担全部历史与并发语义。

### P1：Serving 同步控制外部运行时，六种算法语义分叉

多数 Serving action 在 HTTP 请求中直接调用 Webhookd，并依赖补偿恢复 Django 状态。TimeSeries 加入 generation 与清理 intent 后更可靠，但部分 `transaction.atomic` 路径仍在数据库事务内等待最长数分钟的 runtime I/O，容易长时间占用连接和行锁。其他算法没有等价 generation，创建、停止、删除的超时和部分成功语义各不相同。

引入 `ServingDeployment(serving_id, desired_generation, observed_generation, spec_digest, endpoint_lease, status)`。HTTP 只更新 desired state 并提交 `RuntimeWorkItem`；协调器在事务外调用 Webhookd，通过 idempotency key 执行并条件写回 observed generation。查询与删除都由 reconciler 对账，TimeSeries 现有 generation/intent 迁移为共享实现。

### P1：删除由同步循环和 signal 拼接，部分成功不可恢复

TrainJob 删除会先逐个移除关联 runtime，再删除数据库记录；第三个 runtime 失败时，前两个已经消失而数据库关系仍在。另一路 post-delete signal 又做 best-effort 外部清理，实际语义依赖删除入口和 cascade 顺序。

删除应先创建 `DeletionIntent` 并把资源置为 terminating；按带 token 的步骤停止 runtime、撤销 endpoint、清理 MLflow/对象制品，最后再 tombstone/删除业务记录。每步持久记录 outcome，周期 reconciler 重试或人工接管；signal 只发布意图，不能承载关键清理流程。

## 7. 制品一致性、查询与容量

### P1：模型 `save()` 在数据库事务内上传并删除 MinIO 对象

`TrainJobConfigSyncMixin.save()` 在 `transaction.atomic()` 内保存模型、上传新 config、更新 FileField，见 [mixins.py:211](../../server/apps/mlops/models/mixins.py#L211)；随后立即删除旧对象，见 [mixins.py:302](../../server/apps/mlops/models/mixins.py#L302)。如果对象操作成功后数据库提交失败，事务回滚并不能恢复已删除的旧对象，新对象也可能成为孤儿，代码注释声称的“rollback leaves everything consistent”不成立。

模型保存只写 `ConfigArtifactIntent(content_digest, candidate_key, previous_ref, token)`；事务提交后上传内容寻址对象，成功后 token 条件切换引用。旧对象只由引用计数/保留期 GC 删除。所有 Dataset、Config、Model export 共用同一 artifact port，禁止在行锁事务中等待对象存储。

### P1：MLflow 查询与模型导出先全量获取，再在 API 层分页

`get_experiment_runs` 返回完整 Pandas DataFrame，调用方常在内存中取长度或分页；metric history 同样倾向全量加载。模型下载还需从 MLflow 拉取 artifact 后在 Web worker 临时盘重新压缩。实验 run 数、指标点和模型体积增长后，API 延迟、内存与临时盘都不可预测。

建立 `MLflowQueryPort`：服务端分页/limit、列投影、deadline、最大响应字节和 continuation token；状态观察按确定 run id 查询，不再拉全实验。大模型导出变为异步 `ArtifactExportRun`，使用磁盘配额、流式压缩、内容 digest 和短期下载地址。

### P1：同步推理只有单请求 batch 上限，没有共享容量模型

推理直接在 API worker 中请求 Serving endpoint，已有部分 batch/image budget 是好基础，但没有 team、serving、model 维度的并发 slot、请求/响应字节、总 deadline 或公平性。多个大批量用户仍会同时占满 API worker 和模型容器。

所有 predict adapter 进入 `InferenceBudgetGateway`：按团队和 Serving 分配并发、队列等待、输入/输出字节与 deadline；传播取消；达到预算时显式拒绝或返回异步 job，不在 API worker 无限等待。算法能力负责 schema 和 cost estimator，预算与观测由共享网关负责。

## 8. 代码结构：统一生命周期，保留算法差异

六类算法不是六个独立模块，因为它们共享相同的 Dataset→Release→Train→MLflow→Serve→Predict 状态链、权限模型和外部系统；但也不应通过一个巨型 BaseViewSet 加大量 `if algorithm_type` 合并。

建议使用深模块结构：

```text
mlops/
  domain/          Dataset, DatasetPublishRun, TrainingRun, ServingDeployment
  application/     publish_dataset, start_training, reconcile_runtime, predict
  capabilities/    registry + six algorithm plugins
  ports/           artifact, runtime, mlflow, inference, credential broker
  adapters/        django_http, celery, minio, webhookd, mlflow
  projections/     current status, run list, artifact/export views
```

`AlgorithmCapabilityRegistry` 的每个插件只声明：dataset schema、packager、训练参数 schema、image policy、serve/predict adapter、cost estimator。共享 application service 独占 scope、run identity、状态转换、重试、fencing、预算和审计。这样新增第七种算法无需复制整套模型/View/task，也不会让可靠性修复只落到 TimeSeries。

## 9. 不合理设计要素与优先级

| 优先级 | 设计要素 | 影响 | 优化方向 |
|---|---|---|---|
| P0 | 图片 ZIP 直接 `extractall`，无路径与展开预算 | 路径逃逸、ZIP bomb、磁盘占满和长时 worker 占用 | SafeArchiveExtractor + 受限临时卷 + bytes/files/ratio/type budget |
| P0 | tag/`latest` 镜像获得共享长期 MinIO 凭据 | 供应链变化与对象存储越权面 | digest pin/allowlist/attestation + run-prefix 短期凭据 |
| P1 | 六套生命周期代码复制 | 修复漂移、接口不一致、新算法扩展成本高 | AlgorithmCapabilityRegistry + shared lifecycle application services |
| P1 | Release 的 PROCESSING 可重复执行且无 generation | 重投与失败重试相互覆盖、制品无法对账 | DatasetPublishRun + token/lease/heartbeat + content digest |
| P1 | TrainJob 无 TrainingRun，按最新 MLflow run 关联 | 旧 poll/重训/超时副作用串线 | immutable TrainingRun + explicit MLflow run id + fencing |
| P1 | Serving 在 HTTP/事务内同步控制 runtime | 长事务、请求超时、部分成功和算法语义分叉 | desired/observed generation + RuntimeWorkCoordinator |
| P1 | 删除由同步循环和 signal 承担 | 多 runtime 部分删除、孤儿与入口差异 | DeletionIntent + step outcome + reconciler/GC |
| P1 | Model.save 在事务中上传/删除 MinIO | DB 回滚不能回滚对象存储 | ArtifactIntent + on-commit worker + digest reference + GC |
| P1 | MLflow 全量 DataFrame 和同步模型打包 | 内存、临时盘与响应时间随历史无界增长 | MLflowQueryPort + server pagination + ArtifactExportRun |
| P1 | 推理无团队/Serving 共享预算 | API worker 与模型容器被并发大请求耗尽 | InferenceBudgetGateway + slots/bytes/deadline/fairness |
| P2 | team IDs 使用 JSON 列表、算法映射散落 | 查询/约束弱，新增算法需修改多处 map | 规范化 scope relation + capability id registry |

## 10. 分阶段优化路线

### 短期：0—2 个迭代

1. 立即替换两处 `extractall`，上线统一 safe extraction、归档/展开/临时盘硬预算与恶意归档测试；
2. 禁止 `latest` 和未登记 registry/repository，训练启动时记录 resolved image digest；将共享 MinIO 长期密钥改为最小 prefix、短期凭据或预签名 URL；
3. DatasetRelease claim 增加 generation/token/lease，PROCESSING 不可被第二 worker 领取，发布制品使用内容寻址 key；
4. 新增 TrainingRun，至少把每次训练 attempt、image/dataset/config digest、runtime request id 与 MLflow run id 持久化；
5. Serving 外部调用移出数据库事务和 HTTP 主流程，先落 desired generation/intent，再异步执行与对账；
6. 给推理、MLflow 查询、模型导出和临时盘增加团队级并发、字节、时间和磁盘上限。

### 中期：2—5 个迭代

1. 建立 `AlgorithmCapabilityRegistry`，将六套 dataset schema、packager、train/serve/predict 差异迁入插件；
2. 建立共享 `DatasetAggregate + DatasetPublishRun + TrainingRun + ServingDeployment` 状态机；
3. 建立 `RuntimeWorkCoordinator`，统一 lease、heartbeat、retry_at、idempotency key、effect intent 和 reconciler；
4. 建立 `ArtifactPort` 和内容寻址引用，统一 Dataset、Config、Model export 的提交与 GC；
5. 建立 `MLflowQueryPort + InferenceBudgetGateway`，统一分页、预算、观测和审计。

### 长期：5 个迭代以后

1. dataset/config/image/model/artifact digest 与 run/deployment generation 形成完整 lineage，可复现训练与部署；
2. 容量调度按团队、算法和资源需求公平分配 GPU/CPU、临时盘、推理 slot 与 MLflow/MinIO 带宽；
3. 只有当 runtime coordinator、artifact export 或 inference gateway 确实需要独立扩缩容和发布时，才沿既有 Port 拆进程；不要先用微服务掩盖本地 run identity 与预算缺失。

## 11. 目标架构图

- [MLOps 目标架构（Archify HTML）](./mlops-target.architecture.html)
- [MLOps 目标架构规格](./mlops-target.architecture.json)
- [MLOps 目标架构静态图](./mlops-target.architecture.light.png)

目标 Module 对外只暴露小接口：

```text
HTTP/NATS Adapter
  → MLOpsAccessScope
  → AlgorithmCapabilityRegistry
  → Dataset / TrainingRun / ServingDeployment
  → RuntimeWorkCoordinator
  → Artifact / Runtime / MLflow / Inference Ports
```

算法插件知道本算法的数据和运行契约，但不知道 Celery 重试、Webhook 凭据、状态 fencing 或对象清理细节；运行协调器知道如何可靠执行，却不需要知道六种算法的内部字段。

## 12. 给开发同学的架构提醒

1. **不要再复制第七套 ViewSet/Model/Task 生命周期。** 新算法先定义 capability schema 和 adapter，共享发布、训练、服务与推理协议。
2. **任何上传归档都先扫描、再预算、最后逐成员安全写入。** 不能直接 `extractall`，临时目录也不是安全边界。
3. **镜像 tag 不是运行事实。** 每次 TrainingRun/ServingDeployment 必须保存 resolved digest，默认镜像也不能使用 `latest`。
4. **不要把共享长期凭据传给可配置代码。** 凭据必须短期、最小 scope，并绑定 run 和对象 prefix。
5. **业务对象与运行 attempt 分开。** DatasetRelease、TrainJob、Serving 定义不能代替 DatasetPublishRun、TrainingRun、ServingDeployment。
6. **状态值不是锁。** `processing/running` 必须配 generation、token、lease、heartbeat 和条件完成；旧 worker 不能提交新一轮结果。
7. **外部副作用超时不等于失败。** Webhook/MinIO/MLflow 超时后先进入 unknown 并对账，不可直接恢复旧状态。
8. **不要在数据库事务或 HTTP 请求里等待容器启动和对象上传。** 先持久 intent，再由 worker 执行，完成写回必须验 token。
9. **删除是可恢复工作流。** 先 terminating，再逐步清理和记录 outcome；关键清理不能只靠 signal 或 best-effort 循环。
10. **所有批量/列表/推理接口都有四类上限。** item count、bytes、deadline、concurrency；临时盘再单独设 quota。
11. **MLflow 查询必须按确定 run id 和服务端分页。** 不允许为状态检查加载完整 experiment DataFrame。
12. **保留现有可靠性基础。** Scope 校验、流式 I/O、引用 guard、状态 CAS、TimeSeries generation/token/cleanup intent 都应迁移进共享协议。
