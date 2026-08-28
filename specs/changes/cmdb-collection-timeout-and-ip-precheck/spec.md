# CMDB 配置采集超时体系简化与任务级 IP 预检

Status: done

## Problem Statement

配置采集链路目前存在三个互相纠缠的超时问题与一个效率问题：

1. **表单「超时时间」语义失真**：前端文案宣称"单个对象的采集超时时间，超过该时长
   将跳过该对象"，但该值实际未接管单对象预算（由 `plugin.yml` executor timeout 控制），
   反而被十几个插件误用为**连接超时**——表单默认 600s 会把 MySQL 等插件的建连超时
   抬到 600s，而框架 30s 就掐掉整个采集，该值完全失真。
2. **超时配置双轨**：`plugin.yml` 的 executor `timeout` 与表单 timeout 并存，用户可配的
   不生效，生效的用户不可配。
3. **企业版 4 个插件完全无超时**：openstack / fusioncompute / smartx / inspurincloudrail
   的同步 `requests` 调用未传 timeout（默认无限等待），且 asyncio 取消对阻塞中的同步
   调用无效，连接挂死会占住执行资源直到进程级处理。
4. **离线 IP 消耗凭据尝试与预算**：客户环境 254 个 SNMP 目标中约 124 个离线，每个
   离线 IP 都要走完凭据探测才出局（`credentials_exhausted`），拖长整体采集时间。

## Solution

超时体系从三层收敛为两层，并为采集任务建立"凭据前连接预检"的任务级开关链路：

1. **插件内部超时全部硬编码写死**（连接建立、脚本执行上限等），用户不可配；
2. **用户唯一可配的超时 = 单对象（单 IP）正式 Collector 采集预算**：表单 timeout
   下发后只在 `plugin.collect()` 外由框架 `asyncio.timeout` 强制，每个 IP 独立计时；
   调度排队、preflight、access probe、publish 使用各自预算，删除 `plugin.yml`
   executor `timeout` 参数，消灭双轨；
3. **任务级 IP 预检开关**（本期只建链路）：开启后每个目标在进入凭据尝试前先做
   无凭据连接性探测，探不通直接出局，不消耗凭据与预算。

## Implementation Decisions

### 一、插件连接/执行超时——硬编码写死

#### 社区版

| 插件 | 写死值 | 改动 |
|---|---|---|
| mysql（gbase8a 继承） | 连接 10s | 停止读任务 `timeout`，写死 |
| postgresql（greenplum/kingbase/opengauss/vastbase 继承） | 连接 10s | 同上 |
| mssql | 连接 5s | 同上 |
| oracle | 连接 20s | 同上 |
| influxdb | 请求 10s | 同上 |
| oceanstor | 请求 60s | 同上 |
| nacos | 请求 10s | 同上 |
| server_bmc | 请求 10s | 同上 |
| highgo | 连接 10s | 同上 |
| tdsql | 连接 10s | 同上 |
| aliyun | 连接 30s / 读 60s | 同上 |
| qcloud | 请求 60s | 同上 |
| network（snmp_facts） | 10s / 重试 1 次 | 已改（工作区待提交） |
| network_config_file | 建连 `conn_timeout` 30s；单命令 `timeout_ops` 60s | 写死 |
| SSH/job 类全体（host、config_file、physcial_server 及约 34 个中间件插件） | 脚本执行上限 `execute_timeout` 60s | 停止读任务参数写死；server 侧 `node_configs/ssh/base.py` 同步停止把表单 timeout 塞入凭据下发 |
| vmware_vc（10s/池 10s）、fusioninsight（60s） | — | 已写死，不动 |
| ip（IP 发现） | 探测超时=表单值（其"连接"即单 IP 探测，与单对象预算同义） | 不动 |
| physcial_server IPMI | pyghmi 库默认（无参数可设） | 不动 |

#### 企业版

| 插件 | 写死值 | 改动 |
|---|---|---|
| aws | 连接 10s / 读 60s | 停止读任务 `timeout`，写死 |
| nacos / oceanbase / server_bmc | 10s | 同上 |
| h3c_cas / sangforhci | 60s | 同上 |
| winsphere | 30s | 同上 |
| highgo | 10s（继承社区 postgresql） | 随社区版自动生效 |
| openstack / fusioncompute / smartx / inspurincloudrail | 连接 10s / 读 60s | **当前完全无超时，必须补**：`handle_request` 统一 `kwargs.setdefault("timeout", (10, 60))`；openstack 另有 2 处直连 `requests.post`（登录取 token）单独补 |
| pc（PC 盘点） | 脚本执行上限 120s | 写死为现值（盘点脚本较慢，保留） |
| 企业版 job/SSH 类（aix、hdfs、sybase 等约 24 个） | `execute_timeout` 60s | 随 script_executor 统一写死 |
| azure（30s）、nutanixhci（30s） | — | 已写死，不动 |
| sangforscp | 由 `plugin.yml` collector.options 静态配置 | 不动 |
| hwcloud / manageone | CMP 驱动内部 10s | 不动 |
| 存储/设备 stub 插件 | 无网络连接 | 不涉及 |

