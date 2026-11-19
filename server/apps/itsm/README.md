# ITSM

本目录目前包含基线核对和 M1-02 骨架。模型与业务接口留到后续任务。

健康检查：`GET /api/v1/itsm/api/health/`，免登录，返回 Flowable 是否返回 200。

`init_realm_resource` 会把名为 `manager` 的角色改成全部菜单。菜单文件里的 `itsm--manager` 不含 `setting`，入库后会被这条平台逻辑盖掉。

## M1 已实现

- Flowable 7.1 本地编排，REST 前缀 `/flowable-rest/service`。
- 表单 schema 校验、设计 JSON 转 BPMN、附录 B 可部署。
- 表单、字典、流程设计/发布、处理组、通知模板接口。
- 工单创建与 submit/approve/reject/claim。或签在本地 Flowable 上跑通：一人通过后另一人任务结束，处理完成后状态为 finished。
- 新任务通过 `itsm_event` 调控制台 `create_notification`，接收人写入 `recipient_usernames`。外部消息优先用已就绪的 IM 应用通知（飞书、企微），否则用飞书或钉钉机器人通道，经 `send_msg_with_channel` 发出。
- 前端门户、表单设计、流程画布、工单列表和详情。门户可建服务并提单；详情含表单、待办动作、流转日志和节点进度。
- `batch_init` 与 `make server-init` 会执行 `init_itsm`，并尝试 `init_itsm_itil`（请求、事件、问题流程和 SLA）。
- M2：工单动作含响应、催办、挂起、恢复、转单、退回提单/上一节点、撤回、终止、关闭、重新打开；列表可按创建人、优先级、标签、时间和标题/单号过滤，并带 SLA 截止；评论、附件、关注、标签、关联；流程版本列表、导入导出与启用；变量可测试；SLA 可分类启停；数据表支持 Excel。
- M3 到 M5 的本地对象在 `/api/resources/<kind>/`。已验证：批量催办、xlsx 导出、决策表命中、触发器打标签、OpenAPI 双组织隔离、NATS `itsm_create_ticket`、打印模板、本机作业、DMN 部署、10 万单列表、本地 eml 收信、知识页同步。
- 仍依赖外部环境、本机收不了口：已发布的编排流程和 Conductor、FalkorDB、OpsPilot 对话、Django Channels、待办 HTTP 的公网地址（本机回环会被 SSRF 拦住）。

## 自动节点恢复

- 自动节点失败原因显示在工单的「流转日志」。可查看该工单，且同时具备工单操作和流程编辑权限的用户可请求重试。确定动作未发生时才重跑动作。已记录动作成功的执行仅补交流程推进。外部结果未确认时，先核对外部系统，系统不会重放。重试请求写入流转日志。

## 定时建单

- 「规则与时效 → 定时任务」支持单次和五段 Cron，周期采用平台时区。建单按执行时可用的已发布版本和配置人的实时权限校验，自动完成提单节点。执行记录保留关联工单和失败说明，可从记录打开已创建的工单。
- 每个任务和计划时间只领取一次。停机后每项周期任务最多补执行一个到期时点。引擎启动结果不明确时，该次执行留档待核对。若工单已创建但提单节点推进失败，可打开同一工单继续处理。
- 升级会暂停旧定时任务及其旧版调度，检查配置后重新启用。新任务由 Celery Beat 的 `itsm-schedule-tick` 分发，请在应用迁移后重启 Beat 和 Worker。

## SLA 预警与升级

- 「规则与时效 → SLA」按流程绑定响应或解决时限。预警按服务窗口计算并通知当前处理人，超时升级发送给指定的当前组织用户。0 分钟关闭预警，升级对象留空时只标记超时。
- 工单开始计时时保存规则与服务窗口。挂起时冻结剩余工作时间，恢复后按原窗口继续计时。已发送的预警不会因挂起恢复而重发。
- 工单详情的「SLA」记录触发时间、接收人和发送结果。每条 SLA 计时记录的预警及升级各执行一次。没有有效接收人时记为跳过，通知写入失败时留档。

