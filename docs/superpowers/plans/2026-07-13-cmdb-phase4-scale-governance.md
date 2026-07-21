# CMDB 阶段四规模治理执行计划

**目标：** 关闭 K8s 资源视图、实例唯一规则和批量审计在大数据量下的无界查询、N+1 与同步 RPC 风险，并以查询预算测试固定生产契约。

**执行纪律：** 每个任务严格 RED→GREEN→相关回归；只使用 Django ORM 与现有图客户端抽象，不引入原生 SQL。

## Task 1：K8s 资源视图真实分页与批量关系查询

1. 在 `test_k8s_resource_overview_service.py` 增加查询预算测试：概览不加载 Pod 实体，Namespace/Workload/Node 读取次数为固定值；Pod 当前页到 Node 只允许一次批量关系查询。
2. 在 `InstanceManage` 和两种图驱动增加 K8s 专用的关联分页、聚合计数和当前页批量关系查询契约。
3. 重写 `K8sResourceOverviewService` 的概览、列表和 Pod 分支，只保留当前页实体；权限裁剪在候选页上执行，必要时以有界补页保证页大小。
4. 运行 K8s Service/View、FalkorDB/Neo4j 图驱动聚焦回归。

## Task 2：实例唯一规则定向候选与同键串行化

1. 增加测试证明实例创建/更新仅按唯一规则实际字段和值查询候选，禁止按 `model_id` 拉取全模型。
2. 从内置唯一字段、历史 `is_only` 与联合唯一规则生成候选谓词；图驱动只返回可能冲突的实例。
3. 对同模型、同唯一签名使用带 owner token/租约的关系库锁，覆盖“检查 + 图写”窗口；不同唯一键不互相阻塞。
4. 运行 unique-rule、instance、两种图驱动及 operation/outbox 回归。

## Task 3：批量审计 outbox

1. 增加测试证明一万条变更只产生有界批次数的异步任务/平台日志 RPC，且下游失败不回滚 `ChangeRecord`。
2. 新增批量审计 outbox，`ChangeRecord.bulk_create` 后按固定批大小持久化待镜像事件，不在采集主链同步逐条 RPC。
3. 消费者使用 owner token、租约、有限批次和退避重试；一次 RPC 携带一批平台日志，若下游只支持单条则在 worker 内受控降级，主任务不阻塞。
4. 运行 change-record、采集数据处理、Celery 任务及迁移回归。

## Task 4：阶段门禁

1. 合并运行阶段四全部聚焦测试并检查改动覆盖率。
2. 运行 CMDB 相关回归、`makemigrations --check`、`git diff --check`。
3. 自审权限、跨库兼容、秘密泄露、租约并发与无界内存风险；逐项记录 projectmem 修复证据。
