# Celery 四池弹性运行手册

本变更仅调整公共运行架构。架构设计和待办的真相源为 [OpenSpec](../openspec/changes/isolate-celery-workload-runtime/design.md)，本手册描述实际运行入口。**当前尚未完成生产版本、Linux 全应用兼容性与整机容量验收，不应直接升级线上镜像。**

## 1. 配置与启动

原默认工作负载拆为四类独立 worker：`critical`（告警）、`notification`（通知/回调）、`state`（节点状态/控制）、`background`（重后台）。后台同时消费历史 `celery` 队列；新注册但未映射的任务落到该默认队列并产生限频提示。路由清单在 `server/apps/core/celery_runtime/manifest.py`，不按模块通配。直接函数调用不受任务路由影响。

每池保留上游原生 prefork，使用 `--autoscale=MAX,MIN` 伸缩。MIN≥1，MIN≤MAX；MIN=MAX 可固定容量。并发参数必须显式填写，不能依 CPU 数或“每池 1”推断够用。填写 [配置模板](../server/support-files/env/celery-runtime.env.template) 后由部署环境注入；命令示例均在 `server/` 执行。

```bash
python -m apps.core.celery_runtime.launcher --check
# 开发环境分别启动四池；四个进程应使用同一组容量配置。
make celery POOL=critical
make celery POOL=notification
make celery POOL=state
make celery POOL=background
```

release 保留 migrate 失败立即停止与 batch_init 的原有顺序；随后纯本地生成 `$SUPERVISOR_CONF_DIR/celery.conf` 并删除旧独立 beat.conf，再启动 supervisor。生成器不访问外部依赖。关闭 ENABLE_CELERY 只关闭本次管理的四池和 Beat，既有专用 worker 保持上游独立配置；若要全部停用须由部署层同时停用它们。

上游既有 OpsPilot、报表渲染、补丁维护专用 worker 均保留，包含其显式队列、任务声明及回收参数。全装时共有7个Celery主进程（四池+三个既有专用池），不是四个。

`CELERY_TOTAL_CONCURRENCY_LIMIT` 限制所有同时运行实例的“四池MAX总和 + 报表并发 + 补丁维护1 + 启用OpsPilot时的并发”。报表/补丁worker当前固定安装，即使未启用对应业务模块仍须计入。`CELERY_WORKER_REPLICAS` 包含升级重叠，异构部署另行逐实例求和。预算不是硬内存限制，其他组件和每个子进程依赖副本也要测量。

多实例必须显式设置 `CELERY_RUN_BEAT`，只让一个实例为 true。它不是分布式锁，唯一性需要部署层保证，不能对所有副本复制相同的 true。每个容器/主机必须有不同 hostname，防止节点名冲突。

原生 autoscale 根据池内需求扩容，`AUTOSCALE_KEEPALIVE` 控制原生收缩等待，默认 60 秒；不保证连续空闲满 60 秒，也不按整机剩余内存决策。所有 MAX 同时执行的资源预算必须事先通过，无法借用其他池的空闲额度。此阶段不开放绕过持久配置预算的远程改范围入口。

## 2. prefork 准入与资源验收

最新上游已经使用prefork。保留 CELERY_MAX_TASKS_PER_CHILD（默认200）、CELERY_MAX_MEMORY_PER_CHILD（默认512000KiB）、任务软/硬超时及ACK/retry；不会取消既有强制超时或按任务/内存回收行为。阈值回收发生在任务结束后，不限制单个在途任务的瞬时内存。

仍须在目标Linux镜像验证启用应用的连接、模型库、线程和在途行为在四池伸缩下的兼容性。Celery原有Django连接处理保持不变。

各池先测到达速率 λ、执行均值 E[S]、长尾和突发量，用 `ceil(λ×E[S]/目标利用率)` 估计保底；需要在 T 秒内消化积压 Q 时，粗略要求 `MAX/E[S] > λ+Q/T`。公式仅用于选择压测起点，最终需验证关键排队 P95/P99、积压下降速率及资源峰值。

整机验收包含应用、NATS、数据库、图库、Redis、算法等全部组件，覆盖启动、MIN 稳态、所有 MAX 峰值、反复伸缩和升级重叠。记录容器内存、整机可用内存、CPU、连接数及安全余量；不能简单累加 RSS 当成实际物理占用。预取乘数为 1，仍可能基于最大并发预取，ETA 也不受相同驻留上限约束。

## 3. 只读诊断和路由调整

```bash
python manage.py celery_runtime_report
python manage.py celery_runtime_report --workers --timeout 3
python manage.py celery_runtime_report --workers --strict
```

报告包含本地注册任务、未映射项、启用的 Beat 有效路由、prefork/回收配置和可用资源信息。`--workers` 增加消费队列、实际 MIN/MAX、远端注册集合、active/reserved/scheduled 数量和 Redis ready 数量，并核对消费者是否注册该池的目标任务及是否使用上游原生prefork。任意节点缺少部分 inspect 回复也会令严格检查失败。Redis ready 聚合优先级子列表，不含 unacked/执行中/已预取/ETA；这些数值可能有交集，不能直接相加。其他 broker 或缺失的指标标为未知，不代表零。worker `maxrss` 不是整个执行池的实时内存，cgroup v2 和 `/proc/meminfo` 不可读时相应字段为 null。