## 工单后台导出

- 在「工单中心」按当前筛选或勾选范围提交 Excel 导出，可附加所选流程的表单字段。每个任务最多 5000 条，文件最多 8 MB。
- 「导出记录」按当前账号和组织展示排队、生成、完成及失败。失败可重新提交，保留原记录。文件可下载 7 天，下载时重新核对工单及字段权限。
- 部署时应用迁移 `0017_async_ticket_export`，并重启消费 `background` 队列的 Celery Worker。历史同步导出接口保留原有 JSON 响应字段和 500 条上限。

## 基线核对

核对日期：2026-11-06。工作分支 `feature_itsm`。

### 上游提交

| 项 | 值 |
|---|---|
| 当前 HEAD | `68eb738e06faf258eb666084ada46a5947696e70` |
| 提交说明 | Merge pull request #6942 from CharlesWhj/master |
| 与 `weops/master` | 2026-11-06 15:22 再次 fetch 后，HEAD 与 `weops/master` 同为 `68eb738e`，没有更新的提交 |
| 计划核对点 | 《开发计划》V1.1 写的上游核对点是 `17174186`。该提交已被更新的上游合并超过。后续开发以当前 HEAD `68eb738e` 为基线，不以 `17174186` 为准 |

### 阅读范围

0.1 列出的五份文档在仓库中均存在：

- `specs/capabilities/openapi-gateway.md`
- `server/apps/core/openapi/README.md`
- `server/apps/job_mgmt/docs/open_api.md`
- `server/apps/workflow/docs/open_api.md`
- `server/apps/workflow/atom_packages/README.md`

同时核对了 `server/apps/job_mgmt/` 与 `server/apps/workflow/` 的 models、`nats_api.py`、`openapi_api.py`，以及编排启动执行的服务函数。

### job_mgmt NATS 方法

签名从 `@nats_client.register` 的函数定义抄录。`nats_api.py` 里另有同进程函数 `execute_automation_script_local`、`execute_automation_file_distribute_local`、`list_automation_targets_local`，未注册为 NATS 方法，不列入下表。

| 函数 | 签名 | 所在文件 |
|---|---|---|
| `get_job_mgmt_module_list` | `get_job_mgmt_module_list()` | `server/apps/job_mgmt/nats_api.py` |
| `get_job_mgmt_module_data` | `get_job_mgmt_module_data(module, child_module, page, page_size, group_id, *, team=None)` | 同上 |
| `job_script_detail` | `job_script_detail(data: dict)` | 同上 |
| `job_list` | `job_list(data: dict)` | 同上 |
| `ansible_task_callback` | `ansible_task_callback(data: dict)` | 同上 |
| `job_script_execute` | `job_script_execute(data: dict, **_ignored)` | 同上 |
| `job_file_distribute` | `job_file_distribute(data: dict)` | 同上 |
| `job_status_batch_query` | `job_status_batch_query(data: dict)` | 同上 |
| `job_detail_query` | `job_detail_query(data: dict)` | 同上 |
| `job_task_terminate` | `job_task_terminate(data=None, task_id=None, **kwargs)` | 同上 |
| `job_target_list` | `job_target_list(data: dict)` | 同上 |
| `get_job_usage_statistics` | `get_job_usage_statistics(user_info=None, time=None, **kwargs)` | 同上 |
| `job_opspilot_action` | `job_opspilot_action(data: dict)` | `server/apps/job_mgmt/nats_opspilot.py` |

计划点名的五个方法都在：`job_list`、`job_script_execute`、`job_status_batch_query`、`job_detail_query`、`job_target_list`。参数都收在 `data: dict` 里，不是展开的具名业务参数。`job_script_execute` 额外忽略调用方 kwargs。

作业模型在 `server/apps/job_mgmt/models/`：`Script`、`Playbook`、`JobExecution`、`Target`、`DistributionFile`、`ScheduledTask`、`DangerousRule`、`DangerousPath`、`JobCompletionOutbox`，以及脚本 / Playbook 修订。

