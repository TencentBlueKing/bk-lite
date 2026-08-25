# 深信服平台模型与配置采集完善

Status: proposed

## 摘要

在现有 CMDB“深信服云平台”分类和 SCP 三模型基础上，统一整理为一个“深信服平台”模型分类，
分类下分别维护 SCP 与 HCI 两套独立模型、采集插件和平台实例。SCP 与 HCI 可以复用安全、分页和
错误分类等实现能力，但不得共用产品模型、认证流程或接口契约。

本变更包含三部分：

1. 修改 `server/apps/cmdb/support-files/model_config.xlsx` 中的模型、属性和关联定义；
2. 优化、修复 SCP/HCI Stargazer 企业版采集插件，并补齐 HCI 底层资产；
3. 修改采集任务的平台实例选择契约，阻止 SCP 任务选择 HCI 实例或 HCI 任务选择 SCP 实例。

本变更只覆盖底层基础设施数据，不采集租户、项目、配额、审批、计费和服务目录。

## 问题陈述

### 模型配置不完整

当前 `model_config.xlsx` 已存在：

- 分类 `sangforscp / 深信服云平台`；
- 模型 `sangforscp`、`sangforscp_host`、`sangforscp_vm`；
- 工作表 `attr-sangforhci`、`attr-sangforhci_vm`、`asso-sangforhci_vm`。

但是 `models` 表没有正式登记 `sangforhci` 和 `sangforhci_vm`，HCI 属性和关联工作表成为孤立
定义；SCP Host 也没有归属 SCP 平台的关联，现有拓扑只有 VM 到 Host，无法从 SCP 平台完整遍历。

### 产品模型边界不清晰

SCP 是云管理平台，HCI 是底层超融合平台。两者可能同时发现 Host、VM 等相同真实资源，但产品
身份、接口、稳定 ID 和权威字段不同。若把 HCI 结果写入 `sangforscp_*` 模型，会造成：

- HCI 设备被错误识别为 SCP；
- Janus 与 HCI VAPI/版本化接口混用；
- 同一 VM 被两套来源错误覆盖或错误合并；
- 采集失败无法区分产品不匹配与凭据错误；
- 资产关系和来源不可审计。

### 采集任务缺少服务端模型匹配约束

前端通常按采集对象的 `model_id` 查询平台实例，但服务端当前主要校验实例存在性和访问权限，
没有把“任务模型必须等于所选平台实例模型”固化为强制契约。绕过前端或编辑存量任务时，仍可能
把 HCI 实例提交给 SCP 任务，最终在错误产品端点上请求 `/janus/public-key` 并得到 401。

## 目标

1. 保留现有深信服分类和 SCP 模型的兼容身份，不迁移已有模型 ID。
2. 将分类显示名称统一为“深信服平台”，分类下分别放置 SCP 与 HCI 模型。
3. 补齐 SCP 平台到 Host、Host 到 VM 的底层拓扑。
4. 补齐 HCI 平台、Host、VM、Storage 及其关系。
5. HCI 插件保持原生异步，SCP 插件不得阻塞 Stargazer 事件循环。
6. 两个插件均使用 3000 秒任务超时，并提供有界响应、分页和对象处理。
7. SCP 任务只能选择 SCP 平台实例；HCI 任务只能选择 HCI 平台实例。
8. 用 Mock 全链路测试验证平台实例、任务下发、认证、采集、转换、落库和关系创建。

## 非目标

- 不采集 SCP 租户、组织、项目、用户、配额、审批、计量或账单；
- 不把 SCP/HCI 合并为一个采集插件或一张采集卡片；
- 不把 HCI 结果写入 `sangforscp_host` 或 `sangforscp_vm`；
- 不在首期自动合并 `sangforscp_vm` 与 `sangforhci_vm`；
- 不使用名称、IP 或 MAC 单独判定两条记录是同一资产；
- 不在真机接口未确认前增加 HCI 网络、物理磁盘、虚拟磁盘等模型；
- 不在真机没有独立稳定集群 ID 时制造 `sangforhci_cluster` 空壳模型。

