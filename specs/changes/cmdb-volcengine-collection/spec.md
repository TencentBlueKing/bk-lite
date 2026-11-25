# 火山引擎 CMDB 配置采集

Status: implemented

## Problem Statement

CMDB 已经能采集阿里云、腾讯云和华为云资产。火山引擎上的云服务器、公网 IP、传统型负载均衡、云数据库和对象存储仍要手工录入。录入后的资源 ID、名称、地域和账号归属对不齐，火山引擎模型之间也没有可用的归属和绑定关系。

## Solution

增加火山引擎模型分组和一条云采集。用户先创建火山引擎账号，再为每个地域单独建一条采集任务，填写 AK/SK 并选择这一个地域。任务发现该地域下的云服务器、公网 IP、传统型负载均衡、云数据库 MySQL、云数据库 PostgreSQL 和对象存储，写入与现有云模型同名的字段。子资源归属这个账号；公网 IP 绑定云服务器或传统型负载均衡时补上连接。云上改名后仍更新原来那条资产。某一类资源失败时，已经成功的类继续更新，这一轮不删除已有资产。

## User Stories

1. As a CMDB 管理员, I want 在火山引擎分组下看到账号、云服务器、公网 IP、传统型负载均衡、MySQL、PostgreSQL 和对象存储, so that 这些资产有统一的模型和字段，不用再手工建一套。
2. As a CMDB 管理员, I want 先创建火山引擎账号，再创建一条只采集一个地域的任务, so that 换地域时另建任务，手动执行和周期执行都沿用现有云任务。
3. As a CMDB 管理员, I want 任务用 AK/SK 发现该地域的六类资源并写入资源 ID、名称、地域和状态, so that 资产清单里的关键字段与云上一致，状态和付费类型保持接口原值。
4. As a CMDB 管理员, I want 云上改名后仍更新原来那条资产的实例名, so that 手工补充的属性、已有关系和变更历史留在同一条资产上。
5. As a CMDB 管理员, I want 子资源归属账号，公网 IP 在绑定云服务器或传统型负载均衡时连到对应资产, so that 火山引擎模型之间能看出归属和当前新增的绑定。
6. As a CMDB 管理员, I want 公网 IP 解绑或换绑后保留原来的连接, so that 采集只补充关系，取消旧连接由我在资产里手动完成。
7. As a CMDB 管理员, I want 某一类资源失败时仍更新其他成功的类，并且这一轮不删除已有资产, so that 权限不足、限流或单条资源错误不会被当成「该地域已经没有这些资产」。
8. As a CMDB 管理员, I want 失败落在这条任务上，并带上任务地域、产品，以及单条资源失败时的资源 ID, so that 我能直接判断要改授权、重试，还是查看这一条资源。
9. As a CMDB 管理员, I want 对象存储只进入任务所选地域的桶, so that 一条地域任务不会收下账号在其他地域的桶。
10. As a CMDB 管理员, I want 这些资产继续使用现有导出、变更记录和订阅, so that 不需要为火山引擎再做一套。
11. As a CMDB 管理员, I want 分组建好后用现有方式在分组下新建模型，并用已有自定义采集脚本采集, so that 本期未内置的云产品仍可以按现有能力扩展。

## Implementation Decisions

### 边界

- 本期只做 CMDB 配置采集。清单访问放在 CMDB 云采集插件和 Stargazer 的清单输入里，不导入、不调用监控代码，也不复用已有的火山引擎云监控采集器。
- 不新增对外 API。任务保存、地域刷新、手动执行和周期执行沿用现有云采集任务。
- 不把火山引擎模型加入监控实例同步，也不对它们开放「建立监控关联」。处理方式与现有阿里云、腾讯云、华为云子模型一致。
- 采集不写、不清 `node_id` 和 `monitor_id`。`monitor_id` 仍只由后续已有的关联动作在监控侧已有实例时回写。
- 云厂商地域写入资源字段 `region`，保存 RegionId，例如 `cn-beijing`。不写入主机使用的云区域。
- AK/SK 沿用现有云任务的加密凭据。日志、变更记录和采集快照不包含凭据、请求正文或响应正文。

### 模型与目录

