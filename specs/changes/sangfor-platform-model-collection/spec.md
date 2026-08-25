# 深信服平台模型与配置采集完善

Status: **implemented（第一阶段）**（2026-08-25；HCI Host/Storage 仍等待真机接口契约）

## 摘要

在现有 CMDB `sangforscp / 深信服云平台` 分类与 SCP 三模型基础上，将展示语义整理为
“深信服平台”分类，分类下分别维护 SCP 与 HCI 两套独立根模型、子资源模型、平台实例、采集任务
和企业版 Stargazer 插件。

本次变更分两阶段：

1. 第一阶段修复当前已有接口和实现证据的链路：SCP 平台、Host、VM，以及 HCI 平台、VM；
2. 第二阶段只有在真实 HCI 设备上确认 Host、Storage 接口、稳定 ID 和关联字段后，才原子增加相应
   模型与采集能力。

本变更只覆盖底层基础设施配置数据，不采集租户、项目、配额、审批、计费和服务目录。

## 已确认的当前事实

### 模型配置处于半接通状态

`server/apps/cmdb/support-files/model_config.xlsx` 当前包含：

- 分类 `sangforscp / 深信服云平台`；
- 已登记模型 `sangforscp`、`sangforscp_host`、`sangforscp_vm`；
- 工作表 `attr-sangforhci`、`attr-sangforhci_vm`、`asso-sangforhci_vm`；
- SCP VM 到 Host 的关联。

但是 `models` 表没有登记 `sangforhci` 和 `sangforhci_vm`。模型迁移只遍历 `models` 表，再按
`attr-<model_id>` 和 `asso-<model_id>` 读取定义，因此现有 HCI 工作表是孤立配置，不会形成完整的
CMDB 模型。SCP Host 也没有归属 SCP 根平台的关联。

### SCP/HCI 已经是原生异步企业版插件

当前开发分支中的 `SangforSCPManager.list_all_resources()` 和
`SangforHCIManager.list_all_resources()` 都是原生异步入口，且使用异步 HTTP 客户端。SCP 已具备
完整快照失败语义、分页/对象/字节上限、重试和内部总预算；HCI 已具备 RSA 票据认证、VM 有界分页、
响应大小与 JSON 复杂度限制。

因此本变更不重新实施“SCP 同步改异步”或“HCI 改异步”，只补充回归验证和当前链路缺口。

### 当前 HCI 配置采集只证明 VM 接口

HCI 当前实现只调用 `/vapi/json/cluster/vms` 并输出 `sangforhci_vm`。没有足够的当前代码、测试或
真机证据证明 Host、Storage 的接口路径、版本兼容、稳定 ID 和关系字段，因此第一阶段不得先创建
无法采集的 HCI Host/Storage 空模型。

### 任务实例缺少服务端产品模型校验

Web 当前通常按采集对象的 `model_id` 查询平台实例；Server Serializer 会使用 `inst_uuid` 重新查询
可信实例并检查访问权限，但未继续验证所选实例的 `model_id` 是否与任务目标模型一致。绕过前端、
编辑态残留或异常请求仍可能把 HCI 实例交给 SCP 任务。

已知两台 `10.230.0.53`、`10.230.0.66` 是 HCI，而 SCP 管理地址是 `10.233.1.17`。此前 SCP
任务访问 HCI 地址的 `/janus/public-key` 返回 401，首要原因是任务实例选择错误，不是 SCP 凭据本身
已被证明无效。

### 超时已经收口到任务运行时

当前开发分支的超时链路是：

```text
CMDB CollectModels.timeout
→ NodeParams params.timeout
→ Stargazer ExecutionPlan.collection_timeout_seconds
→ TargetCollectionExecutor asyncio.timeout
```

异步插件契约测试要求 `plugin.yml` executor 不再声明 `timeout`。因此本方案废止“在 SCP/HCI
`plugin.yml` 写 `timeout: 3000`”的旧决定。

## 领域模型与不变量

| 术语 | 含义 |
| --- | --- |
| 深信服平台分类 | CMDB 模型分类，只负责模型归组，不代表真实资产实例 |
| SCP 平台 | 一套可连接、认证并采集的深信服 SCP 管理端实例 |
| HCI 平台 | 一套可连接、认证并采集的深信服 HCI 管理端实例；首期同时代表其管理范围 |
| 平台实例 | 用户在 SCP/HCI 根模型中创建、供采集任务选择的管理端实例 |
| 产品资源投影 | SCP/HCI 从各自接口看到的 Host、VM、Storage 等资源记录 |
| 原生资源 ID | 厂商接口返回的稳定 ID/UUID，只保证在所属平台实例作用域内唯一 |
| 完整快照 | 单个平台实例在一次成功采集运行中返回的全部目标资源；中途失败不构成完整快照 |