### 二、用户唯一可配：单对象（单 IP）正式 Collector 采集预算

- 表单「超时时间」= 一个 IP/实例进入正式 `plugin.collect()` 后的硬截止；IP 段拆开后
  **每个 IP 独立计时**，某个正式采集超时不影响其余。
- 生效机制：框架层（`ExecutionPlanResolver` / executor）使用任务下发的 `timeout`，
  在 `plugin.collect()` 外由 `asyncio.timeout` 强制。等待 Scheduler 槽位的时间不计入；
  preflight、access probe 和 publish 继续使用各自独立预算。
- **删除 `plugin.yml` executor `timeout` 参数**（各插件 yml 的 `executors.*.timeout`
  字段与解析一并移除）；回落链 = 任务下发 timeout → 环境默认 `COLLECTION_TIMEOUT`。
- 一般插件钳制边界：最小 1s，最大 86400s（1 天）；空/0 视为未设置走回落链。
  `target_policy.mode=snmp` 的正式采集最小值为 30s，以容纳内部固定
  `timeout=10s`、`retries=1` 的完整重试周期；存量 1～29s 值运行时钳到 30s。
- 配套修正：`NetworkNodeParams` 停止用凭据 timeout（默认 10s）覆盖表单值，凭据
  timeout 不再下发——否则表单接管预算后 SNMP 单 IP 预算会塌成 10 秒。
- job 类说明：该预算掐的是 stargazer 侧正式 Collector 调用；目标主机上脚本自身的运行上限由
  写死的 `execute_timeout=60s`（pc 为 120s）约束。
- `TASK_JOB_TIMEOUT`（默认 600s）保留为 server 内部状态兜底（把僵死 RUNNING 收敛为
  TIME_OUT），与用户超时体系无关，不暴露、不改动。
- 前端 tooltip 应明确为“单个对象正式采集超时时间”，避免再次被理解为调度至发布的
  完整流程预算。

### 三、任务级 IP 预检

- **语义**：任务级开关，默认关闭。开启后每个目标在进入凭据尝试前先过预检钩子，
  按插件协议做**无凭据**连接性探测，探不通的目标立即以 `unreachable` 出局
  （attempts=0，独立失败分桶），不消耗凭据尝试、不占用采集预算。
- **预检方式由插件类型自动决定，用户只有开/关**（六类方案，见下节锁定表）。
- **预检组件自身失效**（权限不足、探测库异常）时放行目标继续正常采集，仅记告警
  日志——预检是加速筛除，不得因预检组件故障阻断采集。
- **存储**：不新增模型字段，写入 `CollectModels.params` JSONField（`ip_precheck`）。
- **链路**：前端采集任务表单「高级」区 Switch（默认关；K8s 等逻辑目标 UI 可隐藏）
  → `formatTaskValues` → server `params` → `node_configs` 下发 `cmdbip_precheck` header
  → agent 侧 header 去前缀后落入 `params["ip_precheck"]`。
- 不保留全局开关；agent 只读取当前请求的 `params["ip_precheck"]`。未下发、空值或显式
  关闭均不执行可达性探测，避免部署级配置覆盖任务语义。
- **同步修订** `specs/changes/stargazer-stateless-async-collection/spec.md` 中
  「ICMP 不得作为硬过滤」「预检默认不拨测」等锁定条款为「默认不做；任务显式开启
  `ip_precheck` 时按协议探测作为准入」。

### 四、IP 预检分类方案（已锁定 2026-08-25）

六类方案：

| # | 方案 | 适用 | 判定 |
|---|---|---|---|
| 1 | TCP 端口 | 直连 DB、多数 protocol、BMC/Redfish 管理口等 | 拨业务端口；超时/拒绝 → unreachable |
| 2 | HTTPS/TLS | vCenter、OceanStor、Nacos、私有云 API 等 | 拨 TLS 端口；**证书校验失败仍算可达**，交给凭据/业务阶段 |
| 3 | SSH remote | 全部 job/SSH；`network_config_file` | 拨 SSH 端口（默认 22）；**仅目标 IP == 接入点管理 IP（executor_node_ip）时跳过**；其它已注册节点仍拨 22 |
| 4 | SNMP/UDP | network、network_topo、**security_device** | 无凭据层不发送裸 UDP；出站策略通过后交给带凭据的最小协议探测 |
| 5 | Cloud / 逻辑 | 公有云账号、K8s 等 | 不做 IP 拨测；UI 可隐藏或忽略开关 |
| 6 | 不适用 / none | IP 发现、无固定端口存根、缺 `target_policy.port` 的插件 | 开关开启也不拨测 |

争议点拍板（同日锁定）：

1. **双执行器**（mysql / postgresql / physcial_server 等）：按**本次下发**的
   `executor_type` 选方案（`job` → remote；`protocol` → tcp/https），不按 model 写死。
