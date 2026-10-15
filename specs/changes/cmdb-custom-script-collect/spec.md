# CMDB 自定义脚本采集（自定义插件库）

Status: draft（设计五轮收敛，待用户整体确认后实施）

日期：2026-10-09。

## 1. 目标与范围

新增采集类型 `custom_script`：用户在**自定义插件库**中维护采集插件（脚本 + 凭据
声明 + 目标模型），创建采集任务时引用插件；脚本按约定格式输出 JSON，由 Stargazer
下发到目标机执行并回收数据，最终按既有采集对账逻辑写入 CMDB 实例。

核心设计原则（用户确认）：**`custom_script` 仅在"采集执行"环节使用自定义脚本，
下游（VM 查询之后的对账、入库、清理、变更记录、任务详情展示）与既有采集业务逻辑
完全一致，不新增任何对账/归属机制。**

本期完成：

- 自定义插件库：插件 CRUD、版本、凭据 schema 声明、删除保护、审计；
- 插件动态挂载到采集对象树，任务创建表单复用既有流程；
- Linux（SSH / 本地执行）与 Windows（WinRM）双路由执行；
- 按插件命名的独立指标与动态字段映射入库；
- 自定义插件任务与同模型内置任务（如 host）共存，互不干扰。

本期不做：

- 关联关系输出（脚本只产出单模型实例，不支持 `assos`）；
- "增强更新"入库模式（已否决，见 §12）；
- Windows 本地执行模式（Windows 固定 WinRM 远程，与 PC 采集一致）；
- 单目标"测试执行"预览（P1，见 §10）。

## 2. 已确认的关键决策

| # | 决策 | 结论与理由 |
|---|---|---|
| D1 | 插件库 | **独立表 `CustomCollectPlugin`**（用户修订：否决任务内嵌存储）。插件可被多个任务引用，统一版本与审计 |
| D2 | 脚本下发通道 | Stargazer 运行期经 NATS RPC 向 Server 拉取（复用 `get_nodes_by_ips` 模式）。否决 headers 透传脚本正文 |
| D3 | Windows 执行 | WinRM，经 `ansible_adhoc(connection=winrm, module=win_shell)`，与企业版 PC 采集器 `PCInventoryCollector._run_windows` 同构 |
| D4 | Linux 执行 | 复用 `SSHPlugin`（`local.execute`/`ssh.execute` 既有分流），为其增加 `script_content` 参数 |
| D5 | NodeParams 选择 | 哨兵键 `("custom_script", JOB)` 进现有自动注册表，工厂按 `task_type` 构造候选键。否决"查不到再回退"（自定义 host 任务会错误命中内置 `HostNodeParams`） |
| D6 | 下游对账 | 零改动。同模型内置/自定义任务共存走既有"各任务按 `collect_task` 隔离 + `inst_name` 唯一校验冲突进 failed"语义 |
| D7 | 一插件一 OS | 插件声明 `os_type`，创建后不可改（windows 固定 WinRM，linux 固定 SSH，借鉴 `pc_collect_policy`） |
| D8 | 指标命名 | **按插件命名 `{plugin_id}_info_gauge`**（用户修订：否决按 model_id 派生）。两个插件同指向 host 时指标各自独立；与内置"一插件一指标"惯例一致，不把隔离压在 `instance_id` 单一 label 上 |
| D9 | 凭据设计 | 传输凭据组按 `os_type` 系统固定（SSH 组 / WinRM 组）；业务凭据由插件 `credential_schema` 声明，加密字段 schema 驱动，脚本内占位符注入 |
| D10 | 业务凭据存放 | **独立存 `params.custom_credential_values`，只允许表单填写**。自定义脚本任务的登录凭据和业务凭据都不能选择凭据库。加密字段显式加密写入 params，明文不落库。传输凭据仍放凭据池，但 `credential_source` 必须是直填 |
| D11 | 脚本执行超时 | 脚本执行超时 = `min(任务 timeout, 600)`。现状 `SSHPlugin.execute_timeout` 硬编码 60s（自定义脚本可能不够），为其增加可选 `execute_timeout` 参数（默认 60，内置调用方行为不变）；windows 路径直接传给 `ansible_adhoc` |

## 3. 自定义插件库（阶段一）

### 3.1 数据模型

