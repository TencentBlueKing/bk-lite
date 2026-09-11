# 周期采集错峰验收记录

日期：2026-09-11。范围：主机、网络设备、网络拓扑；未新增表、迁移、前端配置或 Stargazer 排队。

用户重启本地前端后的实际 Chrome 操作记录见 [browser-validation.md](browser-validation.md)。已新建任务 8，在同一任务完成改名、拓扑关闭／重开和周期修改，并通过节点管理核对两通道配置及偏移；手动同步返回“未发现任何有效数据”，真实目标采集入库尚未验收通过。

## 验收结论与证据边界

2026-09-11 15:49（北京时间）重新执行当前工作区的相关回归：**355 passed、3 skipped、0 failed、0 errors，6.00 秒**。
相比首次交付的 347 项，补充三个插件“不传／传零”的 6 项参数化用例，以及 one-shot“不传／传零”的 2 项用例。
当前结论是：本次修改在真实 ORM 保存、配置生成、外部调用参数和一次性执行配置转换层面通过回归。
这些是分段集成验证；RPC、远程执行器使用替身，不能表述为真实设备端到端采集已经验收通过。

| 链路／功能 | 实际验证内容 | 证据及边界 |
|---|---|---|
| 创建主机任务 → 保存 → 下发参数 | 服务端分配偏移，落库值与最终 TOML 一致，周期仍为 1800s | 真实 serializer、ORM、模板、提交回调；NodeMgmt RPC 为替身。用例 `test_collect_create_ignores_client_offset_and_pushes_saved_phase` |
| 网络设备 + 网络拓扑 → 两份配置 | 配置 ID 对应正确，两通道周期分别为 1800s/9000s，各自偏移与数据库一致 | 真实保存与模板；RPC 为替身。用例 `test_two_channel_save_pushes_matching_ids_intervals_and_offsets` |
| 编辑 → 重试 | 不允许客户端覆盖或遗漏清空偏移；下发失败保留落库值，重试下发同一偏移 | 真实 ORM；通过 RPC 替身注入下发失败。用例 `test_edit_cannot_overwrite_or_erase_server_owned_offset`、`test_saved_offset_survives_post_commit_failure_and_retry` |
| 节点同步 → 自动主机任务 | 新建参与分配；刷新目标列表保持同一任务及偏移 | 真实节点同步保存入口、ORM；同步配置查询为替身。用例 `test_node_sync_created_host_gets_offset_and_refresh_preserves_it` |
| 周期配置 → 首采／立即执行 | 不传、传 0s、传 9000s 均可接受；转换后 HTTP input 不含 interval/collection_offset，timeout 保留 | 真实配置读取和转换；远程 Executor 为替身，未测真实首采耗时。用例 `test_one_shot_accepts_periodic_offset_but_does_not_wait_for_it` |
| 配置兼容与范围 | 三插件独立渲染；不传、传 0 和非法值均输出 0s；其他插件、非周期任务不输出偏移 | 真实策略、模板、TOML 解析；29 项配置与目标计数用例 |
| 保存完整性 | 事务失败回滚、锁竞争不提前下发、锁内重新读与检查权限、竞争事务重试后偏移分散 | 真实 SQLite ORM/事务；不代表生产数据库锁行为。保存编排 23 项、写锁 3 项通过 |
| 周期错峰算法 | 原场景与独立穷举 oracle 对照、互质周期、相位耗尽、确定性 | 15 项算法用例通过；忙时是估计值，不保证实际运行不重叠 |
| Telegraf 调度 | 10s 周期、0s/5s 相位，以及重载／重启 | 独立真实容器测试，详见下文；使用公共 exec input，未对接真实 Stargazer |

完整逐项结果及被测生产文件 SHA-256 见 [test-results.json](test-results.json)，便于核对报告对应的代码。
原始回归输出：`/tmp/cmdb-offset-recheck-final.log`；JUnit：`/tmp/cmdb-offset-recheck-final.xml`；覆盖率：`/tmp/cmdb-offset-recheck-coverage-final.json`。

要把结论升级为“实际业务端到端验收通过”，仍需在具备真实测试依赖的环境执行：

1. 创建主机、网络设备及启用拓扑的任务，检查节点实际收到的配置与数据库偏移一致。
2. 观察周期触发到 Stargazer 接纳、采集执行、结果处理和 CMDB 入库完整成功，至少覆盖两个周期；对照未传偏移、0s 和非零偏移。
3. 执行一次首采／手动采集，确认实际立即发起且结果完成；重载节点配置后再次观察周期与相位。