### 编排中心启动执行

进程内启动已发布流程的服务函数是 `apps.workflow.services.runtime.start_execution`，不是 `services/executions.py`。`executions.py` 负责把 Conductor 远端状态同步回本地执行记录。引擎客户端 `ConductorClient.start_workflow` 由 `start_execution` 在落库后调用。

```python
def start_execution(
    workflow: Workflow,
    *,
    inputs: dict[str, Any],
    started_by: str,
    domain: str,
    client: ConductorClient | None = None,
    version_number: int | None = None,
    mode: str = WorkflowExecution.Mode.PRODUCTION,
    trigger_type: str = "FORM",
    trigger_id: str = "",
    parent_execution: WorkflowExecution | None = None,
    launch_token_hash: str | None = None,
    target_snapshot: dict[str, Any] | None = None,
    entry_input_schema: dict[str, Any] | None = None,
    async_callback_context: dict[str, Any] | None = None,
    async_callback_deadline_at=None,
    async_callback_key: str | None = None,
) -> WorkflowExecution:
```

网关入口与详设「等价于 OpenAPI `workflow/execute-async`」一致：

```python
def openapi_workflow_execute_async(workflow_id, callback_context, inputs=None, *, team=None, user_info=None):
```

路径 `POST /openapi/v1/workflow/execute-async`。列表入口是 `openapi_workflow_list`，路径 `workflow/workflows`。

模型 `Workflow`、`WorkflowExecution`、`WorkflowInteraction` 都在 `server/apps/workflow/models.py`。

### IMNotificationChannel 支持的 IM 类型

`IMNotificationChannel` 本身没有 IM 类型枚举。类型来自所绑定 `IntegrationInstance.provider_key`，且该 provider 必须声明 `im_notification` 能力。

当前内置 provider 里声明了该能力的只有：

| provider_key | 适配器 |
|---|---|
| `feishu` | `feishu.im_notification`（`server/apps/system_mgmt/providers/builtin/feishu/manifest.py`） |
| `wecom` | `wecom.im_notification`（`server/apps/system_mgmt/providers/builtin/wecom/manifest.py`） |

没有钉钉 provider，也没有钉钉的 `im_notification` 适配器。模型里的外部身份字段文案仍写着 Feishu User ID / Open ID，不代表只支持飞书。

`system_mgmt.Channel`（`ChannelChoices`）是另一套渠道，当前取值：`email`、`enterprise_wechat`、`enterprise_wechat_bot`、`nats`、`feishu_bot`、`dingtalk_bot`、`custom_webhook`。机器人群通知里的飞书 / 钉钉走 `Channel`，不走 `IMNotificationChannel`。

### system_mgmt.Group 负责人字段

没有。`Group`（`server/apps/system_mgmt/models/user.py`）字段为：`name`、`description`、`parent_id`、`external_id`、`roles`、`is_virtual`、`allow_inherit_roles`、`sync_source`、`is_delete`。没有 `leader`、`owner` 或负责人字段。

「提单人上级」第一期按已定决策使用 `HandlerGroup.leaders`，不依赖 `Group`。

### OpsPilot 知识库写入接口

有写入接口，路径不在详设写的 `knowledge_mgmt`。

`server/apps/opspilot/urls.py` 当前知识库路由前缀是 `wiki_mgmt`。旧表 `knowledge_mgmt_*` 只出现在早期 migration 和过时的查询说明里，现行 urls 没有 `knowledge_mgmt`。

可用的写入路径（挂在 `/api/v1/opspilot/` 下）：

| 方法 | 路径 | 行为 |
|---|---|---|
| POST | `wiki_mgmt/page/` | `WikiPageViewSet.create`，调用 `create_manual_page` 写知识页面（title / body） |
| PUT / PATCH | `wiki_mgmt/page/{id}/` | 更新知识页面 |
| POST | `wiki_mgmt/knowledge_base/{id}/import_markdown_preflight/` | 上传文件做导入预检，不直接落页面 |
| POST | `wiki_mgmt/knowledge_base/{id}/import_markdown_execute/` | 按预检 token 或 options 执行导入并写入 |
| POST | `wiki_mgmt/knowledge_base/{id}/import_markdown/` | 兼容旧入口，实现上转去预检，不绕过 token 直接写入 |
| POST | `wiki_mgmt/material/` | `WikiMaterialViewSet.create`，写入资料 |