```python
class CustomCollectPlugin(MaintainerInfo, TimeInfo):
    name              # 显示名
    plugin_id         # 唯一标识，^custom_[a-z0-9_]{2,40}$（前缀表单自动补全），创建后不可改
    model_id          # 目标 CMDB 模型（任意现有模型）
    os_type           # "linux" | "windows"，创建后不可改
    shell             # linux: bash/sh；windows 固定 powershell
    content           # 脚本正文，≤ 64KB，UTF-8
    content_checksum  # sha256，Server 保存时计算
    version           # content 变更时递增
    credential_schema # 业务凭据字段声明，见 §3.3
    desc              # 描述（前端展示）
    team              # 关联组织（权限隔离）
```

约束与保护：

- `plugin_id` **全局唯一（跨组织）**：VM 指标空间全局共享，派生指标名必须全局
  唯一，因此 plugin_id 不能按组织分别唯一；重名时提示"标识已被占用"即可
  （不回显占用方信息）。`custom_` 前缀保证派生指标 `{plugin_id}_info_gauge`
  永不与内置指标（`nginx_info_gauge` 等）冲突，无需维护内置名单黑名单；
- **删除保护**：存在引用该插件的 `CollectModels` 时禁止删除（引用计数校验）；
- 编辑 content → version+1、checksum 重算；引用中的任务**下一轮 Run 自动生效**
  （Stargazer 每轮拉最新，见 §6.1），无需逐任务重推节点配置；
- `model_id`、`os_type`、`credential_schema` 中加密属性在有任务引用时锁定修改
  （变更会破坏在跑任务的表单/加密契约；需先解除引用）。

### 3.2 指标命名（决策 D8）

- 指标名固定派生：`{plugin_id}_info`（VM 侧呈现 `{plugin_id}_info_gauge`），
  不提供独立配置项——plugin_id 已唯一，再开一个自由命名字段只会引入二次冲突面；
- Stargazer 采集器返回 `{"result": {plugin_id: records}}`，
  `convert_to_prometheus_format` 按 dict 键自动产出该指标（机制零改动）；
- Server 同步按 `{plugin_id}_info_gauge{instance_id="cmdb_<task_id>"}` 查询，
  记录归入任务的 `model_id` 入库（指标名与模型名自此解耦，由格式化插件桥接）。

两个插件都指向 host 的场景：`custom_a_info_gauge` / `custom_b_info_gauge` /
内置 `host_info_gauge` 三路指标完全独立，查询互不可见。

### 3.3 凭据设计（决策 D9）

凭据分两层：

**传输凭据（系统固定，不可自定义）**——由 `os_type` 决定，用于连到目标机：

| os_type | 字段组 | 加密字段 |
|---|---|---|
| linux | username / password 或 private_key(+passphrase) / port(默认22) | password, private_key, passphrase |
| windows | username / password / port(默认5986) / winrm_scheme / winrm_transport / winrm_cert_validation | password |

**业务凭据（插件声明，可选）**——脚本自身需要的秘密（如脚本内连数据库的口令）：

```json
"credential_schema": [
  {"key": "db_password", "name": "数据库密码", "type": "password",
   "required": true, "encrypted": true},
  {"key": "api_token",  "name": "API Token",  "type": "password",
   "required": false, "encrypted": true},
  {"key": "db_port",    "name": "数据库端口",  "type": "text",
   "required": false, "default": "3306"}
]
```

- `key` 限小写蛇形且不得与传输凭据字段、系统参数（host/node_id/timeout 等
  header 保留字）冲突，serializer 维护保留字清单；
- **存放位置（决策 D10）**：业务凭据的值存 `params.custom_credential_values`
  （dict，按 schema key），**不进 `credential` 凭据池**。每个字段的值：

```json
{"db_port": {"source": "inline", "value": "3306"},
 "db_password": {"source": "inline", "value": "enc:..."},
 "api_token": {"source": "vault", "vault_credential_id": "crd-1",
               "vault_field": "token",
               "vault_actor_context": {"username": "...", "domain": "...", "current_team": 1}}}
```

  - 明文文本字段只允许 `source=inline`；
  - `encrypted` 字段允许 `inline`（serializer 显式加密后写入，`save()` 不覆盖
    params，必须补这一处并配测试）或 `vault`；
  - vault 引用只存凭据 ID、取值字段名和服务端绑定的操作者上下文
    （浏览器提交的 `vault_actor_context` 不可信，复用
    `CollectModelService._bind_vault_credentials` 的写入方式）；
  - **解析时机是下发构建**（`CustomScriptNodeParams`），调用既有
    `SystemMgmt.resolve_credential`：凭据类型必须包含 `vault_field`，且该字段
    为秘密类；解析出的明文只进入内存中的 env 间接引用，不写回任务；
    凭据不可用/类型不含该字段/操作者无权 → 下发失败并给出稳定错误，不静默回退直填；