核心不变量：

1. 模型分类不参与实例拓扑；
2. SCP 与 HCI 根模型代表不同产品管理端，不共用产品模型、认证流程或接口契约；
3. 子资源身份由“来源平台实例 + 原生资源 ID”共同确定；
4. 任务只能选择与其目标模型相同的根平台实例；
5. 只有完整成功快照可以进入本轮 CMDB 对账；失败或不完整快照不得触发差集清理。

## 目标与非目标

### 第一阶段目标

1. 保留分类技术 ID `sangforscp`，只把展示名改为“深信服平台”；
2. 保留现有 `sangforscp*` 模型 ID，补齐 SCP 平台→Host→VM 拓扑；
3. 正式登记现有 HCI 平台和 HCI VM 模型；
4. 保留并回归验证 SCP/HCI 原生异步采集实现；
5. 在 Web 和 Server 同时阻止 SCP/HCI 跨模型实例绑定；
6. 将两个产品的 CMDB 任务默认总预算设为 3000 秒，超时归属任务运行时而非插件清单；
7. 用 Mock 覆盖模型定义、任务创建、配置下发、认证、采集、转换、写入和关联。

### 第一阶段非目标

- 不采集 SCP 租户、组织、项目、用户、配额、审批、计量或账单；
- 不把 SCP/HCI 合并为一个采集插件或一张采集卡片；
- 不把 HCI 结果写入 `sangforscp_host` 或 `sangforscp_vm`；
- 不自动合并 `sangforscp_vm` 与 `sangforhci_vm`；
- 不使用名称、IP 或 MAC 单独判定两条记录是同一资产；
- 不在真机接口未确认前增加 HCI Host、Storage、网络或磁盘模型；
- 不在缺少稳定集群 ID 时制造 `sangforhci_cluster` 空壳模型；
- 不在本变更中完成全局 `execution_mode` 清理；该事项属于 Stargazer 统一运行时收敛。

## 第一阶段设计

### 一、模型定义

#### 1. 分类

保留：

```text
classification_id = sangforscp
```

显示名称由“深信服云平台”改为“深信服平台”。技术 ID 已被模型、权限和存量环境引用，本期不迁移
为 `sangfor`。

#### 2. SCP 模型

| 模型 ID | 目标显示名称 |
| --- | --- |
| `sangforscp` | SCP云平台 |
| `sangforscp_host` | SCP平台主机 |
| `sangforscp_vm` | SCP平台虚拟机 |

目标拓扑：

```text
SCP云平台
└── SCP平台主机
    └── SCP平台虚拟机
```

关联：

```text
sangforscp_host_belong_sangforscp
sangforscp_vm_belong_sangforscp_host
```

SCP 的 AZ 首期继续作为 Host/VM 字段。只有接口能提供稳定 AZ ID 且业务需要按 AZ 建拓扑时，才
增加独立 AZ 模型。

#### 3. HCI 模型

第一阶段只正式登记当前采集器能产生的数据：

| 模型 ID | 目标显示名称 | 用途 |
| --- | --- | --- |
| `sangforhci` | HCI平台 | HCI 管理端根实例 |
| `sangforhci_vm` | HCI虚拟机 | HCI 虚拟机资源投影 |

两者 `classification_id` 均为 `sangforscp`。

目标拓扑：

```text
HCI平台
└── HCI虚拟机
```

保留现有关系：

```text
sangforhci_vm_belong_sangforhci
```

HCI 根模型至少补齐：

```text
inst_name, organization, endpoint, tag
```

`endpoint` 是平台实例成为可采集目标的必要字段。HCI VM 第一阶段保持当前已采集字段：

```text
resource_name, resource_id, ip_addr, status, os_name, vcpus, memory_mb
```

Excel 中仅存在 `attr-*`/`asso-*` 工作表但没有 `models` 登记的情况必须由模型契约测试阻止。

#### 4. 来源隔离身份

当前 SCP/HCI formatter 使用“资源名 + 原生 ID”生成唯一 `inst_name`。当接入多个平台实例且厂商
返回相同资源 ID 时，存在跨平台碰撞风险。

目标逻辑身份为：

```text
(source_platform_uuid, native_resource_id)
```

实施规则：