`--strict` 只检查报告可确认的配置/路由/消费者条件，不能替代生产容量、真实任务兼容性或全部生产者的核验。最新上游已找到截图中的任务源码并纳入[182项清单](celery-current-task-inventory.md)；仍需确认线上commit和启用模块，不能将静态定义数当作生产注册数。

Beat 的显式 queue/exchange/routing_key 可能覆盖公共路由。先审查明确 ID 名单：

```bash
# 示例 ID 必须替换成现场核对后的名单；默认只读，不创建快照。
python manage.py celery_routes --ids 101 102
# 应用前写入排他创建、权限 0600 的恢复快照，仅更新三个路由字段。
python manage.py celery_routes --ids 101 102 --apply --snapshot /secure/celery-routes-before.json
# 恢复同样先预览，再应用。
python manage.py celery_routes --restore /secure/celery-routes-before.json
python manage.py celery_routes --restore /secure/celery-routes-before.json --apply
```

工具不修改任务名、启停、周期、参数，不自动修复未注册名称。应用时持有行锁，快照落盘后才写路由；恢复前确认当前字段仍等于本次变更结果，有并发变更则整批拒绝。若数据库操作失败而快照已经创建，先核对当前字段，不能盲目重复恢复。快照不得覆盖已有文件。

这些管理命令注册任务时跳过原有静态周期表自动同步，避免只读检查顺便创建/启用业务调度。正常 worker/Beat 的既有同步行为保持不变。对于生产者代码内的显式投递选项，报告无法穷举，发布时仍需源码核对和投递探针。

## 4. 生命周期观测

发布头新增 `bklite_published_at`，每次重试发布覆盖为本次时间，不改 args/kwargs。开始执行时扣除 ETA 的计划等待，旧消息没有时间则标未知，负时延标时钟偏差。执行耗时使用单调时钟。

公共日志输出 `celery_runtime`：计数按进程有界聚合，每 100 个生命周期事件或下次事件距上次输出超过 60 秒时刷新；worker 正常退出尽力刷新。等待样本采样 1%，等待直方图区间为 0.05/0.1/0.5/1/5/15/60/+Inf 秒，非累计桶。可由现有日志平台聚合窗口增量计算速率、失败/重试比例及近似分位数。低流量空闲进程尚未刷出的窗口不等于零流量；崩溃或日志失败会形成观测缺口，不能作可靠审计账本。

只输出有限任务名、队列、阶段、状态和统计值，不输出任务参数、结果或凭据。指标故障不能影响业务执行。精确 P95/P99 和最老等待年龄需额外关联现场探针/采样，报告不会伪造未采集结果。

## 5. 迁移与回滚

1. 确认线上版本/注册、生产者路由、截图任务、既有专用消费者及资源预算；保留现网配置、调度路由快照及实际队列记录。
2. 选择受控维护窗口。对旧 worker 发送 TERM，等待 active 完成；新旧短暂重叠必须计入最大并发和内存预算，否则串行切换。不能直接 kill 在途远端操作。
3. 准备新消费者就绪后再切生产者和唯一 Beat。release 启动脚本本身不能替代跨版本滚动编排；若新镜像同时承载 API/Beat，先以消费者单独启动步骤或维护窗口完成顺序控制。
4. 后台继续排空旧 `celery`，不 purge、不批量重发、不自动清锁或超龄丢弃。新路由不会移动旧消息，历史告警仍可能等待。
5. 回滚时恢复生产者/数据库路由，继续保留新队列消费者直到存量排空；若使用旧单 worker，必须验证其注册集合并显式消费 `critical,notification,state,background,celery`。仅回退镜像会让新队列无人消费。

supervisor 只向主进程发送 TERM，设置长等待且不向整组发终止信号，以等待子进程完成；容器平台的 termination grace period、运维超时仍可强杀，必须与最长在途任务匹配。异步下发的远端操作是否已安全结束仍由原有业务状态机确认，不能由空队列推断。

## 6. 验证入口与当前边界

轻量测试只启用 Django/Beat 基础设施，以独立 SQLite 测试其 ORM；这不替代项目 PostgreSQL 全量测试：

```bash
DJANGO_SETTINGS_MODULE=apps.core.tests.celery_test_settings uv run --extra dev pytest --noconftest -c /dev/null \
  apps/core/tests/test_celery_runtime_pure.py \
  apps/core/tests/test_celery_routing_service.py \
  apps/core/tests/test_celery_observation_pure.py \
  apps/core/tests/test_celery_route_migration_service.py \
  apps/core/tests/test_celery_diagnostics_service.py \
  apps/core/tests/test_celery_runtime_commands_service.py
```

真实 broker 探针需要可执行的 `redis-server`，只创建自己的本机临时服务，不连接生产 broker：

```bash
CELERY_RUNTIME_INTEGRATION=1 uv run --extra dev pytest --noconftest -c /dev/null -p no:django \
  apps/core/tests/test_celery_runtime_integration.py -q
```

当前本机 macOS 验证采用测试专用 fork 模式，不能作为目标 Linux 镜像/全应用的结论。发布还必须完成 `make test`、目标 Linux Redis 多池验证、真实负载时延及整机容量验证、迁移回滚演练。具体结果见 [实施记录](../openspec/changes/isolate-celery-workload-runtime/implementation-evidence.md)。