- `encrypted: true` 字段下发走 env 间接引用（同现有 `${PASSWORD_xxx}` 机制），
  不明文落节点 Telegraf 配置；
- **脚本内注入方式：占位符** `{{credential.<key>}}`，由 Stargazer 采集器在内存中
  渲染（与既有 `{{bk_host_innerip}}` 同机制）。渲染后的脚本含秘密：content 本就
  全链路禁止落日志（§8），错误路径按 `_scrub_secrets` 模式对已知秘密值精确替换。

**加密链路改造**：`get_collect_model_passwords` 增加 task_type 分支——
`custom_script` 任务的加密字段 = 传输凭据固定集（按 os_type）∪ 插件
`credential_schema` 中 `encrypted: true` 的 key。替代现状"按 model_id 查对象树"
（任意 model_id 查不到会导致**密码明文落库**，这是必须修的安全点）。
配回归测试断言保存后全部加密字段带 `enc:` 前缀。

### 3.4 插件库管理（Server + Web，两个入口一个实体）

- CRUD API：`views/serializers` 常规实现，权限复用 team + MaintainerInfo；
- **组织隔离（用户确认为硬要求）**：插件按 `team` 隔离，所有读写面统一过滤，
  复用采集任务（`CollectModels.team`）既有的组织过滤语义（含超管行为）：
  - 插件列表 / 详情 / 编辑 / 删除：只能操作当前用户组织范围内的插件；
  - 对象树动态挂载（§3.5）：树 children 按请求用户组织过滤，别组织的插件
    不出现在采集对象树；
  - 模型详情"自定义采集"tab：同一过滤；
  - 任务创建/更新引用插件：Server 侧校验 `custom_plugin_pk` 在用户组织范围内，
    防止绕过前端直接提交越权引用；
  - `cmdb_get_custom_script` RPC：经任务解析插件，任务自身 team 边界即隔离，
    不走用户态过滤（内网平面，与 `get_nodes_by_ips` 同级）；
- 校验：plugin_id 格式/唯一、content 大小与 UTF-8、shell 与 os_type 匹配、
  credential_schema 形状与保留字、锁定字段修改拒绝；
- 审计：插件创建/编辑走变更记录，**快照只记 version + checksum，不含脚本正文**；
- **入口一（插件库总览）**：Web 新增"自定义插件"管理页。交互形态已确认
  **在线编辑为主、上传为辅**（否决纯上传黑盒，见 §12）：
  - 列表：名称 / plugin_id / 目标模型 / OS / 版本 / 引用任务数 / 更新时间；
  - 详情编辑：脚本编辑器在线查看与修改；支持上传脚本文件（.sh/.ps1），
    **上传仅填充编辑器，经预览确认后保存**——保存即递增版本并对引用中任务
    下轮生效，误传文件必须有确认挡板；被引用插件保存时提示受影响任务数；
  - 凭据声明用 JSON 文本编辑（2026-10-10 确认，不再做逐项表单）。
    此处只维护字段声明；凭据的值在任务创建时表单填写，插件页不触碰值；
  - 输出契约文档内嵌展示；
  - 整插件导出/导入（JSON 包，用于跨环境迁移）列 P1；
- **入口二（模型配置定义）**：模型详情（`assetManage/management/detail`）新增
  "自定义采集"tab——`CustomCollectPlugin` 按 `model_id = 当前模型` 的过滤视图 +
  快捷创建（表单预填且锁定 model_id）。自建私有模型（无任何内置采集）的用户在
  模型管理现场即可定义采集脚本，不需跳转。两个入口读写同一张表，不新增概念。

**引用保护链** `模型 ← 插件 ← 任务`，逐级禁删：

- 插件被任务引用 → 插件禁止删除（§3.1 已列）；
- 模型被插件绑定 → **模型删除校验新增一条**：存在绑定的自定义插件时阻止删除
  （提示先处理插件），避免孤儿插件与失效任务。

### 3.5 对象树动态挂载

`collect_object_tree.py` 构建树时，在"自定义"分组下**按插件库动态生成 children**
（按请求用户的组织范围过滤，见 §3.4 组织隔离）：

```python
{"id": plugin.plugin_id, "model_id": plugin.model_id, "name": plugin.name,
 "task_type": "custom_script", "type": "job",
 "encrypted_fields": <传输固定集 ∪ schema encrypted keys>,
 "credential_type_keys": ["host/ssh"] 或 ["host/winrm"],  # 按 os_type
 "desc": plugin.desc, "tag": ["自定义", plugin.os_type]}
```