没有 `@openapi_expose` 的 OpsPilot 知识库写入网关。M3 同步若走进程内或控制台 REST，应使用 `wiki_mgmt/page/` 或 `import_markdown_execute/`，不要调用 `knowledge_mgmt`。

### 与《详设》不一致

| 详设 / 计划表述 | 代码事实 | 后续怎么用 |
|---|---|---|
| 开发计划基线提交 `17174186`（2026-11-06 上游 master） | 当前 `weops/master` 与 HEAD 是 `68eb738e`（Merge pull request #6942），已超过 `17174186` | 基线以 `68eb738e` 为准 |
| 作业联动只列 NATS `job_list` / `job_script_execute` / `job_status_batch_query` / `job_detail_query`（计划另加 `job_target_list`） | 注册方法共 13 个，见上表；另有 OpenAPI `job-mgmt/script-execute`、`script-execute-async`、`job-status`、`job-detail` | M1 仍按决策直接调已有 NATS；调用时带上代码里的 `data: dict` 契约，不要按展开参数发明签名 |
| 计划 0.3 把编排启动服务写成 `services/executions.py`、`services/conductor.py` | 启动函数是 `services/runtime.py` 的 `start_execution`；`executions.py` 只做执行状态同步；`ConductorClient.start_workflow(name, *, version, inputs, correlation_id="")` 是引擎 HTTP 客户端 | 进程内调用 `start_execution`。网关等价入口仍是 `workflow/execute-async`，与详设一致 |
| `IMNotificationChannel` 仅飞书（含用户映射）；企微 / 邮件走 `Channel`；钉钉若无则 M5 再补 | `im_notification` 能力同时挂在 `feishu` 与 `wecom`。`Channel` 除邮件、企微、企微机器人外，已有 `feishu_bot`、`dingtalk_bot`、`nats`、`custom_webhook`。没有钉钉 IM 通知 provider | 飞书、企微的用户映射通知走 `IMNotificationChannel`。钉钉仍无该通道。群机器人飞书 / 钉钉用现有 `Channel`，不在 ITSM 里新做 |
| `system_mgmt.Group` 可能有组织负责人 / leader，用于「提单人上级」 | `Group` 无负责人字段 | 按已定决策第一期用 `HandlerGroup.leaders` |
| OpsPilot 知识库写入走 REST `knowledge_mgmt`；若只有上传文件接口则上传 Markdown | 现行写入在 `wiki_mgmt`：页面创建 `POST wiki_mgmt/page/`，文件导入 `POST wiki_mgmt/knowledge_base/{id}/import_markdown_execute/`。`import_markdown/` 只做预检 | M3 同步指向 `wiki_mgmt`，不要接已不存在的 `knowledge_mgmt` 路由 |
| 在现有 Postgres 初始化脚本里创建库 `flowable` | 上游 `68eb738e` 没有平台级 Postgres 初始化脚本，仓库里也没有名为 `postgres` 的平台 compose | `deploy/flowable/initdb/01-create-flowable-db.sql` 供挂到现有实例；本地 `deploy/flowable/compose.yaml` 自带一个名为 `postgres` 的库，才能按 JDBC 主机名把 Flowable 拉起来 |
| 验收地址 `$FLOWABLE_URL/process-api/repository/deployments` | `flowable-rest:7.1.0` 的上下文是 `/flowable-rest`，仓库接口是 `/service/repository/deployments`，没有 `/process-api` | 本地验收用 `http://127.0.0.1:8088/flowable-rest/service/repository/deployments`。`FLOWABLE_URL` 仍是 `http://127.0.0.1:8088` |
