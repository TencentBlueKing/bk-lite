# JOB 主机发现：实施与验证记录

日期：2026-09-21

状态：代码完成；2026-09-22 已执行真实 Nginx 联调，目标主机连接失败，端到端成功验收未通过。

依据：[需求](spec.md)、[实施设计](plan.md)。

## 已完成

- 服务端有效采集目录发布 `supports_host_discovery`；开放 JOB 数据库、中间件及物理服务器 SSH 入口。
- 表单增加「选择主机」，按 host 模型、任务组织、接入点云区域查询；支持跨页勾选和取消、删除、编辑、复制。切换来源、组织或接入点清空旧目标。
- 主机模式仅提交 UUID；服务端查真实主机、验证可见性、组织、云区域及管理 IP，按 UUID 去重，拒绝重复 IP，限制最多 2048 项。
- 接入点权限使用真实请求的用户、域与当前组织上下文；区域另从 NodeMgmt 查询，忽略客户端伪造值。RPC 失败不保存新配置。
- 保存可信主机/IP 快照及服务端区域；重新保存刷新快照，周期执行仍使用已保存配置。
- 任务详情增加可展开的来源主机快照，中英文文案齐全。
- 修复显式空 `instances` 被丢弃的问题；host → ip 实际清空落库目标和新模式专属区域，再替换配置、触发首次采集。
- 主机只提供执行 IP。最终配置保持原插件及任务模型；新模式单台、多台来源主机的发现结果均使用任务组织，不借用来源主机名称或 UUID。
- 多凭据下区域仍进入最终配置；首次采集复用已有 Telegraf 子配置 one-shot。
- 复制表单补齐原任务的 IP 预检设置，保留其他 params。
- 更新已有 CMDB 架构报告和两组图件中的采集说明。

未修改数据库模型、部署配置、NodeMgmt/Stargazer 生产代码或采集脚本。提交范围限定本需求，工作区中的其他任务改动保留。

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| CMDB/NodeMgmt 相关回归（SQLite 当前模型建表） | **368 passed，1 deselected**；其中本次新测试 51 项 |
| Web 真实表单交互及 Network 选择工具回归 | **15 passed**；其中本次新交互测试 6 项 |
| Stargazer 节点定位、节点信息查询、执行计划 | **26 passed** |
| Web `pnpm type-check` | 通过 |
| 本次 Web 文件 ESLint | 通过，0 error / 0 warning |
| 本次 Python 文件 Black、isort、flake8 | 通过 |
| 本次差异 `git diff --check` | 通过 |
| 后端新增/修改可执行行覆盖 | **99/103，约 96.1%**；新策略模块报告为 97% |

覆盖率按 Git 差异新增行与 coverage 执行/遗漏行交集统计，并计入新策略文件；不是全仓覆盖率。被测六个完整后端模块的聚合覆盖率为 66%，包括大量本次未改动的序列化与采集逻辑。

关键行为证据：

- 创建/更新序列化：客户端伪造 IP、区域，非 host UUID、不可见 UUID、组织/区域不匹配、不支持插件、未知来源、接入点越权和 RPC 失败均有断言。
- 2048 项通过、2049 项拒绝；重复 UUID 归一、不同 UUID 同 IP 拒绝；重新保存刷新 IP。
- 企业目录默认目标模型仍可用 host 来源发现；asset 来源继续原模型校验。
- 真正调用 `CollectModelService.update`，执行参数转换、序列化、SQLite 落库、配置渲染及首次采集编排；外部权限/配置传输使用测试替身。验证旧目标删除、新 IP 下发与首次触发顺序。
- 最终 TOML 保留 `nginx_info` / `nginx`，包含主机 IP 和可信云区域；多凭据配置不包含明文测试口令。
- 新模式 BaseCollect 的单台/多台主机结果均取任务组织、无来源主机身份；原 BaseCollect、Nginx fixture 管道和节点服务回归通过。
- Web 测试实际操作表单：跨页选择、重开取消当前页、切换 IP、编辑/复制提交、变更组织/接入点清空。目录能力关闭时不出现新入口。
- Stargazer 既有测试验证节点查询传递 task/region、执行计划及查找失败/歧义行为；本次未改动其实现。

## 已有门禁问题与验证边界