2. **network_config_file**：归 **remote（SSH）**，不走 snmp。
3. **HTTPS 证书错误**：**算可达**（不标 unreachable）。
4. **无固定端口 / 存根**：无可靠端口声明 → **none**；有 yml `target_policy.port` 才拨测。
5. **security_device**：与 network 一致，无凭据层只做出站安全检查，协议可达性由带凭据
   的 SNMP probe 判定。
6. **PC**：Windows 拨 **WinRM** 端口（5986/HTTPS 或 5985/HTTP，跟 `winrm_scheme`）；
   macOS 拨 SSH 22。IIS 等仍走 SSHPlugin 的 Job 拨 22，不误用 WinRM。
7. **Job 本地执行与预检跳过**：真正本地执行看节点管理 `get_nodes_by_ips` 命中；
   预检跳过**仅**认接入点本机 IP，与「凡注册节点都跳过」刻意不一致（已确认维持）。

## Testing Decisions

- 只断言外部行为，不断言内部方法调用。
- **超时**：
  - 执行计划契约：任务下发 timeout 生效为正式 Collector 预算；一般插件钳制
    1s/86400s，SNMP 钳制 30s/86400s；空/0 回落 `COLLECTION_TIMEOUT`；yml
    `timeout` 字段删除后解析不再读取。
  - 分阶段契约：Scheduler 排队不计入表单 timeout；preflight、access probe、正式
    collect、publish 分别计时；整轮墙钟上限由独立 Run deadline 管理。
  - 插件契约：连接超时不随任务 `timeout` 变化（抽样断言建连参数为写死值）。
  - server 下发契约：`NetworkNodeParams` 下发的 `cmdbtimeout` 为表单值而非凭据值；
    `ssh/base.py` 不再下发 `execute_timeout`。先例：`test_node_params_multicred`。
  - 企业版 4 插件：`handle_request` 默认超时存在、显式传参不被覆盖。
- **IP 预检**：
  - 开关关闭/未下发 → 行为与现状完全一致；
  - 开启 + TCP：端口拒绝/超时 → unreachable、attempts=0；
  - 开启 + SSH remote：仅接入点本机跳过；其它目标拨 22（或凭据端口）；
  - 开启 + SNMP-B：硬网络失败 unreachable；纯超时放行；
  - 开启 + HTTPS：证书错误仍可达；
  - 开启 + 无端口/none、cloud/逻辑 → 不拨测放行；
  - PC Windows 拨 WinRM 端口；macOS 拨 22；
  - 预检组件抛异常 → 放行 + 告警日志。
  - 先例：`tests/test_preflight.py`。
- 双租户要求不适用（不新增对外 API）。

## Out of Scope

- 监控插件（monitor_plugins）链路的超时语义。
- `TASK_JOB_TIMEOUT` 状态兜底机制本身。
- 执行节点视角的远端预检（下发探测指令到执行节点）——二期评估。
- ICMP 作为硬准入（明确不做）。
- 预检跳过扩展为「凡节点管理已注册 IP 都跳过」（已否定）。

## Further Notes

- 表单 timeout 语义变更属于**行为变更**：存量任务里填过极大/极小值的，本变更后会
  真正生效为单 IP 正式 Collector 预算；SNMP 小于 30s 的存量值会被兼容钳制，需写入
  发布说明。
- 分类方案锁定后，落地工作是：按 `executor_type` / `plugin.yml target_policy` /
  特例表（PC、security_device、network_config_file）对齐
  `request_builder` 与 `preflight`，并补契约测试；不改变「用户只有开/关」产品面。
- 新协议插件应在 `plugin.yml` 声明 `target_policy`（mode + port）；缺省则 none。

## Verification Evidence（2026-08-25）

- stargazer：`tests/test_execution_plan.py`、`tests/test_preflight.py`、
  `tests/test_async_plugin_contract.py`、`tests/test_plugin_execution_metadata.py`
  通过（含 `tests/test_round_complete.py` 等同批 74 passed）。
- server：`apps/cmdb/tests/test_node_params_multicred.py` 17 passed
  （含 `cmdbtimeout` / `ip_precheck` / `execute_timeout` 下发契约）。
- 基线说明：`agents/stargazer/tests/test_collect_multicred.py` 因
  `ModuleNotFoundError: core.task_queue` 失败，与本变更无关。
- 2026-08-25 补充：IP 预检六类方案与争议点已锁定（见「四、IP 预检分类方案」）；
  映射已落地：`yaml_target_policy` 支持 `snmp`/`udp`/`none`；network /
  network_topo / security_device / tape_library → snmp；network_config_file →
  remote_channel；physcial_server IPMI → udp/623；HTTPS 证书错误 → REACHABLE；
  PC Windows WinRM / macOS SSH；契约测试
  `test_preflight` + `test_yaml_target_policy` + `test_collection_request_builder`
  共 56 passed。
