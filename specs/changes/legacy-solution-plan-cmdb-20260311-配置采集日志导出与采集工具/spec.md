# 配置采集日志导出与采集工具

Status: cancelled

> Migrated from `spec/solution_plan/CMDB/20260311.配置采集日志导出与采集工具.md` as historical change evidence.

日期：2026-05-08（更新）

## 方案概览

本方案基于 Requirement，为 CMDB 在"SOID特征库"下新增独立的"采集工具"一级页面，一期支持 SNMP、IPMI 两类协议排障能力，覆盖失败任务快捷跳转、参数预填、异步诊断执行、raw log 展示与文本导出。

总体策略：

- 工具独立于采集任务域：采集工具不复用 `CollectModels` 任务创建/执行模型，不写入新的采集任务，仅在失败任务场景下复用"快捷跳转 + 部分预填"能力。
- 页面形态保持独立：采集工具作为新增一级页面提供，不与现有 SOID 页面合并为"SOID库 / 采集工具"页面组。
- 前后端分层清晰：CMDB 负责入口、参数校验、权限、任务提交、结果查询与展示；Stargazer 负责协议执行；两者通过 NATS request/reply 完成实际诊断链路。
- 保持一期轻量：结果区只展示 raw log，导出内容仅包含 raw log，不引入历史调试记录、文件格式扩展或独立任务中心页面。
- SNMP 一期支持三类诊断能力：一是"测试连通性"（固定 OID 轻量 `snmpget`）；二是"获取OID数据"（`snmpbulkwalk` 从用户指定 OID 开始遍历）；三是"获取原始数据"（`snmpbulkwalk` 从固定根 `1.3.6.1.2.1` 开始遍历）。三类操作共用同一套凭据表单，通过不同按钮触发。
- IPMI 一期支持两类诊断能力：一是"测试连通性"（轻量连接校验）；二是"获取原始数据"（拉取 inventory 并返回 raw log）。
- Timeout 不在页面暴露，后端按操作类型写死：`test_connection` 固定 10s，`get_oid` 固定 120s，`raw_collect` 固定 300s，`ipmi_collect` 固定 30s。
- 失败路径优先：优先解决"失败后快速拿到原始证据"的问题，先在失败摘要区域提供入口，并尽量自动带入失败任务中可解析出的字段，减少用户重复输入。

## 范围与约束

### In Scope

- SOID特征库下新增"采集工具"一级页面。
- 保留现有 SOID 页面形态，采集工具以独立一级页面接入，不做页面组整合。
- 一期支持 SNMP、IPMI 两类协议工具。
- 一期页面不显示 SMI-S、CLI 等未纳入范围的协议标签。
- 失败任务摘要区域新增"前往采集工具"入口。
- 失败任务跳入时尽量自动带入失败任务中可解析出的字段。
- SNMP 支持三类操作：测试连通性（固定 OID 轻量探测）、获取OID数据（用户输入 OID 的 bulkwalk）和获取原始数据（固定根 `1.3.6.1.2.1` 的 bulkwalk）。
- IPMI 支持基础连接参数、测试连通性与原始采集，支持可选 cipher suite。
- Timeout 不在页面暴露，由后端按操作类型写死。
- 诊断结果通过异步提交后轮询返回，页面展示 raw log，并支持导出 `.txt`。
- 错误提示至少包含失败阶段与错误摘要。
- 用户可选择接入点（Stargazer 节点）。

### Out of Scope

- 在一期页面中显示 SMI-S、CLI 预留标签或入口。
- 复用 `CollectModels` 新建临时任务执行诊断。
- CMDB 直连目标设备的兜底执行模式。
- 自动回填全部凭据与全部诊断参数。
- 非文本格式导出、历史调试记录沉淀、批量调试。
- 独立的后台任务结果中心。
- 页面暴露 Timeout 设置项。

## 已确认决策

