# CMDB 采集任务多凭据

Status: cancelled

> Migrated from `spec/solution_plan/CMDB/20260602.CMDB采集任务多凭据.md` as historical change evidence.

日期：2026-06-02

## 方案概览

本方案基于 [spec/prd/CMDB/cmdb-prd.md](spec/prd/CMDB/cmdb-prd.md) 与 [spec/requirements/CMDB/20260602.CMDB采集任务多凭据.md](spec/requirements/CMDB/20260602.CMDB采集任务多凭据.md)，为 CMDB 采集任务提供任务内多凭据能力。

总体策略：

- 复用现有采集任务主模型：不新建任务主表，不改变插件契约，在现有 `credential` 字段上完成“单凭据 → 有序凭据池”的语义升级。
- 保持执行链路稳定：手动执行与周期执行入口保持不变，仅在平台侧派发阶段增加“对象识别、凭据选择、结果回写”逻辑。
- 命中关系独立存储：命中状态作为任务附属运行态独立存储，不进入 `collect_data`、`collect_digest`、`format_data`，不跨任务共享。
- 首期聚焦三类链路：JOB 采集链路、SNMP 协议采集链路、通用 PROTOCOL 协议采集链路；不扩展到 CLOUD、K8S、VM。
- 前端只做任务配置增强：采集任务创建/编辑页支持卡片式多凭据池配置，不新增命中状态详情页，不提供用户重置入口。

## 范围与约束

### In Scope

- 采集任务多凭据池配置，最多 3 个凭据。
- 任务内对象-凭据命中状态记录。
- 平台侧自适应凭据选择与复用。
- 连续失败门槛与渐进冷却恢复。
- 凭据新增、编辑、删除、重排后的命中状态处理。
- 老任务单凭据兼容运行。
- 首期覆盖：
  - JOB 采集链路：HOST、DB、MIDDLEWARE、CONFIG_FILE。
  - SNMP 协议采集链路。
  - PROTOCOL 协议采集链路。
- 前端任务创建/编辑页的多凭据配置交互。

### Out of Scope

- 凭据分组（凭据 + 目标范围）。
- 跨任务命中共享。
- 命中状态前端展示与任务级、对象级重置入口。
- 冷却策略配置化。
- 诊断工具与插件执行契约改造。
- CLOUD、K8S、VM 链路纳入首期范围。

## 已确认决策

- requirement 与原始需求冲突时，以原始需求为准。
- 凭据池数量限制为 1..3。
- 冷却策略采用 1h → 4h → 24h 递进，成功后归零。
- 命中状态不暴露前端。
- 多凭据能力只改变平台派发决策，不改变插件侧“单凭据 + 一批目标”的执行模式。
- 首期覆盖范围为 JOB + SNMP + PROTOCOL。
- 前端采用卡片式凭据池设计，按用户草图落地。

## 数据与架构落点

### 1）任务主模型语义升级

基于 [server/apps/cmdb/models/collect_model.py](server/apps/cmdb/models/collect_model.py)：

- 继续使用现有 `credential` JSONField。
- 将原本的单个凭据对象升级为有序凭据池数组。
- 老数据在读写路径统一兼容为长度为 1 的数组。
- 每个凭据补充内部稳定标识 `credential_id`，用于顺序调整与内容编辑区分。

建议结构：

```json
[
  {
    "credential_id": "cred_1",
    "username": "admin",
    "password": "enc:...",
    "port": 22
  },
  {
    "credential_id": "cred_2",
    "username": "ops",
    "password": "enc:...",
    "port": 22
  }
]
```

### 2）命中状态独立存储

新增任务附属状态表，建议字段至少包括：

- `task_id`
- `object_key`
- `credential_id`
- `status`：`untested` / `success` / `known_failed`
- `consecutive_failures`
- `cooldown_level`
- `next_retry_at`
- `last_success_at`
- `last_failure_at`
- `last_error`
- `object_snapshot`

唯一键建议为 `(task_id, object_key, credential_id)`。

### 3）对象唯一标识策略

对象必须以“任务内实际连接目标”为单位识别。

建议规则：

- HOST：`task_id + ip + cloud_region_id`
- DB / MIDDLEWARE / CONFIG_FILE：`task_id + ip + cloud_region_id + endpoint`
- SNMP：`task_id + ip + snmp_port + cloud_region_id`
- PROTOCOL：`task_id + host/ip + port/endpoint`