前端任务创建流程因此与内置对象完全同构（树节点 → 表单 → 凭据渲染），
业务凭据字段由 schema 追加渲染。

## 4. 脚本输出契约（面向用户）

- stdout 输出 JSON 数组 / 单对象 / NDJSON 均可（`SSHPlugin._parse_collect_output`
  现成支持），stderr 忽略；退出码非 0 视为该目标失败。
- 每条记录 `inst_name` 必填且非空——CMDB 实例对账唯一键；缺失记录丢弃并计数。
- 字段名需与目标模型的属性 ID 一致；模型中不存在的字段被丢弃。
- 字段值经 VM label 传输后均为字符串，Server 按模型属性类型转换（见 §7.3）。
- **字段值必须是标量**：嵌套对象/数组经 prometheus label 传输时会被静默过滤，
  需要结构化内容请自行序列化为 JSON 字符串输出。
- **同一轮输出中 `inst_name` 必须唯一**：重复 inst_name 在对账时去重（后者覆盖
  前者），不报错。
- 占位符：`{{bk_host_innerip}}` 当前目标 IP；`{{credential.<key>}}` 业务凭据值。
  占位符为纯文本替换：凭据值含引号、`$` 等 shell 敏感字符时需脚本自行处理
  （如经 base64 中转）。
- 脚本以传输凭据的用户身份执行；执行超时为 min(任务超时, 600 秒)；
  秘密不得写入脚本输出。

示例：

```json
[{"inst_name": "192.168.1.10-myapp-8080", "ip_addr": "192.168.1.10",
  "port": "8080", "version": "1.2.3"}]
```

## 5. 阶段二：配置采集任务（创建 → 下发）

### 5.1 类型与任务模型

- `CollectPluginTypes` 新增 `CUSTOM_SCRIPT = "custom_script"`；`driver_type` 固定 `JOB`；
- 任务引用插件：`params.custom_plugin_pk = <CustomCollectPlugin.id>`（外键语义，
  删除保护在插件侧校验）；`model_id` 从插件带出，创建后随内置任务同规则；
  create/update 时 Server 校验所引用插件在当前用户组织范围内（§3.4）；
- 其余字段全复用：`name / ip_range / instances / access_point / credential(凭据池，
  仅传输凭据，轮换语义不变) / cycle / timeout / data_cleanup_strategy /
  input_method`；业务凭据值独立存 `params.custom_credential_values`（D10）；
- `unique_together("name", "driver_type", "model_id")` 不受影响。

### 5.2 NodeParams（决策 D5）

```python
class CustomScriptNodeParams(BaseNodeParams):
    supported_model_id = CollectPluginTypes.CUSTOM_SCRIPT  # 哨兵键，不与真实模型撞名
    supported_driver_type = CollectDriverTypes.JOB
    plugin_name = "custom_script_info"   # Stargazer 侧统一执行插件
```

- 自动注册钩子 `__init_subclass__` 零改动；
- `NodeParamsFactory.get_params_class` 候选键按 task_type 构造：
  `custom_script` → `[("custom_script", driver), ("custom_script", None)]`，
  其余任务现状不变；`BaseNodeParams.model_plugin_name` 同步增加该分支；
- `set_credential()`：按插件 os_type 输出传输凭据（linux 复用
  `SSHNodeParamsMixin` 逻辑，天然含 `node_id`；windows 输出 winrm 组，
  **必须同样输出 `node_id`**——ansible_adhoc 按 `ansible_node_id` 路由到
  接入点的 ansible-executor）；
- 业务凭据：`params.custom_credential_values` 各字段以 `cmdb<key>` 下发，
  加密字段一律 env 间接引用（`env_config()` 按 schema 驱动生成）；
- `custom_headers()` 追加：`cmdbcustom_plugin_id / cmdbos_type / cmdbshell`。
  **脚本正文与版本号均不进 headers**——脚本以每轮 RPC 拉取为准（§6.1），
  插件编辑不需要重推节点配置。

### 5.4 任务生命周期 task_type 开关点审计（实施清单）

`custom_script` 必须走默认 VM 同步路径。实施时逐一核对现有按 task_type/模型分支
的开关点，确认自定义任务落入默认分支且行为正确：

- `tasks/celery_tasks.py`：CONFIG_FILE 跳过分支、SNMP/network 拓扑分支、
  `uses_vm_reconciliation`、周期对账的排除名单（现排除 CONFIG_FILE/K8S）、
  轮次解析逻辑；