## 领域模型

| 术语 | 含义 |
| --- | --- |
| 深信服平台分类 | CMDB 模型分类，只负责模型归组，不代表一条真实资产实例 |
| SCP 平台 | 一套可连接并认证的深信服 SCP 管理端实例 |
| HCI 平台 | 一套可连接并认证的深信服 HCI 管理端；首期同时代表其管理的单一 HCI 集群 |
| 产品资源投影 | SCP/HCI 从各自接口看到的 Host、VM、Storage 等资源记录 |
| 原生资源 ID | 产品接口返回的稳定 ID/UUID，仅在所属平台实例的作用域内唯一 |
| 平台实例 | 用户在 CMDB 根模型中创建、供采集任务选择的 SCP/HCI 管理端实例 |

核心不变量：

> 模型分类不参与实例拓扑；SCP/HCI 根模型代表真实管理端；每条子资源身份由“平台实例 + 原生资源
> ID”共同确定。

## 一、模型定义和修改

### 1. 模型分类

保留现有分类 ID：

```text
classification_id = sangforscp
```

只把显示名称从“深信服云平台”调整为“深信服平台”。分类 ID 已可能被模型、权限和现存环境引用，
本期不为了命名整洁将其迁移成 `sangfor`。

### 2. SCP 模型

保留模型 ID，只调整显示名称：

| 模型 ID | 目标显示名称 |
| --- | --- |
| `sangforscp` | 深信服 SCP 平台 |
| `sangforscp_host` | SCP 宿主机 |
| `sangforscp_vm` | SCP 虚拟机 |

目标关系：

```text
SCP 平台
└── SCP 宿主机
    └── SCP 虚拟机
```

模型关联：

```text
sangforscp_host_belong_sangforscp
sangforscp_vm_belong_sangforscp_host
```

SCP 的 AZ 首期继续作为 Host/VM 字段，不升级为独立模型。只有接口提供稳定 AZ 原生 ID 且业务需要
按 AZ 建拓扑时，再增加 `sangforscp_az`。

### 3. HCI 模型

在 `models` 表正式登记以下模型，全部归入 `sangforscp` 分类：

| 模型 ID | 显示名称 | 用途 |
| --- | --- | --- |
| `sangforhci` | 深信服 HCI 平台 | HCI 管理端/单集群根实例 |
| `sangforhci_host` | HCI 主机 | HCI 物理节点 |
| `sangforhci_vm` | HCI 虚拟机 | HCI 虚拟机 |
| `sangforhci_storage` | HCI 存储池 | HCI 集群存储资源 |

目标关系：

```text
HCI 平台
├── HCI 主机
│   └── HCI 虚拟机
└── HCI 存储池
```

模型关联：

```text
sangforhci_host_belong_sangforhci
sangforhci_vm_belong_sangforhci_host
sangforhci_storage_belong_sangforhci
```

现有 `sangforhci_vm_belong_sangforhci` 在迁移期保留兼容。Host 采集和关系稳定后，再单独评估是否
删除直接关系；本变更不让已有 HCI VM 突然失去平台关联。

### 4. 属性定义

HCI 根模型至少包含：

```text
inst_name, organization, endpoint, version, status, tag
```

`endpoint` 是平台实例成为可采集目标的必要字段。

HCI Host 至少包含：

```text
resource_name, resource_id, ip_addr, serial_number, status,
cpu_model, vcpus, memory_mb, storage_gb, hypervisor_type
```

HCI VM 在现有字段基础上补充：

```text
native_uuid, host_id, storage_id, power_status
```

HCI Storage 至少包含：

```text
resource_name, resource_id, storage_type, status,
total_gb, used_gb, available_gb
```

`host_id`、`storage_id` 等只用于采集转换期建立关联，不要求作为用户主要展示字段。