- 模型分组 id 为 `volcengine`，名称「火山引擎」。
- 云平台目录中的采集插件 id 与账号模型 id 都是 `volcengine_account`，页面名称「火山引擎」。
- 子模型为 `volcengine_ecs`、`volcengine_eip`、`volcengine_clb`、`volcengine_mysql`、`volcengine_pgsql`、`volcengine_tos`。
- 账号由用户先创建。账号字段与阿里云账号相同：`inst_name`、`organization`、`endpoint`、`tag`。`endpoint` 为空时，OpenAPI 使用火山引擎公网，对象存储使用 `tos-{region}.volces.com`。填写后，这两类请求都改用该主机。账号身份是用户填写的 `inst_name`，不按 `resource_id` 对账。
- 应用拓扑层级沿用已有规则：`volcengine_ecs` 在主机层，`volcengine_mysql` 和 `volcengine_pgsql` 在应用服务层，账号、EIP、CLB、TOS 不分类。
- 一条任务固定采集上述六类子资源，不提供产品勾选。

### 任务与地域

- 一条采集任务绑定一个已存在的火山引擎账号、一套 AK/SK 和一个地域。另一个地域另建一条任务。
- 地域列表沿用现有云任务的地域刷新，来源是 ECS `DescribeRegions`。服务 `ecs`，版本 `2020-04-01`，分页使用 `MaxResults`（最大 20）和 `NextToken`。结果保存 RegionId，不套用腾讯云地域的改名规则。
- 下发仍沿用现有云任务「使用首条凭据上的地域」的契约，不改成一次下发多个地域。

### 清单接口

清单客户端只服务 CMDB 采集。分页必须走完；限流时按退避重试，重试耗尽记为该产品失败，不写成空清单。

- 云服务器：ECS `DescribeInstances`，服务 `ecs`，版本 `2020-04-01`，`MaxResults` 最大 100，配合 `NextToken`。
- 公网 IP：VPC `DescribeEipAddresses`，服务 `vpc`，版本 `2020-04-01`，`MaxResults` 最大 100，配合 `NextToken`。不使用已废弃的 `PageNumber`。
- 传统型负载均衡：CLB `DescribeLoadBalancers`，服务 `clb`，版本 `2020-04-01`，`PageNumber` 配合 `PageSize`。只调用传统型 CLB，不调用 ALB 或 NLB。
- 云数据库 MySQL：`DescribeDBInstances`，服务 `rds_mysql`，版本 `2022-01-01`，`PageNumber` 配合 `PageSize`。
- 云数据库 PostgreSQL：`DescribeDBInstances`，服务 `rds_postgresql`，版本 `2022-01-01`，`PageNumber` 配合 `PageSize`。按分页清单处理。响应若只有任务号、没有实例列表，记为该产品失败，不另做任务轮询，也不当成空清单。
- 对象存储：`ListBuckets` 使用 `GET /`，主机为 `tos-{region}.volces.com`。一次返回账号下全部桶。只保留 `Location` 与任务地域一致的桶。接口失败记为该任务的对象存储失败，不把已有桶当成空清单。

### 身份与字段

- 子资源同时使用两个唯一字段。`resource_id` 保存云上资源 ID。`inst_name` 写成 `名称(资源ID)`。名称为空时，用资源 ID 作为名称。
- CMDB 实例的不可变业务身份仍是 `inst_uuid`。采集认同一条子资源时使用 `resource_id`，从而在改名时更新原实例的 `inst_name` 和其他采集字段。
- 火山引擎子资源单独按 `resource_id` 对账。共享的新增、更新、心跳和清理继续负责写入。阿里云、腾讯云、华为云仍按各自现有的 `inst_name` 对账。
- 每条子资源都有 `organization`、`resource_name`、`resource_id`、`inst_name`、`region`、`tag`、`auto_collect`、`collect_time`、`collect_task`。
- ECS 另有 `ip_addr`、`public_ip`、`zone`、`vpc`、`status`、`instance_type`、`os_name`、`vcpus`、`memory_mb`、`charge_type`、`create_time`、`expired_time`。内存使用接口返回的 MiB。
- EIP 另有 `ip_addr`、`status`、`bandwidth`、`instance_type`、`instance_id`。
- CLB 另有 `vpc`、`ip_addr`、`public_ip`、`status`、`type`、`charge_type`、`create_time`。
- MySQL 与 PostgreSQL 另有 `zone`、`vpc`、`ip_addr`、`port`、`version`、`status`、`storage_gb`、`storage_type`、`charge_type`、`create_time`。存储容量使用接口返回的 GB，版本保存 `DBEngineVersion` 原值。
- TOS 另有 `location`、`extranet_endpoint`、`intranet_endpoint`、`bucket_type`、`creation_date`。桶名同时作为 `resource_id` 和 `resource_name`。
- 状态和付费类型保存接口原值。采集刷新上述采集字段。用户在模型上另加的属性不写、不清。
- 组织和清理策略沿用现有云采集：新资产带上任务组织；不清理、及时清理、过期删除的适用条件不变。