- `services/collect_service.py`：`should_register_sync_beat` /
  `should_sync_node_params` / `exec_task`（手动立即执行）/
  `FirstCollectionOrchestrator`（首采调度）；
- `services/collection_offset_policy.py`：未登记插件不参与错峰，确认
  `custom_script_info` 不需登记即安全跳过。

每处核对结果记录到实现 PR 描述；行为异常处补分支与测试。

### 5.3 下发链路

零改动：`create/update → push_butch_node_params → NodeMgmt.batch_add_node_child_config
→ Telegraf [[inputs.http]] 周期调 Stargazer /api/collect/collect_info`；
节点配置 ID `cmdb_<task_id>` 按任务隔离。

## 6. 阶段三：Stargazer 采集

### 6.1 脚本拉取 RPC

Server `server/apps/cmdb/nats/nats.py` 新增 responder：

```python
@nats_client.register
def cmdb_get_custom_script(params):
    # 入参 {"collect_task_id": 123}
    # 校验任务存在且 task_type == custom_script，经任务解析引用的插件
    # 返回 {"plugin_id","content","shell","os_type","version","checksum"}
    # 始终返回 DB 当前版——插件编辑下一轮 Run 自动生效
```

- 以 task_id 为入参（鉴权天然：任务存在性即边界），Server 侧解析插件；
- checksum 仅作为**版本标识与审计字段**（PR/导出比对），**不做内容校验**——
  checksum 与 content 在同一 RPC 响应内，互验只能防 TCP 层损坏而 NATS 已保证
  （原 headers 带 checksum 的互验设计随"headers 不带版本"决策一并失效，见 §12）；
- **拉取时机：Run 准备期一次拉取、注入参数（一个采集 Run 只查一次，不是一 IP
  一次；无缓存、无 singleflight）**：`UnifiedPluginFactory` 解析到 custom_script
  插件时，在 Run 准备阶段（目标调度开始前）发起一次 RPC，把返回的
  `script_content / shell / os_type / version` 直接注入 Run 参数；
  目标级 collector 从入参读取 `script_content`，**执行期零 RPC**。
  同 Run 所有目标天然执行同一版本（取自同一次注入），下一轮 Run 准备期拉新版；
- 拉取失败 → **整个 Run 以 `SCRIPT_FETCH_FAILED` 快速失败**（不进入目标调度，
  不逐目标重复失败）；
- 内存边界：脚本 ≤ 64KB，随每目标参数拷贝（`dict(params)`），120 并发目标
  上限约 8MB，可接受；
- responder 与日志均不记录 content；注入后的 Run/目标参数同样禁止整体落日志
  （现有 plugin_exception 调用链日志不含参数值，维持该约束）。

### 6.2 插件与执行路由

新增 `plugins/inputs/custom_script/{plugin.yml, collector.py}`：

```yaml
executors:
  job:
    type: job
    script_source: remote        # 新语义：脚本由 Run 准备期注入，无本地 scripts
    collector:
      module: plugins.inputs.custom_script.collector
      class: CustomScriptCollector
    target_policy:
      mode: remote_channel
default_executor: job
```

框架配套改动一处：`PluginExecutor._prepare_collector()`（executor.py 150-156 行）
对 `script_source: remote` 跳过 `script_path` 强制注入。

`CustomScriptCollector.list_all_resources()`（结构照抄 `PCInventoryCollector`）：

```
1. 校验参数（custom_plugin_id/os_type/node_id/script_content——
   脚本已由 Run 准备期注入入参，§6.1，collector 不发 RPC）
2. 渲染占位符：{{bk_host_innerip}} → 目标 IP；{{credential.<key>}} → 业务凭据值
3. 执行（脚本执行超时 = min(任务 timeout, 600)，决策 D11）：
   linux   → SSHPlugin(script_content=渲染后脚本, execute_timeout=上述值)
             （继承 local.execute/ssh.execute 分流、node_info 判断、私钥认证）
   windows → ansible_adhoc(ansible_node_id=node_id, connection=winrm,
             module=win_shell, module_args=渲染后脚本, winrm_* 透传,
             execute_timeout=上述值)
4. 输出边界：stdout ≤ 4MB；记录数 ≤ 5000；单字段 ≤ 1024 截断；
   超限降级为 partial 计数，不伪装完整（borrow PC 的 _truncate_field）
5. 解析 stdout（SSHPlugin._parse_collect_output 现成）；
   丢弃无 inst_name 记录并计数
6. 返回 {"success": True, "result": {plugin_id: records}}
   → convert_to_prometheus_format 自动产出 {plugin_id}_info gauge → NATS → VM
```

