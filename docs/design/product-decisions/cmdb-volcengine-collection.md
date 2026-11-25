# 火山引擎 CMDB 采集产品决策记忆

- 最近更新：2026-11-25
- 当前规格：`specs/changes/cmdb-volcengine-collection/spec.md`

## 产品定位

本期只做火山引擎云资源的 CMDB 配置采集。监控指标仍走已有 `volcenginecm`，不在本期范围。

## 已确认范围

- 采集插件只写 CMDB 资产、字段和关系。
- 与监控的衔接只用现有模块关联：只读外联 ID，不新建监控实例。

## 已确认设计决策

- 采集代码不得调用、导入监控代码，包括 `volcenginecm`。清单接口在 CMDB 采集插件内自行实现。
- 云资源不写 `node_id`。节点 ID 只属于主机与节点管理。
- 云资源不进入 `CMDB_MODEL_TO_MONITOR_OBJECT`，也不进入「建立监控关联」同步名单，与现有阿里云、腾讯云、华为云子对象一致。
- `monitor_id` 保持现有语义：只读，由后续关联动作在监控侧已有实例时回写。采集任务不写、不清这个字段。
- 负载均衡本期只采集传统型 CLB，模型 `volcengine_clb`。一套接口对应一个模型，不与 ALB、NLB 合并。
- 数据库本期同时采集云数据库 MySQL 与 PostgreSQL，模型分别为 `volcengine_mysql`、`volcengine_pgsql`。MySQL 走 `rds_mysql`，PostgreSQL 走 `rds_postgresql`，版本都是 `2022-01-01`，不合并成一个模型。
- 本期只建立火山引擎模型之间的关系：子资源 `belong` 账号；EIP 在绑定类型为 ECS 或 CLB 时，按资源 ID `connect` 到 `volcengine_ecs` 或 `volcengine_clb`。MySQL、PostgreSQL、TOS 只归属账号。采集只新增这些关系，不删除已有 `connect`。解绑或换绑后，旧 `connect` 保留，由用户在资产里手动取消。
- 内置模型放在火山引擎模型分组下。分组建好后，用户用现有能力在分组下新建模型，并用已有自定义采集脚本编写采集逻辑。本期不新增云上自定义采集配置。
- 厂商地域写入资源字段 `region`，保存 RegionId。不新增主机所用的 `cloud`。
- 一条采集任务只绑定一个地域。多地域通过多条任务完成。手动执行和周期执行沿用现有云任务。
- 失败处理与现有阿里云采集一致：成功的产品继续新增和更新；本轮任一资源查询或格式化失败时，快照不用于删除已有资产。权限拒绝不能当成该类资源为空。
- 模型分组 id 为 `volcengine`，名称「火山引擎」。账号模型与云平台采集插件 id 都是 `volcengine_account`，页面名称「火山引擎」。子模型为 `volcengine_ecs`、`volcengine_eip`、`volcengine_clb`、`volcengine_mysql`、`volcengine_pgsql`、`volcengine_tos`。
- TOS `ListBuckets` 返回账号下全部桶。一条任务只写入 `Location` 与任务地域一致的桶；接口失败按该产品失败处理，不把已有桶当成空清单。
- 子资源同时使用两个唯一身份：`inst_name` 写成 `名称(资源ID)`，`resource_id` 保存云上资源 ID，两个字段都唯一。采集按 `resource_id` 认出同一条实例；云上改名只更新该实例的 `inst_name` 和其余采集字段。名称为空时用资源 ID 作为名称。
- 账号模型 `volcengine_account` 由用户创建，身份是用户填写的 `inst_name`，不按 `resource_id` 对账。阿里云、腾讯云、华为云仍按各自现有的 `inst_name` 对账。
- 子资源字段使用现有云模型的同名属性，只收录火山引擎接口实际返回的值。状态和付费类型保存接口原值。采集刷新这些字段；用户另加的属性不写、不清。
- 每条子资源都有 `organization`、`resource_name`、`resource_id`、`inst_name`、`region`、`tag`、`auto_collect`、`collect_time`、`collect_task`。ECS 另有 `ip_addr`、`public_ip`、`zone`、`vpc`、`status`、`instance_type`、`os_name`、`vcpus`、`memory_mb`、`charge_type`、`create_time`、`expired_time`。EIP 另有 `ip_addr`、`status`、`bandwidth`、`instance_type`、`instance_id`。CLB 另有 `vpc`、`ip_addr`、`public_ip`、`status`、`type`、`charge_type`、`create_time`。MySQL 与 PostgreSQL 另有 `zone`、`vpc`、`ip_addr`、`port`、`version`、`status`、`storage_gb`、`storage_type`、`charge_type`、`create_time`。TOS 另有 `location`、`extranet_endpoint`、`intranet_endpoint`、`bucket_type`、`creation_date`。
- 账号模型字段与阿里云账号相同：`inst_name`、`organization`、`endpoint`、`tag`。`endpoint` 为空时，OpenAPI 使用火山引擎公网，对象存储使用 `tos-{region}.volces.com`。填写后，这两类请求都改用该主机。
- 应用拓扑层级沿用已有规则：`volcengine_ecs` 在主机层，`volcengine_mysql` 和 `volcengine_pgsql` 在应用服务层，账号、EIP、CLB、TOS 不分类。
- 任务入口、AK/SK、手动执行、周期执行、导出、变更记录和订阅沿用现有云采集。AK/SK 不进入日志、变更记录和采集快照。

## 明确后置

- 火山引擎监控指标、监控对象和实例同步。
- 在火山引擎资产上开放「建立监控关联」。
- 应用型 ALB、网络型 NLB。
- 与主机、网络设备及其他火山引擎以外模型的关系。
- 为火山引擎单独做自定义模型采集配置。
- 清理 EIP 解绑或换绑后留下的旧 `connect`。

## 仍待确认

无。

## 已替代决策

- 2026-11-24 之前把火山引擎模型加入监控实例同步名单的设想，改为本期不加入。
- 2026-11-25 建议账号模型用 `volcengine`，改为 `volcengine_account`。
- 2026-11-25 建议唯一键只选 `inst_name` 或只选 `resource_id`，改为两个都要：展示名用 `inst_name`，对账用 `resource_id`。
- 2026-11-25 建议完整采集时按当前绑定清理旧 `connect`，改为不清理。

## 决策来源

- 2026-11-24 对话：本期只做 CMDB 配置采集；采集插件与监控代码隔离；打通方式为现有模块关联 ID。
- 2026-11-25 对话：负载均衡先做传统型 CLB，模型 `volcengine_clb`。
- 2026-11-25 对话：云数据库 MySQL 与 PostgreSQL 本期都采集，分成两个模型。
- 2026-11-25 对话：主机和网络设备的关系本期不做，只做火山引擎模型之间的关联。
- 2026-11-25 对话：自定义模型扩展指分组下新建模型并复用已有自定义采集脚本，本期不新做。
- 2026-11-25 对话：厂商地域字段用 `region`。
- 2026-11-25 对话：一条采集任务只采集一个地域。
- 2026-11-25 对话：失败处理与现有阿里云采集一致，有错误的快照不删除已有资产。
- 2026-11-25 对话：账号模型用 `volcengine_account`。
- 2026-11-25 对话：`inst_name` 与 `resource_id` 都作为唯一身份，对账使用 `resource_id`。
- 2026-11-25 对话：子资源字段按现有云模型同名，只收录接口实际返回的值。
- 2026-11-25 对话：不清理 EIP 解绑或换绑后的旧 `connect`。
- 2026-11-25 对话：按已确认范围落成变更规格。