- 采集工具是独立的协议排障页面，不是采集任务详情的扩展页。
- 采集工具是新增一级页面，不与现有 SOID 页面合并为页面组。
- 失败任务仅提供快捷入口与上下文预填，不决定工具页的执行模型。
- 一期范围固定为 SNMP、IPMI。
- 失败入口先放在任务失败摘要区域。
- 失败跳转后尽量自动带入失败任务中可解析出的字段，用户可修改。
- 页面当前输入即本次执行的唯一生效参数。
- SNMP 主链路固定为"CMDB 经 NATS 调用 Stargazer 执行诊断并回传结果"。
- Stargazer 路由一期优先复用现有逻辑：根据接入点关联的 `cloud_name` 拼接目标 `service_name={cloud_name}_stargazer`；handler 按协议固定为 `debug_snmp` / `debug_ipmi`。`access_point` 仅作为执行上下文输入，不单独承担实例名推导。
- 执行模式固定为异步提交 + 结果轮询，后续如需流式推送可升级为 SSE，Stargazer 侧无需改动。
- Timeout 不在页面暴露，由后端按操作类型写死：`test_connection` 10s、`get_oid` 120s、`raw_collect` 300s、`ipmi_collect` 30s；NATS request timeout 固定为对应值 +5s 缓冲。
- SNMP 支持三类操作，`action` 字段区分：`test_connection`（固定 OID 轻量探测）、`get_oid`（用户指定 OID 的 bulkwalk）和 `raw_collect`（固定根 `1.3.6.1.2.1` 的 bulkwalk）。
- SNMP 表单填写方式尽量与现有 SNMP 采集任务保持一致：版本选项使用 `v2/v2c/v3`，v3 使用 `level/username/integrity/authkey/privacy/privkey` 字段与联动规则。
- 结果区与导出边界固定为 raw log。
- 失败跳转预填一期采用专用 `prefill` 接口，按"能解析就带"的原则直接回填目标地址、端口、接入点、协议版本及可解密凭据字段；仅对缺失字段要求手动补全。
- IPMI 支持可选 cipher suite 输入项（选填）。
- IPMI `privilege` 作为表单输入项提供，默认值为 `administrator`，用户可按设备实际情况调整。
- CMDB 接口一期单独建 `CollectToolViewSet`，不挂在现有 `CollectModelViewSet` 下。

## 分阶段计划

### 阶段一：页面骨架与失败跳转链路

**里程碑目标**

- 完成"采集工具"页面入口、页面结构和失败摘要跳转。

**交付内容**

- 保持现有 SOID 页面不变，新增独立一级页面"采集工具"。
- 采集工具页内新增 SNMP、IPMI 两个协议工具页签，一期不显示 SMI-S、CLI 预留页签。
- 失败摘要区域新增"前往采集工具"入口。
- 失败跳转支持自动带入协议类型及失败任务中可解析出的字段。
- 自动带入缺失时统一提示"无法自动带入，请手动补全参数"。

**里程碑结果**

- 用户可从 SOID特征库进入采集工具。
- 用户可从失败摘要一跳进入对应协议页。

### 阶段二：协议诊断执行链路落地

**里程碑目标**

- 打通 CMDB → NATS → Stargazer → 设备 → CMDB 结果查询 的诊断链路。

**交付内容**

- CMDB 新增协议诊断接口，统一接收 SNMP/IPMI 请求，`action` 字段区分操作类型。
- CMDB 对接入点、端口、协议参数做校验与标准化。
- CMDB 优先复用现有按 `cloud_name` 路由到 Stargazer 的方式，根据接入点关联的云区域名称拼接目标 `service_name`，不引入额外映射表。
- Stargazer 新增 NATS handler，支持 SNMP（`debug_snmp`）、IPMI（`debug_ipmi`）诊断请求。
- SNMP `test_connection`：对固定 OID `1.3.6.1.2.1.1.1.0` 执行轻量 `snmpget`，timeout 写死 10s。
- SNMP `get_oid`：执行 `snmpbulkwalk <用户指定OID>`，timeout 写死 120s。
- SNMP `raw_collect`：执行 `snmpbulkwalk 1.3.6.1.2.1`，timeout 写死 300s。
- IPMI `test_connection`：建立会话后执行轻量查询验证连通性与凭据，timeout 写死 10s。
- IPMI：支持 target/port/username/password/privilege/cipher_suite（选填），timeout 写死 30s；privilege 默认 `administrator`，允许用户按设备实际情况调整。
- 统一返回结果结构：成功标记、失败阶段、错误摘要、raw log、耗时。
- 执行超时场景具备明确结果反馈。

**里程碑结果**