本次未连接真实目标设备，未执行上述业务端到端验收；全仓门禁及 Linux 专用测试限制见文末。

## 实现入口

- `server/apps/cmdb/services/collection_offset.py`：最大公约数计算、等价相位折叠、重复占位合并、稳定分配。
- `server/apps/cmdb/services/collection_offset_policy.py`：三个插件的集中登记、目标计数、有效通道与服务端字段保护。
- `server/apps/cmdb/services/collection_offset_service.py`：复用数据库写锁，在任务事务内分配并持久化。
- `CollectModelService.create/update`、扫描生成任务所复用的保存入口、`NodeMgmtSyncService._ensure_region_collect_task`：统一保存规则。
- `BaseNodeParams` 与 `base.child.toml.j2`：仅登记插件渲染偏移。
- `TelegrafOneShotService`：允许周期配置携带偏移，转换一次性 input 时不转发，保持原执行限制。

## 功能与完整性结果

最新直接相关测试：**355 passed，3 skipped**，退出码 0，6.00 秒（首次交付为 347 passed，10.92 秒）。

三个新增错峰模块合计覆盖率 **96%**：计算 95%、策略 96%、保存编排 100%。
覆盖配置保存与编辑、三个插件最终 TOML、原周期保持、存量占位/不回填、关闭与新增拓扑、
客户端字段覆盖与遗漏、锁内重读、组织权限拒绝、跨组织共享负载、两个竞争事务及失败重试、
事务回滚、提交后下发失败与重试、节点同步生成/刷新主机任务、未来插件登记接入、首次采集与 one-shot 安全回归。

原型中的“设备间隔固定至少 40 分钟”是某次排列结果，现测试验证估计忙时所需间距及无可避免之外的同刻触发，
不锁定具体相位排列。忙时不再被周期一半裁剪；互质周期与相位用尽场景接受不可避免的冲突。

三个跳过项：两个已有 Linux 专用 one-shot 资源边界测试在 macOS 不适用；一个真实 Telegraf 时序测试默认显式启用，已单独执行通过。

复现（仓库 `server/` 下；变量均为测试专用，不需要启动中间件）：

```sh
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
MINIO_ACCESS_KEY=unit-test MINIO_SECRET_KEY=unit-test \
.venv/bin/python -m pytest \
  apps/cmdb/tests/test_collection_offset*.py \
  apps/cmdb/tests/test_collect_service_first_collection.py \
  apps/cmdb/tests/test_collect_service_methods.py \
  apps/cmdb/tests/test_collect_service_permission_and_node_params.py \
  apps/cmdb/tests/test_first_collection_policy.py \
  apps/cmdb/tests/test_first_collection_orchestrator.py \
  apps/cmdb/tests/test_first_collection_task.py \
  apps/cmdb/tests/test_node_params_multicred.py \
  apps/cmdb/tests/test_network_channel_split.py \
  apps/cmdb/tests/test_node_mgmt_sync_execution.py \
  apps/cmdb/tests/test_node_mgmt_sync_node_config.py \
  apps/cmdb/tests/test_unique_write_lock*.py \
  apps/node_mgmt/tests/test_telegraf_oneshot_service.py \
  --nomigrations -o addopts='' \
  --cov=apps.cmdb.services.collection_offset \
  --cov=apps.cmdb.services.collection_offset_policy \
  --cov=apps.cmdb.services.collection_offset_service \
  --cov-report=term-missing -q
```

`--nomigrations` 用当前模型建 SQLite 测试库，验证真实 ORM 与事务；不等同于验证历史迁移或生产数据库锁等待行为。

## 真实 Telegraf 1.29.5

官方镜像 `telegraf:1.29.5`，镜像摘要 `sha256:c3b08145370a7e8d0614ad8b883a14b7003bfa505be6d31023d75200e935e7d6`。
隔离容器无网络、只读根目录，CPU 0.5、内存 128 MB、进程上限 64；临时样本文件放在 1 MB tmpfs，完成后自动删除。

使用三个本地 exec input 验证公共插件调度：周期均为 10 秒，偏移分别为显式 0s、5s 和不传。
首次运行、SIGHUP 重载、完整退出后重启，采样时间始终分别落在 `timestamp % 10 == 0/5`。
最新结果：**1 passed，62.20 秒**。每个阶段、每个通道至少连续采到两个样本，阶段内间隔严格为 10 秒；
不传与显式 0s 相位相同，5s 通道固定错开。跨重载边界不承诺每一轮都能采到。