- HCI 尚未形成稳定存量，可从首次正式落库开始使用来源隔离身份；
- SCP 已可能存在历史实例，不得直接改变唯一 `inst_name` 后产生重复资产；
- SCP 先增加并回填来源平台身份，再以双读/受控切换方式迁移唯一身份；
- `resource_name` 继续作为用户展示名称，不承担稳定唯一身份；
- 图数据库内部 `_id` 不得进入跨模块或前后端身份契约。

SCP 身份迁移如果无法与第一阶段安全合并，应拆成独立、可回滚提交；不得因此阻塞模型关联与任务
模型校验先上线。

### 二、CMDB 采集任务与实例契约

#### 1. 采集对象目录

继续保留两张企业版卡片：

```text
深信服 SCP
深信服 HCI
```

两者仍属于当前采集对象树的云平台分组。HCI 采集对象定义的 `classification_id` 必须调整为
`sangforscp`，与模型 Excel 一致。即使当前树接口尚未输出该字段，源定义也不得制造第二套不存在的
分类身份。

采集对象定义应显式提供任务所选实例的目标模型（`target_model_id`）；没有特殊目标模型时默认等于
任务 `model_id`。Web 与 Server 共享这一契约，不能由 Web 单独推断。

#### 2. Web 行为

- SCP 卡片只查询 `sangforscp` 根实例；
- HCI 卡片只查询 `sangforhci` 根实例；
- “新增实例”使用 `instanceModelId` 读取属性并创建对应根模型实例；
- 切换模型卡片时清空旧 `instUuid`、旧选项和产品不兼容的凭据状态；
- 编辑任务遇到历史实例模型不匹配时显示错误，不静默保留；
- 下拉项显示平台实例名和 endpoint；
- Web 校验只负责及时反馈，不能代替 Server 强制校验。

#### 3. Server 行为

Serializer 继续只接受 `inst_uuid`，重新查询可信实例并校验权限，然后追加：

```text
trusted_instance.model_id == resolved_target_model_id
```

第一阶段至少对 `sangforscp`、`sangforhci` 强制生效。跨模型提交必须在保存任务阶段返回明确参数
错误，不能等任务下发后由厂商 `/public-key` 401 被动暴露。

服务端生成任务实例快照时只保留可信白名单字段，不信任客户端提交的 endpoint、模型 ID 或图内部
标识。

#### 4. 存量任务

上线前审计 SCP/HCI 存量任务：

- 所选实例必须有合法 `inst_uuid`；
- 任务模型与实例模型必须匹配；
- 只有 IP 而无平台身份的历史记录不得自动猜测产品；
- 错误绑定任务标记为待修复，由用户重新选择平台实例；
- 不自动把错误任务 IP 复制成另一产品的平台实例。

### 三、Stargazer 与企业版采集实现

#### 1. 已有异步实现

保留独立插件和认证契约：

```text
sangforscp → SangforSCPManager → Janus
sangforhci → SangforHCIManager → HCI VAPI
```

第一阶段不得重新引入同步 `requests` 到正式配置采集入口。异步契约、事件循环响应、出站地址策略、
响应/分页/对象上限和日志安全继续由现有通用与企业版测试锁定。

当前插件清单仍随全局 Stargazer 迁移保留 `execution_mode: async`。是否移除该字段应由统一运行时
变更一次完成，不在 Sangfor 变更中单独制造特例。

#### 2. HCI

HCI 第一阶段保持 VM 完整快照：

```python
{
    "sangforhci_vm": [...],
}
```

要求：

- `/vapi/json/public_key` 返回 401/403/404 时分类为产品/API 不匹配；
- 登录后 401/403 分类为认证失败；
- TLS、网络、超时、非法 JSON、响应契约错误分别分类；
- 空页、重复页、offset 不生效或已知 total 未完成时整轮失败；
- 响应字节数、JSON 深度/节点数、页数和对象数继续有界；
- 失败结果不发布部分 VM 快照；
- 日志不得包含密码、密文、票据、Token、请求头或响应正文。

#### 3. SCP

SCP 保持当前原生异步、完整快照实现并补充 CMDB Host→平台关联。要求：

- Janus 公钥、认证、AZ、Host、Server 接口保持产品独立；
- 401 不得退化为空结果；
- 公钥阶段的产品/API 错配和认证阶段的凭据拒绝使用不同稳定错误码；
- 所有分页继续受响应、页数、对象数和快照总字节限制；
- VM `host_id` 无法匹配时保留 VM，但不制造错误 Host 关系；
- 真实空平台与采集失败保持不同结果语义；
- 任一关键分页失败后丢弃已收集的部分数据。

#### 4. 超时契约