- 用户可在工具页提交一次诊断任务，并通过轮询拿到 raw log。
- 执行失败时可看到可读错误摘要。

### 阶段三：前端交互打磨与联调验收

**里程碑目标**

- 完成结果展示、导出、参数联动与端到端联调。

**交付内容**

- SNMP 表单填写方式复用现有 `snmpTask.tsx` 逻辑：Version(`v2/v2c/v3`)、`snmp_port`、Community，以及 v3 的 `level/username/integrity/authkey/privacy/privkey` 联动规则。
- SNMP 三个执行按钮："测试连通性"（test_connection）、"获取OID数据"（get_oid，点击弹窗输入 OID）和"获取原始数据"（raw_collect，直接发起固定根 `1.3.6.1.2.1` 的 walk）。
- IPMI 表单：Target IP、Port、接入点、Username、Password、Privilege（默认 `administrator`）、Cipher Suite（选填）。
- IPMI 两个执行按钮："测试连通性"（test_connection）和"执行采集"（ipmi_collect）。
- 页面不显示 Timeout 设置项。
- 接入点 Select 下拉，复用现有 `/cmdb/api/collect/nodes/` 接口。
- 结果区统一只展示 raw log。
- 导出功能生成仅包含 raw log 的 `.txt` 文件，文件名格式：`collection_log_{protocol}_{ip}_{timestamp}.txt`。
- 完成前后端、NATS、Stargazer 端到端联调。

**里程碑结果**

- 页面交互、链路执行、结果导出可在一条链路内闭环。

### 阶段四：发布准备与回归

**里程碑目标**

- 完成上线前验证、回滚预案与范围确认。

**交付内容**

- 覆盖页面入口、失败跳转、SNMP test_connection、SNMP raw_collect、SNMP get_oid、IPMI test_connection、IPMI 诊断、导出等回归用例。
- 确认发布顺序：Stargazer → CMDB 后端 → CMDB 前端。
- 输出回滚策略：关闭入口、停用 NATS handler、回退前端页面组。

**里程碑结果**

- 具备安全发布条件。

## 阶段验收清单

- SOID特征库下存在"采集工具"一级页面。
- 现有 SOID 页面保持不变，采集工具不与其合并为页面组。
- 页面一期仅暴露 SNMP、IPMI 两类协议工具。
- 页面一期不显示 SMI-S、CLI 标签或入口。
- 页面不显示 Timeout 输入项。
- 失败摘要区域存在"前往采集工具"入口。
- 跳转后自动进入对应协议页，并尽量带入失败任务中可解析出的字段。
- 用户修改输入后，以当前输入为准执行诊断。
- SNMP 可通过"测试连通性"按钮发起轻量探测，快速判断网络与凭据是否可用。
- SNMP 可通过"获取OID数据"按钮弹窗输入 OID 后发起 bulkwalk，返回对应范围的 raw log。
- SNMP 可通过"获取原始数据"按钮发起固定根 `1.3.6.1.2.1` 的 bulkwalk，返回 raw log。
- IPMI 可通过"测试连通性"按钮快速验证 BMC 可达性与凭据有效性。
- IPMI 基础诊断可返回 raw log，cipher suite 为选填项。
- IPMI 不要求用户填写 `privilege` 仍可完成诊断执行。
- 结果区仅展示 raw log，导出内容仅包含 raw log。
- 轮询与执行超时场景有明确超时反馈。

## 风险与应对

- 风险：将工具链路误建模为采集任务链路，导致页面与后端过度复用 `CollectModels`。
  应对：方案明确工具不写任务、不走 `exec_task`，仅复用失败跳转入口。

- 风险：接入点与云区域关联不清，导致请求无法按现有 Stargazer 实例命名方式路由到正确执行面。
  应对：一期优先复用现有按 `cloud_name` 路由到 Stargazer 的方式，由后端先解析接入点对应云区域，再组装目标实例名，避免新增一套 access_point 到实例名的映射规则。

- 风险：SNMP `raw_collect` 大范围 bulkwalk 设备响应慢，导致 300s 内仍无法完成。
  应对：300s timeout 到期直接返回超时结果，Stargazer 停止 walk。