### 6.3 SSHPlugin 最小改动

两个最小改动，现有调用方（全部内置 job 插件、PC macOS 路径）行为不变，
需回归测试锁定：

- 增加 `script_content` 参数：有则跳过 `_read_script()` 文件读取；shell 类型
  从参数取（现靠文件扩展名推断，自定义脚本无文件名）；
- 增加可选 `execute_timeout` 参数（默认 60 保持现状）：现为硬编码 60s，
  自定义脚本按 D11 传入 `min(任务 timeout, 600)`；`nats_timeout` 按既有公式
  随之放大（execute_timeout × TASK_MAX_JOBS）。

### 6.4 探活与错误分类

- probe：linux 复用 `SSHPlugin.probe()`；windows 不实现（`NOT_SUPPORTED`，
  与 PC 采集器一致，框架跳过预检直接采集）；
- 稳定错误码：沿用 PC 集合 `TARGET_UNREACHABLE / WINRM_AUTH_FAILED /
  WINRM_TLS_FAILED / SSH_AUTH_FAILED / SSH_KEY_INVALID / SCRIPT_TIMEOUT /
  SCRIPT_OUTPUT_INVALID`，扩 `SCRIPT_FETCH_FAILED`（RPC 拉取失败/超时）；
- 仅认证类错误允许框架轮换下一凭据（凭据冷冻机制现成）；
- 错误文本进 `cmdb_collect_error` 前按 PC `_scrub_secrets` 模式脱敏——
  脱敏集合包含传输凭据与**全部 schema 加密字段的值**。

## 7. 阶段四：CMDB 查询数据入库

### 7.1 数据形态

脚本记录经 `convert_to_prometheus_format` 后每字段成为 VM label
（list/dict/空值被过滤），指标名 `{plugin_id}_info`；Server 按
`{plugin_id}_info_gauge{instance_id="cmdb_<task_id>"}` 查询，所有值为字符串。
指标按插件唯一，与内置指标、其他自定义插件指标互不可见。

### 7.2 任务分发

`CollectionPluginRegistry.get_plugin(task_type, model_id)` 精确匹配未命中时
回退 `"*"`；通用插件声明 `supported_model_id = "*"`。注册冲突检查照旧。

### 7.3 通用格式化插件（本阶段唯一新代码）

```python
# server/apps/cmdb/collection/plugins/community/custom_script/generic.py
class CustomScriptCollectionPlugin(AutoRegisterCollectionPluginMixin, CollectBase):
    supported_task_type = CollectPluginTypes.CUSTOM_SCRIPT
    supported_model_id = "*"

    @property
    def _metrics(self):
        # 经任务解析引用插件，返回 [f"{plugin.plugin_id}_info_gauge"]
        ...
```

动态白名单透传规则（替代按模型硬编码的 `model_field_mapping`）：

| 规则 | 行为 |
|---|---|
| 属性白名单 | 同步开始查一次目标模型属性定义（`ModelManage.search_model_attr` 现成），只保留模型存在的字段 |
| 系统 label 排除 | `__name__ / instance_id / model_id / collect_task_id / agent_id` 等不在模型属性中，白名单天然过滤 |
| 类型转换 | 按属性类型：int/float 数值转换；bool 按 "true"/"1" 判定；enum 校验在枚举值内；str 原样 |
| 转换失败 | 该字段置空并计入 warning 汇总，不丢整条记录 |
| inst_name | 缺失/为空丢整条并计数 |

产出 `{task.model_id: [records]}`——指标名与模型在此桥接，下游结构与内置插件同形。

### 7.4 对账入库：零改动（决策 D6）

`MetricsCannula._collect_models()` → 按 `collect_task == task_id` 查旧资产 →
`Management.controller()` 以 `inst_name` diff → add/update/delete 写图库。
`data_cleanup_strategy`、任务详情展示、变更记录全部现成。

同模型共存语义（内置 host + 自定义插件 host）：各任务资产按 `collect_task` 隔离；
后建任务输出撞既有 `inst_name` 时 add 撞唯一校验、该记录进 failed——与今天两个
IP 重叠的内置同模型任务行为逐行一致，不新增机制。

## 8. 安全与资源边界汇总

- 权限：插件库与任务均复用 team + MaintainerInfo，不新增权限面；
- 脚本 ≤ 64KB；stdout ≤ 4MB；记录 ≤ 5000；字段 ≤ 1024；脚本执行超时
  `min(任务 timeout, 600)`（D11，任务 timeout 仍作框架级单目标总预算）；