`plugin.yml` executor 不声明 `timeout`。两个产品的任务默认预算通过 CMDB 采集任务设置为：

```text
timeout = 3000 seconds
```

并由 Stargazer 外层 `asyncio.timeout()` 形成单目标正式采集总预算。

需要同时处理以下现状：

- Web 云采集全局默认值当前是 600 秒，且局部允许 `min=0`；Sangfor 应通过采集对象元数据或明确的
  产品默认值使用 3000，最小值统一为 1；
- `CollectModels.timeout` 当前为 `PositiveSmallIntegerField`，3000 可保存，但 Web/运行时允许到
  86400，与数据库整数范围不一致。本变更将字段迁移为 `PositiveIntegerField`，并在 Serializer 与
  Web 统一限制为 `1..86400`；
- HCI 的 60 秒是单次 HTTP 请求超时，不等于整轮任务预算；
- SCP `collector.options.total_timeout=300` 当前仍会先于 3000 秒外层预算终止，因此在不调整它时，
  SCP 的实际有效总预算仍是 300 秒。

锁定任务预算为单一正式总预算。SCP 用受信任任务参数计算内部截止时间：

```text
effective_total_timeout = min(task_timeout, trusted_max_total_timeout=3000) - exit_grace
```

`exit_grace` 只用于在外层取消前返回稳定错误，不能形成第二套业务超时。现有固定
`collector.options.total_timeout=300` 替换为可信最大值 3000；连接、读取、重试、分页、对象和字节
上限继续作为内部安全边界。任务设置小于 3000 时内外层都服从较小预算，任务设置大于 3000 时
Sangfor 插件仍以 3000 为安全上限。

调整 SCP 300 秒锁定前，必须同步修订
`specs/changes/stargazer-stateless-async-collection/sangforscp-async-remediation-2026-08-20.md`，并重新执行
单机大快照与并发压测。

### 四、CMDB 转换与完整快照对账

SCP formatter 处理顺序保持：

```text
SCP Host → SCP VM
```

Host 增加归属根平台关联；VM 继续通过当轮 `host_id → Host inst_name` 映射建立关系。

HCI formatter 第一阶段只处理 HCI VM，并关联所选 HCI 根平台。第二阶段增加 Host 后再调整拓扑，
不得在第一阶段预留无法满足的 Host 关联。

CMDB 必须复用现有 `cmdb_round_complete_gauge` 和 round gate：

- 任务仍在运行时不对账；
- 没有新完整轮次标记时不处理差异；
- 同一轮次不重复同步；
- 插件失败指标只进入原始诊断，不进入 CMDB 实例计算；
- 不为 Sangfor 另建一套快照删除机制。

## 第二阶段：HCI Host/Storage 扩展

第二阶段开始前必须在真实 HCI 设备上进行只读能力确认，且不得记录凭据或响应正文：

1. Host/节点列表接口、分页方式、稳定资源 ID；
2. 存储池/数据存储接口、容量单位和稳定资源 ID；
3. VM→Host、存储→平台或存储→节点的稳定关联字段；
4. 不同企业版 HCI 版本的路径、字段和认证兼容性；
5. 最大响应、最大对象量和所需任务预算。

只有接口契约被真实设备和 Mock 固定后，才能在同一纵向切片中同时增加：

```text
model_config.xlsx 模型/属性/关联
→ HCI collector 输出
→ Prometheus 转换
→ CMDB formatter
→ Mock 全链路测试
→ 插件说明文档
```

不得只增加模型或只增加接口调用。具体模型 ID 在接口确认后锁定，候选为
`sangforhci_host`、`sangforhci_storage_pool`；物理盘和虚拟磁盘只有在确有配置管理价值时再增加。

## 测试方案

### 模型契约

- `models` 中的每个 Sangfor 模型都有对应 `attr-*`；
- 每个 `asso-*` 的源/目标模型都已登记；
- 不允许存在孤立 HCI 工作表；
- SCP Host→平台、SCP VM→Host、HCI VM→平台关系存在；
- 采集 formatter 字段与 Excel 属性类型一致；
- HCI/SCP 采集对象的分类和目标模型与 Excel 一致。

### 任务实例契约

- SCP 任务绑定 SCP 根实例成功；
- HCI 任务绑定 HCI 根实例成功；
- SCP→HCI、HCI→SCP 跨模型提交均由 Server 拒绝；
- 客户端伪造 endpoint/model_id 不会覆盖服务端可信实例快照；
- Web 切换产品卡片会清理旧 `instUuid`；
- 编辑历史错配任务有明确错误提示。