- 风险：失败任务可回填字段来源不稳定，导致不同协议或不同失败场景下预填结果不一致。
  应对：一期采用专用 `prefill` 接口，直接从任务快照与可解密凭据中回填字段；无法解析时统一按缺失字段处理，不再设计复杂优先级策略。

- 风险：结果区同时展示摘要、结构化结果、raw log，交互复杂度升高。
  应对：一期只保留 raw log 与错误摘要，避免结果模型膨胀。

## 依赖与协同

- 产品：确认"采集工具"一级页面命名、失败摘要入口文案。
- 前端：完成独立一级页面接入、SNMP/IPMI 表单、三类 SNMP 操作按钮、结果展示与导出。
- 后端：完成统一协议诊断接口、参数校验、接入点解析、按 action 分发 timeout。
- Stargazer：完成 NATS handler 与 SNMP/IPMI 执行逻辑（bulkwalk + snmpget + IPMI）。
- 测试：覆盖异步提交、结果轮询、超时、失败跳转、导出、三类 SNMP 操作等核心场景。

## 需人工判断/确认

- 发布策略选择：是否需要先灰度给社区环境或指定组织，需人工确认。
- 接入点展示名称：是否继续沿用"接入点"，还是切换为"执行节点/调试节点"，需人工确认。

## 遗漏项检查

- 范围边界：已明确 In Scope 与 Out of Scope，一期不显示 SMI-S、CLI，不暴露 Timeout，未扩展到异步任务中心等非目标。
- 依赖方：已覆盖产品、前端、后端、Stargazer、测试。
- 验收口径：阶段验收项均可执行、可验证、可回归。
- 风险与回滚：已明确主要失败路径、bulkwalk 超时风险与回滚动作。

## 一期简化实现建议

- 采集工具页面保持独立入口，不改造成"SOID库 / 采集工具"页面组；SOID 页面保留现状。
- Stargazer 路由一期优先复用现有实现，不新增 access_point 到实例名的映射表；后端先解析接入点关联的 `cloud_name`，再按 `{cloud_name}_stargazer` 组装目标实例名，调用固定 handler `debug_snmp` / `debug_ipmi`。
- Timeout 不暴露给用户，后端按 `action` 写死：`raw_collect` → 300s，`get_oid` → 120s，IPMI → 30s；NATS request timeout = 对应值 + 5s。
- `test_connection` 作为轻量探测动作单独保留，SNMP 通过固定 OID `1.3.6.1.2.1.1.1.0` 校验连通性与凭据，IPMI 通过轻量会话查询校验连通性与凭据。
- Timeout 不暴露给用户，后端按 `action` 写死：`test_connection` → 10s，`raw_collect` → 300s，`get_oid` → 120s，`ipmi_collect` → 30s；NATS request timeout = 对应值 + 5s。
- 失败跳转预填一期不做复杂字段优先级设计，直接使用专用 `prefill` 接口返回"当前任务能解析出的全部表单字段"；前端按返回值原样回填，缺失项再手工补齐。
- SNMP 表单填写方式尽量复用现有采集任务实现：前端内部字段命名沿用 `version/snmp_port/level/username/integrity/authkey/privacy/privkey`，减少新旧表单心智差异与映射成本。
- SNMP `test_connection` 对固定 OID `1.3.6.1.2.1.1.1.0` 执行 snmpget；`get_oid` 对用户输入 OID 执行 bulkwalk，OID 格式前端做基础校验（纯数字+点号）；`raw_collect` 对固定根 `1.3.6.1.2.1` 执行 bulkwalk。
- IPMI `test_connection` 仅执行轻量连通性校验；`ipmi_collect` 返回 inventory raw log。
- IPMI cipher suite 为选填，不填时不传该参数，执行层使用 pyghmi 默认值。
- IPMI `privilege` 对用户可见，未填写时默认使用 `administrator`，传入其他合法值时按传入值执行。
- `raw_log` 一期保持完整返回，不做长度截断；前端结果区与文本导出均基于完整 raw log。
- CMDB 接口一期单独建 `CollectToolViewSet`，不挂在现有 `CollectModelViewSet` 下，避免与采集任务主链路语义混用。
- HTTP 执行采用异步提交 + 轮询结果；如后续需要流式推送，可将结果查询接口升级为 SSE，Stargazer 侧无需改动。