- 加密：传输凭据固定集 ∪ schema `encrypted` 字段，schema 驱动分支替代
  按 model_id 查树（修复明文落库坑，§3.3）；加密字段下发走 env 间接引用；
- 脚本正文（含渲染后）不进 headers、不进日志、不进变更记录快照、不进 RPC 日志；
- 错误文本脱敏覆盖传输凭据 + schema 加密字段值（§6.4）；
- `cmdb_get_custom_script` 为 NATS 内网平面 RPC，信任级别与
  `get_nodes_by_ips` 一致；
- 插件删除保护（被引用禁止删除）；采集为只读周期对账，幂等；
  删任务复用 `delete_params()` 清理节点配置。

## 9. 测试要求

| 层 | 用例 |
|---|---|
| 插件库 | CRUD 校验（plugin_id 格式/唯一/前缀、content 大小、shell 匹配、schema 形状与保留字）；锁定字段修改拒绝；插件删除保护（被任务引用）；模型删除保护（被插件绑定）；审计快照不含正文 |
| 组织隔离 | 双组织用例：A 组织插件对 B 组织用户列表/详情/树/模型 tab 均不可见；B 用户直接提交 A 插件 `custom_plugin_pk` 创建任务被拒；超管行为与采集任务列表语义一致 |
| 凭据 | 传输凭据池加密（`enc:` 前缀）；直填业务凭据显式加密（save() 不覆盖 params）；**vault 引用不存明文，下发时 resolve 成功进 env、凭据不可用则下发失败**；浏览器提交的 actor context 被服务端覆盖；占位符渲染与脱敏（含 schema 字段值哨兵不泄露） |
| Server 下发 | `CustomScriptNodeParams` 双 OS headers 契约（哨兵键注册、工厂候选键、`model_plugin_name`、**windows 含 node_id**）；内置任务工厂行为回归 |
| Server RPC | `cmdb_get_custom_script`：存在性/类型校验/始终返回最新版/日志不含 content |
| 生命周期 | §5.4 task_type 开关点逐项回归（beat 注册、节点下发、手动执行、首采调度、错峰跳过均走默认/正确分支） |
| Server 入库 | 通用格式化插件：动态 `_metrics` 取插件指标名、白名单过滤、类型转换、转换失败置空、inst_name 缺失丢弃、系统 label 排除；registry `"*"` 回退与精确优先 |
| Server 共存 | 同模型三路（内置 + 两个自定义插件）：指标互不可见；inst_name 冲突进 failed 且归属不变 |
| Stargazer | `test_async_plugin_contract` 合同；**Run 准备期注入：整 Run 仅一次 RPC、全目标入参同一版本脚本（Run 中途编辑插件不影响在途 Run）、拉取失败 Run 快速失败不进目标调度、跨 Run 拉新版**；linux/windows 路由（mock nats/ansible_adhoc）；**execute_timeout 透传（D11）与 SSHPlugin 默认 60s 回归**；输出边界截断降级；错误码分类；SSHPlugin `script_content` 分支 + 既有 script_path 路径回归 |
| E2E | 参照 `tests/e2e/test_hdfs_pipeline.py` fixture 流水线：脚本输出 → prometheus 格式 → format → 入库断言 |

验证命令（Cursor Cloud）：
`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest <paths> --no-cov`；
`cd agents/stargazer && uv run pytest -q -o addopts='' tests/test_async_plugin_contract.py <新增测试>`。

## 10. 分期

- **MVP**：§3–§7 全部 + §9 测试。
- **P1**：单目标"测试执行"预览（复用 `pc_connection_test` 真实链路最小执行模式，
  返回解析记录与被丢弃字段，辅助用户调脚本）；Windows probe（win_ping）；
  整插件导出/导入（JSON 包，跨环境迁移）。
- **不排期**：关联关系输出；增强更新模式（见 §12）；凭据声明逐项表单（维持 JSON）。
- **待数据库迁移后验证**：插件页与模型页的创建、编辑、保存；§9 中尚未覆盖的组织隔离、Windows 下发、输出截断、拉取失败终止采集、完整入库。迁移完成前不展开这两组验证。

## 11. 改动清单（文件级）