原则：有端口或 endpoint 时必须纳入，避免同 IP 多目标共享命中。

### 4）凭据变更失效规则

在 [server/apps/cmdb/services/collect_service.py](server/apps/cmdb/services/collect_service.py) 的 create/update 路径中处理：

- 新增凭据：分配新的 `credential_id`，命中状态初始为空。
- 删除凭据：删除对应 `credential_id` 的命中关系。
- 编辑凭据内容：清理该 `credential_id` 对应命中关系。
- 调整凭据顺序：仅更新顺序，不清理命中关系。

## 执行链路设计

### 1）统一入口保持不变

现有入口继续沿用：

- [server/apps/cmdb/views/collect.py](server/apps/cmdb/views/collect.py) 的 `exec_task()`
- [server/apps/cmdb/services/collect_service.py](server/apps/cmdb/services/collect_service.py) 的 `CollectModelService.exec_task()`
- [server/apps/cmdb/tasks/celery_tasks.py](server/apps/cmdb/tasks/celery_tasks.py) 的 `sync_collect_task()`

### 2）三条采集链路并行纳入

#### JOB 链路

入口：[server/apps/cmdb/collection/collect_tasks/job_collect.py](server/apps/cmdb/collection/collect_tasks/job_collect.py)

覆盖：

- HOST
- DB
- MIDDLEWARE
- CONFIG_FILE

#### SNMP 链路

锚点：

- [server/apps/cmdb/node_configs/network/network.py](server/apps/cmdb/node_configs/network/network.py)
- [server/apps/cmdb/collection/collect_plugin/network.py](server/apps/cmdb/collection/collect_plugin/network.py)

说明：SNMP 不走 JOB 分发器，属于协议采集侧的独立实现。

#### PROTOCOL 链路

入口：[server/apps/cmdb/collection/collect_tasks/protocol_collect.py](server/apps/cmdb/collection/collect_tasks/protocol_collect.py)

说明：PROTOCOL 通过 RegisteredCollect 分发体系执行，适用于直接连接目标的协议类采集。

### 3）平台侧多凭据调度服务

在进入具体采集器之前新增平台侧调度逻辑，职责包括：

- 解析任务凭据池。
- 生成对象唯一键。
- 查询命中状态表。
- 计算每个对象的候选凭据顺序。
- 按凭据聚合对象批次。
- 执行结果回写命中状态。

### 4）凭据选择规则

1. 已有成功命中的对象，优先复用成功凭据。
2. 未命中的对象，按凭据池顺序尝试 `untested` 凭据。
3. `known_failed` 且仍在冷却期内的凭据跳过。
4. 某对象在本轮一旦命中成功，立即停止后续凭据试探。
5. 非凭据问题导致的任务级失败，不污染对象级命中状态。

### 5）冷却与回写规则

- 首次失败：累计连续失败次数，不进入冷却。
- 第二次连续失败：进入 `known_failed`。
- 冷却时长按阶梯递增：1h → 4h → 24h。
- 再次成功后：`consecutive_failures` 与 `cooldown_level` 归零，状态切回 `success`。
- 同一对象只允许 1 个当前有效的成功凭据；新成功写入时需撤销旧成功状态。

## 前端方案

### 1）页面范围

只改采集任务创建/编辑页，不改任务详情页。

复用现有表单体系：

- [web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/baseTask.tsx](web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/baseTask.tsx)
- [web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/hostTask.tsx](web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/hostTask.tsx)
- [web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/sqlTask.tsx](web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/sqlTask.tsx)
- [web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/configFileTask.tsx](web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/configFileTask.tsx)
- [web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx](web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx)
- 协议采集对应页面

### 2）交互设计

按用户草图，采用“卡片列表 + 拖拽排序 + 折叠编辑”的单列布局。

每个凭据卡片包含：

- 左侧：拖拽手柄
- 中间：标题“凭据 1 / 凭据 2 / 凭据 3”
- 摘要区：用户名、密码占位、端口或 SNMP 版本等摘要信息
- 右侧：编辑、删除、展开/收起按钮

交互规则：

- 新增凭据默认展开。
- 已有凭据默认折叠。
- 编辑在卡片内展开完成，不使用弹窗。
- 底部提供“添加凭据”按钮。
- 达到 3 个后按钮禁用。
- 展示说明文案：“最多可配置 3 个凭据，按顺序依次试探”。