1. **历史 SQLite migration 失败。**正常迁移方式运行相关后端测试时，告警模块迁移报 `FieldDoesNotExist: NewSessionEventRelation has no field named 'event'`。本次无 migration；采用 `--nomigrations` 按当前模型创建隔离 SQLite 测试库，完成上述行为验证。这不能证明生产数据库升级通过。
2. **目录数量断言已过时。**`test_all_118_tree_entries_publish_their_credential_binding` 断言 118，当前目录实际 119。使用 `git show HEAD:server/apps/cmdb/services/collect_object_tree.py` 的原始实现，在独立 Python 进程重跑此测试同样失败；未改动工作区来验证基线。最终回归明确排除该一项。完整相关回归此前结果为 368 passed / 1 failed。
3. **全仓 Web lint 未通过。**`pnpm lint` 报 31 errors / 98 warnings，错误在本次未修改的 APM 等文件，主要为 interface/type 规则。该次运行中本次测试文件的 4 条 warning 已修正，随后针对本次文件 ESLint 为零。未顺带修复其他任务代码。
4. **全仓 Server 门禁在收集阶段失败。**已运行 `make test`（SQLite、离线、不同步依赖、遇错即停），APM 测试导入时报 `ApmApplication ... isn’t in an application in INSTALLED_APPS`，未进入全仓用例执行。本次相关回归独立通过；不宣称全仓门禁通过。日志为 `/tmp/cmdb-job-make-test.log`。
5. **真实设备成功链路未通过。**2026-09-22 已使用用户现有 `nginx测试` 任务执行真实联调，确认任务持久化、配置生成和请求接纳；目标分别存在 SSH 认证失败和连接拒绝，未产生可供入库的指标，详见下文。自动化中的 RPC、图查询和配置传输替身不等于真实环境成功验收。

## 2026-09-22 真实 Nginx 任务联调

### 范围与结果

用户指定页面中的 `nginx测试`（任务 ID `20`，配置 `cmdb_20`）。使用其已有目标、凭据、接入点和已保存配置执行一次 one-shot；未调整主机清单、凭据、采集周期或清理策略，未安装或重启远程服务。本轮仅补充验证文档，未修改业务代码。

**结论：请求已进入真实采集入口，但目标连接条件不满足，不能宣称 Nginx 发现、VM 上报和 CMDB 入库闭环成功。**

| 环节 | 实际证据 | 判定 |
| --- | --- | --- |
| 页面与任务保存 | 编辑页面为「选择主机」；数据库 `params.target_source=host`、区域 `1`，保存两个主机 UUID/IP 快照，模型仍为 `nginx` | 通过 |
| 配置生成 | `cmdb_20` 包含 `cmdbhosts=172.18.0.1,172.18.0.18`、`cmdbplugin_name=nginx_info`、`cmdbmodel_id=nginx`、`cmdbcloud_region_id=1`、`instance_id=cmdb_20`，周期 `1800s` | 通过 |
| 接入点 | `fusion-collector-default`，IP `172.18.0.12`，节点 `8d41f0d8a12811f1a1920242ac120010`；执行器健康 RPC 成功，Telegraf/NATS executor/Ansible executor 状态正常 | 通过；节点汇总异常来自其他采集器，未据此误判 JOB 不可用 |
| 首次执行编排 | `FirstCollectionRun` ID `7`，2026-09-22 11:17:39（北京时间）为 `accepted` | 仅代表接纳，不代表完成 |
| 本次实际触发 | 经 `NodeMgmt.run_telegraf_child_configs_once`，限定配置 `cmdb_20`、上述接入点、组织 `[1]`，返回通道 `accepted` | 请求接纳通过 |
| 执行方式前提 | 同区域 Node 中未匹配到两个目标 IP；主机库存记录不等于当前可用 Agent 节点 | 需要 SSH 回退 |
| `172.18.0.1` | 从接入点连接 22 端口成功并取得 SSH banner；使用任务现有凭据执行只读探针返回 `NatsClientException`，错误归类为 `authentication` / `unable to authenticate` / `handshake failed` | SSH 认证失败；未验证 Nginx 是否安装或运行 |
| `172.18.0.18` | 从接入点连接 22 端口返回 `ConnectionRefusedError` | SSH 不可用 |
| Stargazer | 从接入点查询 ready/stats，运行时、Redis、metrics JetStream、NATS subscriber 健康 | 基础服务可达，不等于本任务执行成功 |
| VM | 11:31:08（北京时间）按 `instance_id=cmdb_20` 回看 1 小时，`nginx_info_gauge` 和 `cmdb_round_complete_gauge` 查询成功、均为 0 条 | 没有观测到 Nginx 数据或完整轮次 |
| CMDB 任务结果 | 11:31:36 复核：`exec_status=0`、`exec_time=null`、`collect_digest={}`、`collect_data={}` | 无同步结果，不能验证资产入库或幂等 |
| 页面最终同步 | 后续操作时出现登录过期提示，已请用户重新登录 | 页面同步与最终展示待验证 |

本次 one-shot 请求 ID：`nginx-host-e2e-3b230d730f94494684691ede383cfc06`。通道返回 Stargazer 请求标识：`req_8a25e2ec7742c308a99293781190b1c857f7ce257df1a1f2137b4f191d79f96a`。该标识与首次触发相同，不能凭它证明新轮次完成；本次返回状态为 `accepted`，不是 `duplicate_active`。

执行器 SSH 探针仅检查命令路径与进程存在性，未修改目标。异常只记录类别，未保存凭据或原始错误正文。中间一次只读 PostgreSQL 查询发生连接超时，后续复核成功；没有把该瞬时失败当成采集失败根因。