### 5. 身份规则

子资源不得只按 `resource_id` 跨平台唯一，逻辑身份必须为：

```text
(platform_instance_id, native_resource_id)
```

`inst_name` 是显示值，不承担稳定身份。不同 SCP/HCI 管理端允许返回相同 `resource_id`。

## 二、采集插件优化和修复

### 1. HCI 插件

HCI 保持原生异步接口，在现有 VM 采集基础上增加 Host 和 Storage：

```python
{
    "sangforhci_host": [...],
    "sangforhci_vm": [...],
    "sangforhci_storage": [...],
}
```

要求：

- 增加 Host、Storage 接口适配；
- VM 输出稳定 `host_id`，接口具备时输出 `storage_id`；
- HTTP 请求全部异步；
- RSA 构造/加密不得长时间阻塞事件循环；
- 列表有最大响应字节数、JSON 深度/节点数、页数和对象数限制；
- 空页、重复页、offset 不生效或已知 total 未完成时整轮失败；
- 不完整快照不得触发差集删除；
- 认证、TLS、超时、产品/API 不匹配和响应契约错误分别分类；
- 日志不得包含凭据、Token、请求正文或响应正文。

CMDB formatter 处理顺序为：

```text
HCI 平台 → HCI Host/HCI Storage → HCI VM
```

以保证关联目标先于来源实例建立。

### 2. SCP 插件

SCP 插件必须满足 Stargazer 统一异步契约，不允许同步 `requests` 直接运行在事件循环中。

要求：

- 普通 HTTPS 优先使用异步客户端；
- 只能通过同步库兼容的 TLS 1.0/1.1 请求，在插件内部显式 `asyncio.to_thread()` 隔离；
- 同步请求自身仍必须有连接和读取超时；
- Janus 公钥、认证、AZ、Host、Server 接口保持产品独立；
- 所有分页增加响应、页数和对象数上限；
- 401 不得退化成空结果，必须区分认证拒绝和产品/API 不匹配；
- TLS、网络超时、非法 JSON、供应商业务错误分别分类；
- Host 输出归属 SCP 平台的关系；
- VM 的 `host_id` 无法匹配时保留 VM，但不制造错误 Host 关系并记录安全诊断；
- 真实空平台与采集失败必须有不同结果语义。

### 3. 插件清单

SCP/HCI 均为企业版插件，分别保留独立插件清单和卡片：

```text
sangforscp → SangforSCPManager
sangforhci → SangforHCIManager
```

两者 `plugin.yml` 的任务超时固定为：

```yaml
timeout: 3000
```

异步执行契约必须由运行时契约测试验证，不能只依赖 `async def` 或清单声明。

### 4. 可复用与不可复用范围

可以复用：

- 出站地址安全策略；
- 有界响应和分页保护；
- 安全日志和错误分类；
- RSA 输入上限和线程隔离工具；
- Mock HTTP/分页测试设施。

不得复用：

- 产品认证流程；
- 产品接口路径；
- SCP/HCI 模型 ID；
- 产品专属字段映射；
- 产品能力探测结论。

## 三、采集任务选择的平台实例

### 1. 产品卡片

采集对象树继续展示两张独立卡片：

```text
深信服 SCP
深信服 HCI
```

不合并成一张“深信服”卡片后再选择产品类型。

### 2. 实例选择约束

SCP 任务：

```text
task.model_id = sangforscp
selected_instance.model_id = sangforscp
```

HCI 任务：

```text
task.model_id = sangforhci
selected_instance.model_id = sangforhci
```

任务只能选择根平台实例，不能选择 Host、VM 或 Storage 子资源。

### 3. Web 行为