### Stargazer 插件

- 注册入口是协程，事件循环不被阻塞；
- 正常认证和完整快照；
- 公钥端点 401/403/404 与登录后 401/403 的分类；
- TLS、网络、请求超时、非法 JSON 和供应商业务错误；
- 空平台、多页、无 total、重复页、分页无进展和提前空页；
- 响应、JSON、页数、对象数和快照总大小上限；
- 中间失败不发布部分快照；
- 日志不包含凭据和响应正文；
- CMDB 任务预算确实进入 `ExecutionPlan`，`plugin.yml` 不含 executor `timeout`。

### Mock 全链路

现有 HCI 测试已经覆盖任务镜像→NodeParams→企业版插件加载→Mock HTTP→Prometheus 转换→CMDB
formatter，但实施验收必须补齐尚未穿过的接缝：

```text
model_config 导入/契约
→ CollectModelSerializer 创建任务
→ 可信平台实例与凭据快照
→ NodeParams 下发
→ Stargazer PluginExecutor
→ Mock 厂商认证与分页接口
→ Prometheus 指标转换
→ CMDB formatter
→ MetricsCannula/实例写入
→ 关联写入
→ round gate 完整轮次确认
```

SCP 至少验证平台→Host→VM；HCI 第一阶段至少验证平台→VM。第二阶段增加 Host/Storage 后再扩展相应
拓扑断言。

Mock 只替换厂商 HTTP 边界；其余尽量使用生产公开接口。测试数据使用保留地址和虚构凭据，不得读取、
打印或固化真实设备凭据。

## 迁移、发布与回滚

1. 不修改现有 `sangforscp*` 模型 ID；
2. 分类 ID 保留 `sangforscp`，只改变显示名称；
3. 先部署模型定义和关联，再允许新 HCI 结果进入 CMDB；
4. 先上线 Server 跨模型校验前的存量审计，再启用强制拒绝；
5. 新模型第一次完整成功快照前不得清理历史数据；
6. SCP 来源身份迁移必须独立可回滚，不能静默重建全部已有实例；
7. Excel、Server formatter、Stargazer 输出、任务卡片和插件说明文档在同一发布中保持一致；
8. 回滚采集实现时不得删除已创建模型或资产；先停用新任务，再回退插件和 formatter；
9. 任何回滚都不能恢复跨模型实例绑定能力。

## 验收标准

1. CMDB 显示“深信服平台”分类，技术 ID 仍为 `sangforscp`；
2. 第一阶段分类下包含 SCP、SCP Host、SCP VM、HCI、HCI VM；
3. 不存在未被 `models` 登记的 Sangfor 属性/关联工作表；
4. SCP 形成平台→Host→VM，HCI 形成平台→VM；
5. SCP/HCI 继续满足原生异步和完整快照契约；
6. 两个产品的 CMDB 任务默认且最大有效预算为 3000 秒，`plugin.yml` 不声明 executor `timeout`；
7. SCP 内部截止时间由任务预算派生，原固定 300 秒不会提前截断合法采集；
8. SCP 任务只能选择 SCP 根实例，HCI 任务只能选择 HCI 根实例；
9. Server 拒绝所有 SCP/HCI 跨模型实例绑定；
10. Mock 全链路覆盖模型、任务、下发、采集、转换、写入、关联和完整轮次；
11. 401、TLS、超时和产品错配具有明确且安全的分类；
12. 不输出、保存或记录任何凭据；
13. 现有 SCP 模型 ID、资产和合法任务可以兼容升级；
14. HCI Host/Storage 不会在真机接口契约确认前提前进入第一阶段模型。

## 实施切片

建议按以下顺序提交，每个切片独立验证：

1. **模型与目录对齐**：分类展示名、HCI 模型登记、根属性、SCP Host 关联、模型契约测试；
2. **任务目标契约**：共享 `target_model_id`、Web 清理旧实例、Server 跨模型拒绝、存量审计；
3. **采集与转换补强**：SCP Host→平台关联、错误分类回归、round gate 回归；
4. **超时单一来源**：Sangfor 默认/可信上限 3000、字段迁移与范围对齐、SCP 派生预算及压测；
5. **第一阶段 Mock 全链路与文档**：覆盖真实模型/Serializer/写入接缝；
6. **第二阶段 HCI 扩展**：真机接口确认后原子增加 Host/Storage 模型与采集能力。

第一阶段完成并验收后才能标记本变更为 implemented；第二阶段可在本文件追加已确认的厂商接口契约，
或拆分为独立 change spec。