### 3）前端数据处理

- 在 [web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/hooks/formatTaskValues.ts](web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/hooks/formatTaskValues.ts) 增加凭据池格式化逻辑。
- 提交结构仍使用 `credential` 字段，避免后端接口字段名扩散。
- 在 [web/src/app/cmdb/types/autoDiscovery.ts](web/src/app/cmdb/types/autoDiscovery.ts) 与 [web/src/app/cmdb/api/collect.ts](web/src/app/cmdb/api/collect.ts) 中补充多凭据类型定义。
- 保留 `PASSWORD_PLACEHOLDER` 逻辑。
- SNMP 继续兼容 `community` / `authkey` / `privkey` 的占位回填。
- PROTOCOL 按现有插件字段结构做同构校验，不额外定义新的通用凭据模型。

## 分阶段计划

### 阶段一：后端兼容层与数据模型

**交付内容**

- `credential` 字段的数组化兼容读写。
- 命中状态独立模型与迁移。
- 凭据变更失效逻辑。
- 单凭据老任务兼容策略。

**里程碑结果**

- 老任务和新任务都能在不改执行入口的情况下使用统一的多凭据数据结构。

### 阶段二：派发与回写

**交付内容**

- 平台侧多凭据调度服务。
- JOB 链路接入。
- SNMP 链路接入。
- PROTOCOL 链路接入。
- 对象键生成、命中查询、冷却恢复与结果回写。

**里程碑结果**

- 三条链路均支持命中复用、顺序试探、冷却跳过和成功归零。

### 阶段三：前端任务配置

**交付内容**

- 卡片式凭据池 UI。
- 拖拽排序。
- 卡片内展开编辑。
- 编辑态回填与密码占位兼容。
- 最多 3 个凭据限制与字段同构校验提示。

**里程碑结果**

- 用户可以在现有任务配置页完成多凭据录入、修改和排序。

### 阶段四：联调、回归与发布

**交付内容**

- 前后端联调。
- 老任务兼容验证。
- 单凭据行为对比验证。
- JOB、SNMP、PROTOCOL 分链路回归。
- 发布与回滚预案确认。

**里程碑结果**

- 具备灰度上线条件，回滚时可退化为仅使用首个凭据。

## 验收清单

- 老任务无需人工迁移即可继续运行。
- 单凭据任务升级后无额外鉴权请求。
- 新任务可保存 1..3 个同构凭据。
- 冷启动对象按顺序试探，命中即停。
- 已命中对象二次执行直接复用成功凭据。
- `(对象, 凭据)` 连续两次失败后进入冷却。
- 冷却按 1h → 4h → 24h 递增，成功后归零。
- 编辑、删除、新增、重排凭据后的命中状态处理符合预期。
- 首期范围内的 HOST、DB、MIDDLEWARE、CONFIG_FILE、SNMP、PROTOCOL 均可使用该能力。
- 命中状态不会改变采集结果差集口径。

## 风险与应对

- 风险：对象键不稳定导致命中污染。
  应对：对象键生成逻辑集中收口，并保留 `object_snapshot` 便于排查。

- 风险：凭据重排或轻微编辑被误判为新凭据。
  应对：引入稳定的 `credential_id`，只在内容实变时清理命中。

- 风险：多凭据导致采集尝试次数明显增加。
  应对：优先复用成功命中，仅对未命中对象做最小试探，且单任务最多 3 个凭据。

- 风险：全局任务失败污染对象级状态。
  应对：明确区分凭据失败与任务级失败，仅前者写入命中表。

- 风险：回滚复杂。
  应对：回滚时保持任务结构不变，只退化为默认取凭据池首项执行。

## 待确认项（TODO）

- TODO: SNMP 对象唯一键是否固定采用 `task_id + ip + snmp_port + cloud_region_id + credential_id`。
- TODO: PROTOCOL 对象唯一键是否统一采用 `task_id + host/ip + port/endpoint + credential_id`。
- TODO: DB / MIDDLEWARE 是否统一把 endpoint 纳入对象唯一键。
- TODO: 是否需要管理员侧只读排查入口；若需要，应单独立项，不并入本次方案。
- TODO: 是否进行历史 `credential` dict → 数组的批量回填；建议不做强迁移，采用读写兼容。