- SCP 卡片以 `sangforscp` 查询实例；
- HCI 卡片以 `sangforhci` 查询实例；
- “新增实例”打开对应根模型的字段表单；
- 下拉项显示平台实例名和 endpoint；
- 切换 SCP/HCI 卡片时清空上一个产品的 `instUuid`；
- 编辑任务遇到历史实例模型不匹配时显示错误，不静默保留；
- 保存前再次校验所选实例模型。

### 4. Server 行为

服务端在验证实例存在性和权限后，必须继续验证实例模型与任务模型一致。绕过前端提交错误实例时
返回明确的参数错误，不把任务下发到 Stargazer。

这项校验是产品/API 错配的系统性防线，不能只依赖插件在 `/public-key` 返回 401 后被动判断。

### 5. 存量任务

上线前审计 SCP/HCI 存量任务：

- 所选实例必须有合法 `inst_uuid`；
- SCP/HCI 任务与实例模型必须匹配；
- 只有 IP 而无平台身份的历史记录不得自动猜测产品；
- 错误绑定任务标记为待修复，由用户重新选择平台实例；
- 不自动把错误任务 IP 复制成另一产品的平台实例。

## 全链路测试

SCP/HCI 分别覆盖：

```text
平台实例
→ 创建采集任务
→ 生成 Stargazer 配置
→ Mock 产品认证
→ Mock 分页资源接口
→ 插件结果
→ 指标转换
→ CMDB 实例
→ CMDB 关联
```

HCI 至少验证：

```text
HCI 平台 → Host → VM
HCI 平台 → Storage
```

SCP 至少验证：

```text
SCP 平台 → Host → VM
```

必须包含：

- 正常登录与完整快照；
- HTTP 401；
- TLS 失败和超时；
- HCI IP 误用于 SCP、SCP IP 误用于 HCI；
- 空平台；
- 多页、无 total、多页重复和分页无进展；
- 已知 total 但提前空页；
- 超大响应、过深 JSON、对象数超限；
- 单条关系目标缺失；
- SCP/HCI 实例跨模型提交被服务端拒绝；
- 凭据和响应正文不进入日志；
- 异步契约和事件循环不阻塞；
- `timeout: 3000` 被插件加载和执行链路采用。

## 迁移与兼容

1. 不修改现有 `sangforscp*` 模型 ID；
2. 分类 ID 保留 `sangforscp`，只改变显示名称；
3. 先增加模型和关联，再启用新的采集结果，避免结果先于模型配置到达；
4. HCI VM 迁移期同时保留到平台和 Host 的关系；
5. 新模型第一次完整成功快照前不得清理历史数据；
6. 任务实例模型校验上线前先完成存量审计，避免无提示阻断计划任务；
7. 模型 Excel、Server formatter、Stargazer 输出和插件文档必须在同一发布中保持一致。

## 验收标准

1. CMDB 显示“深信服平台”分类；
2. 分类下包含 SCP 平台、Host、VM 和 HCI 平台、Host、VM、Storage；
3. 每个正式模型都有对应 `attr-*` 工作表；
4. 每条目标关联都有对应 `asso-*` 定义，不存在孤立 HCI 工作表；
5. SCP 能形成平台→Host→VM 拓扑；
6. HCI 能形成平台→Host→VM 和平台→Storage 拓扑；
7. SCP/HCI 插件均满足异步执行契约；
8. 两个插件的 `timeout` 均为 3000；
9. SCP 任务只能选择 SCP 平台实例；
10. HCI 任务只能选择 HCI 平台实例；
11. 服务端拒绝跨模型实例绑定；
12. Mock 全链路验证采集、转换、落库和关联；
13. 401、TLS、超时和产品错配有明确且安全的分类；
14. 不输出、保存或记录任何凭据；
15. 现有 SCP 模型 ID、资产和任务可以兼容升级。

## 建议交付顺序

建议拆成三组独立、可验证的提交：

1. 模型定义、关联及采集任务实例契约；
2. SCP 异步化、安全与可靠性修复；
3. HCI Host/Storage 扩充及 SCP/HCI Mock 全链路测试。