实际采样时间（北京时间，2026-09-11）：

| 阶段 | 不传偏移 | 显式 0s | 显式 5s |
|---|---|---|---|
| 启动 | 15:49:30、15:49:40 | 15:49:30、15:49:40 | 15:49:35、15:49:45 |
| SIGHUP 重载 | 15:49:50、15:50:00 | 15:49:50、15:50:00 | 15:49:55、15:50:05 |
| 完整重启 | 15:50:10、15:50:20 | 15:50:10、15:50:20 | 15:50:15、15:50:25 |

原始容器输出见 [telegraf-timing.log](telegraf-timing.log)，逐阶段纳秒时间戳也已写入 `test-results.json`。
该测试验证 Telegraf 公共调度时序；三个业务插件的实际 TOML、保存与一次性执行转换由上述功能测试覆盖，
未连接生产目标或进行真实千台设备负载验收。

### 本轮发现并修正的测试缺陷

首次交付的真实 Telegraf 测试曾通过，但本次复测和插桩复现均失败：5s 通道只有两个样本。
插桩证据：重启后进程于 07:47:20 UTC 启动，0s 通道于 07:47:30 采样，
测试在 07:47:33 结束，早于 5s 通道下一触发时刻 07:47:35。
根因是固定运行 14 秒不能保证覆盖“启动／重载 + 下一周期边界 + 偏移”，且原断言只检查三个阶段的总样本数。

本次改为每个阶段等待各通道实际输出至少两个样本，再进行重载或重启；每阶段最多等待 35 秒，容器命令总超时 120 秒。
断言加强为逐阶段、逐通道检查样本数量、相位和相邻间隔，没有减少原断言要求，也没有调整生产代码。
初次沙箱内尝试还遇到 Docker socket 权限限制；获得执行权限后完成上述复现和验证。
失败证据路径：`/tmp/cmdb-offset-live-verified.log`、`/tmp/cmdb-offset-live-diagnose.log`；
最新通过证据：`/tmp/cmdb-offset-live-final.log`、`/tmp/cmdb-offset-live-final.xml`。

```sh
CMDB_TELEGRAF_OFFSET_LIVE=1 DB_ENGINE=sqlite DB_NAME=:memory: \
SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
MINIO_ACCESS_KEY=unit-test MINIO_SECRET_KEY=unit-test \
.venv/bin/python -m pytest apps/cmdb/tests/test_collection_offset_telegraf_live.py \
  --no-cov -o addopts='' -s -q
```

## 性能样例

本机 Python 3.12，完整 `assign_offset` 调用，不含 DB、锁与下发耗时，不作为生产延迟承诺。

| 输入 | 本次测量 |
|---|---:|
| 已有周期 31/37/41，新周期 30 分钟 | 约 0.00024 秒 |
| 1000 条通道，周期混合 30/250/1250，新周期 1250 分钟 | 约 0.154 秒 |

千通道样例：已有通道目标数 1200、忙时 20，周期按上述三个值轮换、偏移为 `index % 30`。
相同占位合并前该样例约 2.36 秒；合并保持通道数量权重和评分顺序。该样例含重复占位，
不能代表任意千通道配置；大量互不等价相位的超长周期仍需要另外评估计算耗时。

## 静态检查与环境限制

- 本次生产代码与新增错峰测试的 Black、isort、flake8 检查通过；`git diff --check` 通过。
- 默认 SQLite 迁移建库遇到既有错误：`NewSessionEventRelation has no field named 'event'`；未修改历史迁移。
- 已执行全仓 `make test`（SQLite、禁用迁移和覆盖率、首错停止），收集 `apps/apm/tests/test_alert_handlers.py` 时失败：
  `ApmApplication ... isn't in an application in INSTALLED_APPS`。本机当前 app 配置未启用 APM，全仓门禁未通过。
- 扩大到全部节点同步测试时，既有 `test_changed_hosts_schedule_relation_reconcile_once` 等路径尝试连接 NATS，
  环境不具备该服务；中止该扩大范围运行（当时 218 项通过），最终直接相关回归使用外部接口替身完成。
- 本机不是 Linux；未运行两项既有 Linux `/proc` / one-shot 资源限制测试。没有宣称全仓或生产容量验收通过。