| 端 | 文件 | 改动 |
|---|---|---|
| Server | `models/custom_collect_plugin.py`（新）+ migration | `CustomCollectPlugin` 模型 |
| Server | `views/serializers`（插件库，新） | 插件 CRUD + 校验 + 删除保护 |
| Server | `constants/constants.py` | `CUSTOM_SCRIPT` 类型 |
| Server | `services/collect_object_tree.py` | "自定义"分组动态 children（§3.5） |
| Server | `node_configs/custom_script.py`（新） | `CustomScriptNodeParams`（哨兵键注册、schema 驱动 env_config） |
| Server | `node_configs/config_factory.py` + `node_configs/base.py` | 候选键按 task_type 构造 |
| Server | 凭据契约链路（`encrypt_collect_password.py` 等） | task_type 分支：传输固定集 ∪ schema encrypted keys |
| Server | `nats/nats.py` | `cmdb_get_custom_script` responder |
| Server | `collection/plugins/community/custom_script/generic.py`（新） | 通用格式化插件（动态指标名 + 白名单透传） |
| Server | `collection/plugins/registry.py` | `"*"` 通配回退 |
| Server | `serializers/collect_serializer.py` + `services/collect_service.py` | 任务引用插件校验 |
| Stargazer | `plugins/inputs/custom_script/plugin.yml`（新） | `script_source: remote` 插件声明 |
| Stargazer | `plugins/inputs/custom_script/collector.py`（新） | `CustomScriptCollector`（双路由 + 拉取 + 占位符渲染 + 边界） |
| Stargazer | `plugins/script_executor.py` | `SSHPlugin` 增加 `script_content` 与可选 `execute_timeout` 参数 |
| Stargazer | `core/plugin/executor.py` | `script_source: remote` 跳过 script_path 注入 |
| Stargazer | `core/collection/plugins.py`（`UnifiedPluginFactory`） | custom_script Run 准备期一次拉取脚本并注入 Run 参数；失败则 Run 快速失败 |
| Server | 模型删除校验（`model_ops` / 相应 service） | 存在绑定自定义插件时阻止删除 |
| Web | 自定义插件管理页（新） | 列表/编辑器/凭据声明 JSON/契约文档 |
| Web | 模型详情"自定义采集"tab（新，`assetManage/management/detail`） | 按 model_id 过滤视图 + 预填创建入口 |
| Web | 采集任务创建页 | 树动态节点 → 表单（业务凭据字段按 schema 渲染） |

## 12. 设计过程中的否决记录（防止回退重议）

1. **headers 透传脚本正文**：TOML 转义 + header 大小限制 + 明文落节点配置，否决（D2）；
2. **"查不到再回退"选 NodeParams**：自定义 host 任务会错误命中内置
   `HostNodeParams`，否决（D5）；
3. **工厂 hardcode 分支绕开注册表**：被哨兵键注册方案替代，保持单一注册机制（D5）；
4. **增强更新（enrich）入库模式 + `preserve_ownership`**：过度设计；同模型冲突为
   既有语义，下游零改动（D6）；
5. **脚本内嵌任务存储（无插件库）**：用户修订为独立插件库——复用、凭据 schema、
   指标命名都需要插件作为一等实体（D1）；
6. **指标按 `{model_id}_info_gauge` 派生**：用户修订为按 `{plugin_id}` 派生——
   多插件同模型时指标必须独立，且与内置"一插件一指标"惯例一致（D8）；
7. **插件页纯上传覆盖、不展示内容**：否决——排障必须能看到当前生效脚本；
   黑盒内容导致本地副本与线上版本漂移；微调成本过高。保留上传入口但仅填充
   编辑器、确认后保存（§3.4）；
8. **Stargazer 侧 checksum 内容校验 + `SCRIPT_CHECKSUM_MISMATCH`**：
   自审撤回——headers 不再携带版本/校验和后，checksum 与 content 同出一个
   RPC 响应，互验无增量价值；checksum 降级为版本标识与审计字段（§6.1）；
9. **业务凭据放入 credential 凭据池**：自审修正——池是多凭据轮换结构，
   业务凭据改存 `params.custom_credential_values` 并显式加密（D10）；
10. **执行期缓存方案（模块级 TTL 缓存 → Run 级查询器）**：两版均被用户修正
    否决——TTL 版在长 Run 中途过期会导致同 Run 版本漂移；Run 级查询器版仍是
    执行期拉取 + 缓存。最终方案：**Run 准备期一次拉取、注入 Run 参数，
    collector 从入参拿 `script_content`，执行期零 RPC 零缓存**（§6.1）。

## 13. 部署范围（2026-10-10 已确认）

本功能是**社区版功能**，社区部署包含 ansible-executor。Windows WinRM 路由与
Linux SSH 路由同放 `agents/stargazer/plugins/inputs/custom_script/`，不依赖
企业版 PC 插件包。