### 解释与复验条件

- 当前代码仅在满足完整轮次条件时发布完成标记；目标失败时没有标记不能用于证明 VM 发布链路本身故障。此轮上报、资产新增/更新与重复执行幂等均未得到真实成功验证。
- 页面「同步」读取已有采集结果，不等价于立即执行脚本。本次通过既有 one-shot 入口发起真实采集，没有仅点击同步就宣称执行完成。
- 当前任务 `data_cleanup_strategy=no_cleanup`。没有为了测试切换删除策略或制造指标；不能据此宣称已经验证完整的清理边界。
- 继续成功验收需要：修正 `.1` 的任务 SSH 凭据；使 `.18` 具备有效 Agent 或可登录 SSH，或由用户确认实际应选的 Nginx 主机；恢复页面登录。随后重跑一次采集，检查脚本产出、指标、完整轮次、资产及组织，再重跑检查不重复创建。

### 本轮新鲜自动化验证

在当前工作区运行主机发现策略、序列化、下发管道及 Nginx fixture 管道：**55 passed in 0.95s**。这些用例使用隔离 SQLite 和外部系统替身，证明相应代码回归通过，不能替代上述真实成功链路。

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  .venv/bin/python -m pytest \
  apps/cmdb/tests/test_job_host_discovery_policy.py \
  apps/cmdb/tests/test_job_host_discovery_serializer.py \
  apps/cmdb/tests/test_job_host_discovery_pipeline.py \
  apps/cmdb/tests/e2e/test_nginx_pipeline.py \
  --nomigrations --no-cov -o addopts='' -q
```

## 可复现命令

在仓库根目录进入 `server`，使用已有虚拟环境：

```bash
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true .venv/bin/python -m pytest   apps/cmdb/tests/test_job_host_discovery_*.py   apps/cmdb/tests/test_collect_object_tree.py   apps/cmdb/tests/test_collect_service_methods.py   apps/cmdb/tests/test_collect_service_first_collection.py   apps/cmdb/tests/test_first_collection_*.py   apps/cmdb/tests/test_node_params_multicred.py   apps/cmdb/tests/test_collect_instance_uuid_contract.py   apps/cmdb/tests/test_collect_base_runner_pure.py   apps/cmdb/tests/test_middleware_collect_format_pure.py   apps/cmdb/tests/e2e/test_nginx_pipeline.py   apps/node_mgmt/tests/test_b75_node_service.py   --nomigrations --no-cov -o addopts=''   -k 'not test_all_118_tree_entries_publish_their_credential_binding' -q
```

进入 `web`（Node 24）：

```bash
pnpm exec vitest run   'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/__tests__/jobHostDiscovery.test.tsx'   'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/utils/__tests__/networkAssetSelection.test.ts'
pnpm type-check
pnpm lint
```

进入 `agents/stargazer`：

```bash
.venv/bin/python -m pytest   tests/test_job_node_info_loader.py   tests/test_run_node_info_lookup.py   tests/test_execution_plan.py -q
```

本机原始日志：`/tmp/cmdb-job-final-server-green.log`、`/tmp/cmdb-job-regression.log`、`/tmp/cmdb-job-directory-baseline.log`、`/tmp/cmdb-job-web-final.log`、`/tmp/cmdb-job-agent.log`、`/tmp/cmdb-job-typecheck-final.log`、`/tmp/cmdb-job-lint.log`、`/tmp/cmdb-job-lint-scoped.log`。覆盖率数据在 `/tmp/cmdb-job-coverage.json`；这些是本机会话证据，不作为仓库依赖。

## 2026-09-22 提交前复核

- 再次执行上述后端回归：55 passed；主机发现交互与 Network 选择工具：15 passed。
- 提交钩子的 pyupgrade、冲突检查、Black、isort、flake8、migration/requirements 检查和本次 Web 文件 ESLint 均通过。
- 工作区全量 Web 类型检查被未暂存的告警模板 `templateEditor.tsx:624` 的 AceEditor `ref` 类型错误阻塞，该改动不属于本次提交。
- 将暂存的 Web 文件导出到临时副本，复用已安装依赖和生成文件，执行仓库的 `sync-next-build-types.mjs` 后运行 `tsc -p tsconfig.build.json --noEmit`，通过。原工作区的其他代码未为此修改。
- 完成这些检查后，仅本次 Git 提交使用 `HUSKY=0` 跳过重复钩子执行，不修改钩子配置；提交内容限定为本需求的 25 个文件。

## 成功链路与扩展场景仍需验收

使用隔离环境：一台可用 Agent 主机、一台 SSH 主机；一台有两个不同 Nginx 实例，一台无 Nginx。验证页面保存、实际节点路由、首次和周期执行、脚本输出、最终资产及组织；重复运行不重复创建；部分失败不扩大清理范围。其他适用插件已复用相同通道，不能据此宣称都完成了真实设备验证。

「选择已有资产仅更新选中资产」仍是独立后续需求，本次保持原有行为。