### 关系

- 子资源 `belong` 账号，关系为 n:1。
- EIP 的 `InstanceType` 为 `EcsInstance` 或 `ClbInstance` 时，按资源 ID 找到同一账号下的 `volcengine_ecs` 或 `volcengine_clb`，新增 `connect`。其他绑定类型只归属账号。
- 先落云服务器和传统型负载均衡，再按本轮的 `inst_name` 创建 EIP 连接。目标不存在时跳过这一条连接，EIP 本身仍然更新；找不到目标不算快照失败。
- 采集只新增 `belong` 和 `connect`，不删除已有 `connect`。解绑或换绑后，旧连接保留。

### 失败与删除

- 与现有阿里云采集一致：成功的产品继续新增和更新。本轮任一资源查询或格式化失败时，快照不完整，不用于删除已有资产。
- 权限拒绝、限流耗尽和分页中断都是失败，不能当成该类资源为空。
- 只有整轮快照完整时，才按任务现有清理策略删除本任务拥有、且本轮清单中不再出现的资产。
- 单条资源失败通过现有采集错误记录表达，带上任务地域、产品和资源 ID。错误记录不写成资产。产品级失败带上任务地域和产品，不带虚构的资源 ID。

## Testing Decisions

- 好的测试只断言用户可见的结果：模型是否齐全、字段和原值是否正确、同一 `resource_id` 改名后是否仍是同一个 `inst_uuid`、失败时是否不删除、关系是否只增不删、对象存储是否只留下任务地域的桶、输出中是否没有凭据。
- 最高测试缝是现有云采集流水线：用固定的清单结果驱动火山引擎格式化，再进入现有 CMDB 写入和清理。不连接真实火山引擎账号。
- 模型契约单独锁定分组、模型、两个唯一字段、应用拓扑层级和关系定义，写法对齐现有云模型的模型配置测试。
- 清单客户端用注入的 HTTP 响应锁定分页、权限拒绝、限流和对象存储地域过滤。签名细节不作为验收内容。
- 既有参照是阿里云采集的快照完整性测试、腾讯云采集流水线测试，以及现有云模型的模型配置测试。
- 测试不导入监控采集器，也不把火山引擎模型断言进监控实例同步名单。

## Out of Scope

- 火山引擎监控指标、监控对象、监控实例同步，以及在火山引擎资产上建立监控关联。
- 应用型 ALB、网络型 NLB，以及负载均衡的监听器和后端服务器。
- 与主机、网络设备及其他火山引擎以外模型的关系，包括按 IP 自动匹配。
- 为火山引擎单独做可配置的 API 或脚本映射。分组下的自定义模型和已有自定义采集脚本保持原样。
- 清理 EIP 解绑或换绑后留下的旧 `connect`。
- 修改阿里云、腾讯云、华为云的对账键、字段和关系写入方式。
- 新增对外 API 或新的采集任务类型。

## Completion evidence

- 2026-11-25：`agents/stargazer` 下 `PYTHONPATH=. uv run pytest tests/test_volcengine_client.py`，11 passed。覆盖分页、签名头不含密钥、权限拒绝、限流重试、任务号、分页中断、响应体上限，以及一类失败时其余产品仍返回。
- 2026-11-25：`server` 下 sqlite 内存库执行 `apps/cmdb/tests/test_volcengine_collection_chain.py`，4 passed。完整链路用假云 HTTP 和进程内 VM：创建任务、下发节点配置、采集、Prometheus、Influx、查询 VM、写入 CMDB。改名后 `inst_uuid` 不变，完整快照删除过期资产，ECS 权限失败不删除，EIP 连接只增，对象存储丢掉其他地域，Telegraf 正文和 Prometheus 文本不含密钥。
- 凭据表单没有在浏览器里点过。`web/scripts/cmdb-cloud-credential-contract-test.ts` 在 Node 22 下通过，锁定 `volcengine_account` 的 AK/SK 文案键。

## Further Notes

- 产品决定记在 `docs/design/product-decisions/cmdb-volcengine-collection.md`。
- 接口、版本和分页以 2026-11-25 读取的火山引擎官方文档为准。实现时若官方分页或字段名已变，先核对当前文档，再沿用本规格里的产品和模型边界。
- 一套清单接口对应一个模型。传统型 CLB、MySQL 和 PostgreSQL 不合并。
