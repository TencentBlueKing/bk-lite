# 配置采集日志导出与采集工具 - Tech Plan

Status: cancelled

> Migrated from `spec/tech_plan/CMDB/20260311.配置采集日志导出与采集工具.md` as historical change evidence.

日期：2026-05-08（更新）

## 技术目标与非目标

### 技术目标

- 在不新增采集任务模型、不改造现有 `CollectModels → exec_task` 体系的前提下，为 CMDB 增加独立的协议诊断链路。
- 前端在 SOID特征库下新增独立一级页面"采集工具"，不与现有 SOID 页面合并，一期仅显示 SNMP、IPMI 两类协议。
- 失败摘要区域支持跳转到采集工具，并尽量带入失败任务中可解析出的字段。
- CMDB 提供统一协议调试 API，负责参数校验、权限、接入点解析、按 `action` 类型写死 timeout、NATS request/reply、结果标准化。
- Stargazer 新增同步调试 handler，负责 SNMP、IPMI 实际执行。
- SNMP 支持三类操作：`test_connection`（固定 OID 轻量 `snmpget`）、`get_oid`（用户指定 OID 的 `snmpbulkwalk`）和 `raw_collect`（固定根 `1.3.6.1.2.1` 的 `snmpbulkwalk`）。
- IPMI 支持两类操作：`test_connection`（轻量连通性校验）和 `ipmi_collect`（原始数据采集），cipher suite 为选填。
- Timeout 不在页面暴露，由后端按 `action` 类型写死，用户无需感知。
- 统一结果模型固定为：成功标记 + 失败阶段 + 错误摘要 + raw_log + 耗时。
- 前端仅展示 raw log，并支持导出 `.txt`。

### 非目标

- 不通过 `CollectModels` 持久化调试请求。
- 不复用 `sync_collect_task`、`ProtocolCollect`、`MetricsCannula` 作为诊断执行主链路。
- 不在一期页面中显示或开放 SMI-S、CLI 协议入口。
- 不提供 CMDB 直连目标设备兜底模式。
- 不新增调试历史表、审计明细表、后台任务中心。
- 不在页面暴露 Timeout 输入项。
- 不提供 IPMI `privilege` 的自动探测或兼容性兜底策略，默认值为 `administrator`，由用户按设备实际情况调整。

---

## 1) 文件与目录结构 (File Tree)

```text
web/
└─ src/app/cmdb/
   ├─ api/
   │  └─ collectTool.ts                                      (A) API 请求函数
   ├─ types/
   │  └─ collectTool.ts                                      (A) TypeScript 类型定义
   ├─ locales/
   │  ├─ zh.json                                             (M) 新增文案 key
   │  └─ en.json                                             (M) 新增文案 key
   └─ (pages)/assetManage/autoDiscovery/
      ├─ featureLibrary/
    │  ├─ page.tsx                                         (不变，保持现有 SOID 页面)
      │  ├─ soid/
      │  │  └─ page.tsx                                      (不变)
      │  └─ collectionTool/
    │     ├─ page.tsx                                      (A) 独立一级页面，页内 Tab 切换 SNMP/IPMI
      │     ├─ index.module.scss                             (A)
      │     ├─ components/
      │     │  ├─ SnmpTool.tsx                               (A) SNMP 表单 + 三个执行按钮
      │     │  ├─ IpmiTool.tsx                               (A) IPMI 表单 + 两个执行按钮
      │     │  ├─ ResultPanel.tsx                            (A) raw log 展示区 + 导出按钮
      │     │  └─ OidModal.tsx                               (A) 获取OID数据弹窗（输入 OID）
      │     └─ hooks/
      │        └─ useCollectTool.ts                          (A) 执行状态、计时、结果管理
      └─ collection/profess/
         └─ components/
            └─ taskDetail.tsx                                (M) 失败摘要区域新增"前往采集工具"入口

server/
└─ apps/cmdb/
   ├─ serializers/
   │  └─ collect_tool.py                                     (A) 请求/响应序列化
   ├─ services/
   │  └─ collect_tool_service.py                             (A) 业务逻辑
   ├─ views/
   │  └─ collect_tool.py                                     (A) CollectToolViewSet
   └─ urls.py                                                (M) 注册 collect_tool 路由

agents/stargazer/
├─ service/
│  ├─ nats_server.py                                         (M) 注册 debug_snmp / debug_ipmi handler
│  └─ debug/
│     ├─ protocol_debug_service.py                           (A) 统一入口，按 action 分发
│     ├─ snmp_debug.py                                       (A) SNMP 执行逻辑
│     └─ ipmi_debug.py                                       (A) IPMI 执行逻辑
└─ apps/rpc/
   └─ stargazer.py                                           (M) 新增 collection_tool_debug() 方法
```

说明：

- 前端页面路径为 `featureLibrary/collectionTool/`，与现有 `soid/` 同级；采集工具作为独立一级页面进入，不与 `featureLibrary/page.tsx` 合并为页面组。
- Stargazer 侧新增独立 `debug/` 目录，与现有 `tasks/handlers/` 完全隔离，不影响现有 Prometheus 采集链路。
- CMDB 后端新增独立 `CollectToolViewSet`，不挂在现有 `CollectModelViewSet` 下。

---

## 2) 核心数据结构 / Schema 定义

### 2.1 前端路由参数

跳转 URL 格式：

```
/cmdb/assetManage/autoDiscovery/featureLibrary/collectionTool?protocol=snmp&taskId=123
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `protocol` | `"snmp" \| "ipmi"` | 否 | 有值时自动切换到对应 Tab |
| `taskId` | `number` | 否 | 失败任务 ID，有值时自动调用 prefill 接口 |

### 2.2 执行请求结构（前端 → CMDB）

#### SNMP `test_connection`（固定 OID 轻量 snmpget）

```json
{
  "protocol": "snmp",
  "action": "test_connection",
  "access_point_id": "123",
  "target": "10.0.0.1",
  "port": 161,
  "credential": {
    "version": "v2c",
    "community": "public"
  }
}
```

#### SNMP `raw_collect`（固定根 `1.3.6.1.2.1` 的 bulkwalk）

```json
{
  "protocol": "snmp",
  "action": "raw_collect",
  "access_point_id": "123",
  "target": "10.0.0.1",
  "port": 161,
  "credential": {
    "version": "v2c",
    "community": "public"
  }
}
```

#### SNMP `get_oid`（指定 OID bulkwalk）

```json
{
  "protocol": "snmp",
  "action": "get_oid",
  "access_point_id": "123",
  "target": "10.0.0.1",
  "port": 161,
  "oid": "1.3.6.1.2.1.1.1.0",
  "credential": {
    "version": "v3",
    "level": "authPriv",
    "username": "admin_user",
    "integrity": "sha",
    "authkey": "authpass123",
    "privacy": "aes",
    "privkey": "privpass123"
  }
}
```

#### IPMI `test_connection`（轻量连通性校验）

```json
{
  "protocol": "ipmi",
  "action": "test_connection",
  "access_point_id": "123",
  "target": "10.0.0.2",
  "port": 623,
  "credential": {
    "username": "admin",
    "password": "secret",
    "privilege": "administrator",
    "cipher_suite": "3"
  }
}
```

#### IPMI `ipmi_collect`

```json
{
  "protocol": "ipmi",
  "action": "ipmi_collect",
  "access_point_id": "123",
  "target": "10.0.0.2",
  "port": 623,
  "credential": {
    "username": "admin",
    "password": "secret",
    "privilege": "administrator",
    "cipher_suite": "3"
  }
}
```

**字段规则：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `protocol` | string | 是 | `snmp` / `ipmi` |
| `action` | string | 是 | `test_connection` / `raw_collect` / `get_oid` / `ipmi_collect` |
| `access_point_id` | string | 是 | 接入点 ID，来自 `/cmdb/api/collect/nodes/` |
| `target` | string | 是 | 目标 IP |
| `port` | integer | 是 | 端口号 |
| `oid` | string | `protocol=snmp` 且 `action=get_oid` 时必填 | 表示用户指定的 OID，执行 `snmpbulkwalk` 的起始 OID；格式：纯数字+点号，例如 `1.3.6.1.2.1.1.1.0` |
| `credential` | object | 是 | 按协议版本校验，见下方凭据规则 |

**credential 字段规则（SNMP，保持与现有 SNMP 采集任务一致）：**

| `version` | 必填字段 |
|-----------|---------|
| `v2` / `v2c` | `community` |
| `v3` + `authNoPriv` | `username`, `integrity`(sha/md5), `authkey` |
| `v3` + `authPriv` | `username`, `integrity`, `authkey`, `privacy`(aes/des), `privkey` |

**credential 字段规则（IPMI）：**

| 字段 | 必填 |
|------|------|
| `username` | 是 |
| `password` | 是 |
| `privilege` | 否，前端默认 `administrator`，可选 `callback/user/operator/administrator` |
| `cipher_suite` | 否，不填时执行层使用 pyghmi 默认值 |

### 2.3 执行响应结构（CMDB → 前端）

```json
{
  "request_id": "dbg_7f6d8c2a",
  "protocol": "snmp",
  "action": "raw_collect",
  "executor": "stargazer",
  "success": false,
  "stage": "auth",
  "summary": "认证失败: snmp_usm_bad_password",
  "raw_log": "Error in packet.\nReason: authenticationFailure...",
  "duration_ms": 1243,
  "meta": {
    "target": "10.0.0.1",
    "port": 161
  }
}
```

**字段约束：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 每次请求唯一标识，格式 `dbg_{uuid[:8]}` |
| `success` | boolean | 执行是否成功 |
| `stage` | string | 失败阶段枚举，见下表 |
| `summary` | string | 用户可读摘要，直接在结果区顶部展示 |
| `raw_log` | string | 原始日志，唯一导出内容 |
| `duration_ms` | integer | 本次执行耗时（毫秒） |

**`stage` 枚举：**

| 值 | 含义 | 典型场景 |
|----|------|---------|
| `connect` | 网络连接失败 | 目标不可达、端口拒绝 |
| `auth` | 认证失败 | 密码错误、community 不匹配 |
| `collect` | 采集执行失败 | OID 不存在、协议参数错误 |
| `timeout` | 执行超时 | 设备响应慢 |
| `param` | 参数校验失败 | CMDB 侧校验不通过，未到达 Stargazer |
| `unknown` | 未知错误 | 其他异常 |

### 2.4 失败任务预填响应结构（CMDB → 前端）

```json
{
  "task_id": 123,
  "protocol": "snmp",
  "can_prefill": true,
  "prefill": {
    "access_point": { "id": "abc-001", "name": "北京节点" },
    "target": "10.0.0.1",
    "port": 161,
    "credential": {
      "version": "v3",
      "level": "authPriv",
      "username": "admin_user",
      "integrity": "sha",
      "authkey": "••••••",
      "privacy": "aes",
      "privkey": "••••••"
    }
  }
}
```

**字段规则：**

- `can_prefill=false` 时，`prefill` 字段为空，前端展示"无法自动带入，请手动补全参数"。
- `prefill` 内字段可部分缺失，前端对缺失字段留空等待用户填写；单个字段（如 `access_point`）无法解析时，不应将整体降级为 `can_prefill=false`。
- SNMP 预填字段命名尽量直接复用现有任务详情里的 credential 结构；前端内部可继续沿用现有 `snmpTask.tsx` 的 buildFormValues 映射方式。
- 密码类字段（`authkey`、`privkey`、`community`、IPMI `password`）一律返回 `"••••••"`，前端显示脱敏占位，**执行时若用户未修改（仍为 `"••••••"`），前端需传 `task_id`，由后端从原任务解密后注入**；若用户已修改，直接传用户输入的明文。
- IPMI `prefill` 可返回 `privilege`；若原任务未提供该字段，前端默认使用 `administrator`。

### 2.5 Stargazer NATS 消息结构

#### CMDB 发出的 request payload

```json
{
  "protocol": "snmp",
  "action": "raw_collect",
  "target": "10.0.0.1",
  "port": 161,
  "timeout": 60,
  "credential": {
    "version": "v2c",
    "community": "public"
  }
}
```

注意：`timeout` 由 CMDB 按 `action` 写死后注入，前端不传该字段；`access_point_id` 在 CMDB 侧完成 Stargazer 实例路由后不再透传给 Stargazer。

#### Stargazer 返回的 reply payload

```json
{
  "success": false,
  "stage": "auth",
  "summary": "认证失败: snmp_usm_bad_password",
  "raw_log": "...",
  "duration_ms": 1150
}
```

---

## 3) 关键执行链路与规则口径

### 3.1 页面跳转链路

```
失败任务摘要区（taskDetail.tsx）
  → 点击"前往采集工具"
  → router.push('/cmdb/assetManage/autoDiscovery/featureLibrary/collectionTool?protocol=snmp&taskId=123')

collectionTool/page.tsx 挂载
  → 读取 searchParams.protocol → 切换到对应 Tab
  → 若 searchParams.taskId 存在：
      → GET /cmdb/api/collect_tool/prefill/?task_id=123&protocol=snmp
      → 成功：按返回字段填充表单，密码字段显示 ••••••
      → 失败（can_prefill=false）：Toast 提示"无法自动带入，请手动补全参数"
  → 用户确认参数后点击执行按钮
```

### 3.2 完整执行链路

```
前端（collectionTool）
  → POST /cmdb/api/collect_tool/execute/
  │   body: { protocol, action, access_point_id, target, port, credential, oid?, task_id? }
  │
CMDB（CollectToolViewSet.execute）
  → CollectToolService.validate_and_normalize(payload)
    校验必填字段、credential 按协议/版本校验、oid 格式校验（仅 snmp/get_oid）
      若 credential 密码字段为 "••••••" 且 task_id 存在 → 从 CollectModels 解密并注入
  → CollectToolService.resolve_access_point(access_point_id)
      读取接入点关联的 cloud_name
      组装 service_name = f"{cloud_name}_stargazer"
  → 创建调试任务并返回 debug_id
  │
后台执行器/worker
  → CollectToolService.get_timeout(action)
    test_connection → 10s
      raw_collect   → 300s
      get_oid       → 120s
      ipmi_collect  → 30s
  → CollectToolService.execute_debug(normalized_payload, service_name, timeout)
      → Stargazer(instance_id=service_name).collection_tool_debug(payload, timeout)
          → nats_client.request(f"{service_name}.debug_snmp" 或 ".debug_ipmi",
                               data=payload, timeout=timeout+5)
  │
Stargazer（nats_server.py handler）
  → debug_snmp(data) 或 debug_ipmi(data)
  → ProtocolDebugService(data).execute()
      按 action 分发：
        test_connection → snmp_debug.run_snmp_test_connection(params) / ipmi_debug.run_ipmi_test_connection(params)
        raw_collect  → snmp_debug.run_bulk_walk(params, timeout=300)
        get_oid      → snmp_debug.run_get_oid(params, oid, timeout=120)
        ipmi_collect → ipmi_debug.run_ipmi_debug(params, timeout=30)
  → 返回 { success, stage, summary, raw_log, duration_ms }
  │
CMDB（回到 CollectToolService）
  → 持久化最终结果
  │
前端
  → 轮询 GET /cmdb/api/collect_tool/result/?debug_id=xxx
  → 获取最终结果后展示 raw log（resultPanel）
  → 若 success=false → 结果区顶部展示 summary（红色 banner）
  → "导出文本"按钮可用 → 下载 .txt
```

### 3.3 Timeout 规则

**后端按 `action` 写死，不接受前端传入，不在页面暴露：**

| `action` | 执行超时 | NATS request timeout |
|----------|---------|---------------------|
| `test_connection` | 10s | 15s |
| `raw_collect` | 300s | 305s |
| `get_oid` | 120s | 125s |
| `ipmi_collect` | 30s | 35s |

NATS request timeout = 执行超时 + 5s 缓冲，避免 Stargazer 执行刚好超时时 NATS 层也同时超时导致响应丢失。

超时时 Stargazer 返回 `stage=timeout`，CMDB 持久化结果并由轮询接口返回给前端。

### 3.4 SNMP 执行规则

#### `test_connection`（固定 OID 轻量 snmpget）

- 执行：对固定 OID `1.3.6.1.2.1.1.1.0` 执行一次 `snmpget`，快速验证目标可达性与凭据有效性。
- 实现：调用 pysnmp `getCmd()`，OID 固定为 `1.3.6.1.2.1.1.1.0`，前端不暴露 OID 输入。
- raw_log 格式：单行 `OID = TYPE: VALUE`。
- 成功语义：表示当前网络、端口与凭据可完成一次轻量 SNMP 取值，不等价于完整 bulkwalk 一定成功。

#### `raw_collect`（固定根 `1.3.6.1.2.1` 的 bulkwalk）

- 执行：`snmpbulkwalk` 从固定根 `1.3.6.1.2.1` 开始遍历。
- 实现：调用 pysnmp `nextCmd()` / `bulkCmd()`，起始 OID = `1.3.6.1.2.1`。
- raw_log 格式：每行 `OID = TYPE: VALUE`，例如：
  ```
  1.3.6.1.2.1.1.1.0 = STRING: Cisco IOS Software...
  1.3.6.1.2.1.1.2.0 = OID: 1.3.6.1.4.1.9.1.1
  ```
- raw_log 最大长度不做限制，内容完整返回。
- 已知限制：当前链路仍受 NATS 同步回包大小限制，`raw_collect` 或大子树 `get_oid` 在结果过大时可能失败，建议优先用于小范围排障。

#### `get_oid`（指定 OID bulkwalk）

- 执行：对用户指定的 OID 执行 `snmpbulkwalk`。
- 实现：调用 pysnmp `nextCmd()` / `bulkCmd()`，起始 OID = 用户输入的 OID。
- OID 格式校验：前端做基础校验（只允许数字和点号），后端再做一次兜底校验。
- raw_log 格式：每行 `OID = TYPE: VALUE`。
- OID 不存在时返回 `stage=collect`，summary 为"OID 不存在或无权限访问"。

#### 错误分类映射（Stargazer 侧实现）

| 异常类型 | `stage` | `summary` 示例 |
|---------|---------|--------------|
| `socket.timeout` / `TimeoutError` | `timeout` | "连接超时: 10.0.0.1:161 无响应" |
| `ConnectionRefusedError` | `connect` | "连接被拒绝: 10.0.0.1:161" |
| pysnmp `authenticationFailure` / USM error | `auth` | "认证失败: snmp_usm_bad_password" |
| `NoSuchObjectError` / `NoSuchInstanceError` | `collect` | "OID 不存在或无权限访问" |
| 参数校验失败（CMDB 侧） | `param` | "参数错误: port 超出范围" |
| 其他未捕获异常 | `unknown` | "未知错误: {exception type}" |

### 3.5 IPMI 执行规则

- 参数范围：`target`、`port`、`username`、`password`、`privilege`、`cipher_suite`（选填）。
- `privilege` 接受前端传入；未传时执行层默认使用 `administrator`。
- `cipher_suite` 不填时不传给 pyghmi，使用 pyghmi 默认值。
- `test_connection`：建立 IPMI 会话后执行轻量查询（如 `get_power()`），快速验证 BMC 可达性与凭据有效性，raw_log 返回简要文本结果。
- 实现：复用现有 `PhyscialServerIPMIInfo`，新增 `raw_inventory()` 方法，将 `get_inventory()` 返回的 dict 格式化为可读文本作为 raw_log。
- raw_log 格式示例：
  ```
  System Information:
    Serial Number: ABC123
    Model: PowerEdge R740
    Brand: Dell
  Board Information:
    Manufacturer: Dell Inc.
    Product Name: PowerEdge R740
  ```

### 3.6 凭据安全规则

- 预填接口（`prefill`）返回的密码字段一律脱敏为 `"••••••"`，不返回明文。
- 执行请求（`execute`）中的密码字段处理逻辑：
  ```
  if 密码字段 == "••••••" and task_id 存在:
      从 CollectModels(id=task_id).decrypt_credentials 中取对应字段明文
  else:
      使用请求中的值（用户手动输入或修改的明文）
  ```
- 明文凭据不落库、不写日志，仅在内存中存在于 NATS 请求生命周期内。
- 执行接口走 HTTPS，凭据明文在传输层加密保护。

### 3.7 接入点解析规则

#### 前端：获取节点列表

- 复用现有接口 `GET /cmdb/api/collect/nodes/`（`CollectModelViewSet.nodes` action）。
- 该接口透传 `NodeMgmt().node_list()` 的 NATS 响应，不在 CMDB 层定义字段结构。
- 前端 Select 需要展示节点名称、传递节点 ID，字段名以 `node_mgmt` 实际返回为准（参考现有 `profess/page.tsx` 中接入点 Select 的实现，复用相同取值逻辑）。

#### 后端：`access_point_id` → Stargazer 路由

完整路由链路，参考现有 `CollectModelService.list_regions()` 的实现（`services/collect_service.py:491`）：

```
前端传入 access_point_id（节点 ID）
  → CMDB 调用 NodeMgmt().cloud_region_list()
      取 cloud_region_id → cloud_name 的映射表
  → 用 access_point_id 对应的节点查询其所属 cloud_region
      取 cloud_name（即 CloudRegion.name）
  → service_name = f"{cloud_name}_stargazer"
  → Stargazer(instance_id=service_name)
  → NATS subject: {service_name}.debug_snmp 或 {service_name}.debug_ipmi
```

代码参考（`services/collect_service.py:491-504`，可直接复用）：

```python
# 现有实现（list_regions）
instance_id = f"{cloud_name}_stargazer"
stargazer = Stargazer(instance_id=instance_id)
```

`resolve_access_point()` 实现时直接复用此模式，无需新增映射表。

当 `cloud_name` 为空（例如直连节点无云区域）时，`instance_id` 回退为 `"stargazer"`（`Stargazer.__init__` 默认值）。

---

## 4) 核心接口与函数签名

### 4.1 CMDB REST API

```
POST /cmdb/api/collect_tool/execute/
  请求体：见 §2.2
  响应体：见 §2.3
  HTTP 超时：前端采用异步提交 + 轮询结果，不再受单次长请求超时限制
  权限：登录用户即可；若请求体携带 `task_id` 触发原任务凭据回填，则需与原任务同组织并具备该任务访问权限

GET /cmdb/api/collect_tool/prefill/?task_id=123&protocol=snmp
  响应体：见 §2.4
  权限：登录用户即可，需与原任务同组织
```

### 4.2 CMDB 后端实现

```python
# server/apps/cmdb/views/collect_tool.py

class CollectToolViewSet(AuthViewSet):

    @action(methods=["POST"], detail=False, url_path="execute")
    def execute(self, request):
        """
        执行一次同步协议诊断。
        1. 校验并标准化请求参数
        2. 解析接入点，确定目标 Stargazer service_name
        3. 按 action 写死 timeout
      4. 若密码字段为 '••••••' 且 task_id 存在，先校验当前用户对原任务有访问权限，再从原任务解密注入
        5. 通过 NATS request/reply 调用 Stargazer
        6. 标准化响应并返回
        """

    @action(methods=["GET"], detail=False, url_path="prefill")
    def prefill(self, request):
        """
        根据失败任务 ID 返回预填上下文。
        1. 读取 CollectModels(id=task_id)
        2. 提取可解析字段：target, port, access_point, credential
        3. 密码字段脱敏为 '••••••'
      4. 仅当任务不存在、协议不匹配或没有任何可用预填字段时返回 can_prefill=false
        """
```

```python
# server/apps/cmdb/services/collect_tool_service.py

TIMEOUT_MAP = {
  "test_connection": 10,
    "raw_collect": 60,
    "get_oid": 15,
    "ipmi_collect": 30,
}

def validate_and_normalize(payload: dict) -> dict:
    """
    校验规则：
    - protocol 必须为 snmp / ipmi
    - action 必须为 test_connection / raw_collect / get_oid / ipmi_collect，且与 protocol 匹配
    - target 必须为有效 IP
    - port 必须为 1-65535 整数
    - protocol=snmp 且 action=get_oid 时 oid 必填，格式为纯数字+点号
    - credential 按 protocol + version/level 做字段完整性校验
    """

def resolve_access_point(access_point_id: str) -> str:
    """
    查询接入点记录，取 cloud_name，返回 service_name = f"{cloud_name}_stargazer"。
    接入点不存在时抛出 ValidationError。
    """

def get_timeout(action: str) -> int:
    """按 TIMEOUT_MAP 返回写死的 timeout 秒数。"""

def inject_credentials(payload: dict, task_id: int) -> dict:
    """
    若 payload 中密码字段为 '••••••' 且 task_id 有效：
    从 CollectModels(id=task_id).decrypt_credentials 取对应字段明文并替换。
    task_id 无效或字段不存在时抛出 ValidationError。
    """

def execute_debug(payload: dict, service_name: str, timeout: int) -> dict:
    """
    后台任务中调用 Stargazer RPC 执行诊断。
    NATS request timeout = timeout + 5s。
    返回标准化后的响应 dict（附加 request_id, executor, meta）。
    """

def build_prefill(task_id: int, protocol: str) -> dict:
    """
    从 CollectModels 读取任务快照，提取可填字段。
    密码字段脱敏。返回 prefill dict，can_prefill=false 时只返回粗粒度提示。
    """
```

```python
# server/apps/rpc/stargazer.py（新增方法）

class Stargazer:

    def collection_tool_debug(self, payload: dict, timeout: int) -> dict:
        """
        通过 NATS request 调用 Stargazer debug handler。
        subject 由调用方通过 instance_id 确定（已包含在 self.instance_id 中）。
        handler name 按 protocol 区分：debug_snmp / debug_ipmi。
        nats_timeout = timeout + 5
        """
        handler = f"debug_{payload['protocol']}"
        return self.client.request(handler, timeout=timeout + 5, **payload)
```

### 4.3 Stargazer NATS Handler

```python
# agents/stargazer/service/nats_server.py（新增）

@register_handler("debug_snmp")
async def debug_snmp(data: dict) -> dict:
    """
    接收 CMDB 的 SNMP 诊断请求。
  data 字段：protocol, action, target, port, timeout, credential, oid(可选，仅 get_oid)
    返回：success, stage, summary, raw_log, duration_ms
    """
    return await ProtocolDebugService(data).execute()

@register_handler("debug_ipmi")
async def debug_ipmi(data: dict) -> dict:
    """
    接收 CMDB 的 IPMI 诊断请求。
    data 字段：protocol, action, target, port, timeout, credential
    返回：success, stage, summary, raw_log, duration_ms
    """
    return await ProtocolDebugService(data).execute()

# 注：采集工具的“测试连通性”通过 debug_snmp/debug_ipmi + action=test_connection 实现，
# 不复用当前通用的 test_connection 占位 handler。
```

### 4.4 Stargazer 执行层

```python
# agents/stargazer/service/debug/protocol_debug_service.py

class ProtocolDebugService:
    def __init__(self, data: dict):
        self.data = data

    async def execute(self) -> dict:
        """
        按 action 分发到对应执行函数。
        统一捕获异常，映射到 stage + summary。
        记录 duration_ms。
        """
        action = self.data["action"]
      if action == "test_connection":
        if self.data["protocol"] == "snmp":
          return await run_snmp_test_connection(self.data)
        return await run_ipmi_test_connection(self.data)
      elif action == "raw_collect":
            return await run_bulk_walk(self.data)
        elif action == "get_oid":
            return await run_get_oid(self.data)
        elif action == "ipmi_collect":
            return await run_ipmi_debug(self.data)
```

```python
# agents/stargazer/service/debug/snmp_debug.py

async def run_snmp_test_connection(params: dict) -> dict:
  """
  对固定 OID 1.3.6.1.2.1.1.1.0 执行一次 snmpget。
  使用 pysnmp asyncio API。
  timeout: params["timeout"]（由 CMDB 注入，固定 10s）
  成功时返回单行 raw_log，异常映射与其他 SNMP 动作一致。
  """

async def run_bulk_walk(params: dict) -> dict:
    """
    从固定根 OID 1.3.6.1.2.1 执行 snmpbulkwalk。
    使用 pysnmp asyncio API。
    timeout: params["timeout"]（由 CMDB 注入，固定 120s）
    异常映射：socket 超时 → stage=timeout，USM → stage=auth，等。
    """

async def run_get_oid(params: dict) -> dict:
    """
    对 params["oid"] 执行 snmpbulkwalk。
    使用 pysnmp asyncio API。
    timeout: params["timeout"]（由 CMDB 注入，固定 300s）
    异常映射同上。
    """

def _build_snmp_auth(credential: dict):
    """
    根据 version / level 构建 pysnmp CommunityData 或 UsmUserData。
    复用现有 SnmpFacts._get_snmp_auth() 逻辑。
    """

def _format_raw_log(var_binds) -> str:
    """将 pysnmp varBinds 格式化为 'OID = TYPE: VALUE' 文本。"""
```

```python
# agents/stargazer/service/debug/ipmi_debug.py

async def run_ipmi_test_connection(params: dict) -> dict:
  """
  使用 pyghmi.ipmi.command.Command 建立 IPMI 会话。
  privilege 从 params["credential"] 读取；未提供时默认 'administrator'。
  调用轻量查询（如 get_power）验证连通性与凭据。
  timeout: params["timeout"]（由 CMDB 注入，固定 10s）
  """

async def run_ipmi_debug(params: dict) -> dict:
    """
    使用 pyghmi.ipmi.command.Command 连接 IPMI。
  privilege 从 params["credential"] 读取；未提供时默认 'administrator'。
    cipher_suite 若存在则传入，不存在则不传（使用 pyghmi 默认值）。
    调用 command.get_inventory() 并格式化为可读文本作为 raw_log。
    timeout: params["timeout"]（由 CMDB 注入，固定 30s）
    """
```

### 4.5 前端 API 函数

```typescript
// web/src/app/cmdb/api/collectTool.ts

export const useCollectToolApi = () => {
  const { get, post } = useApiClient()

  const executeCollectTool = (payload: CollectToolExecuteRequest) =>
    post<CollectToolExecuteResponse>('/cmdb/api/collect_tool/execute/', payload)

  const getCollectToolPrefill = (taskId: number, protocol: string) =>
    get<CollectToolPrefillResponse>('/cmdb/api/collect_tool/prefill/', {
      task_id: taskId,
      protocol,
    })

  return { executeCollectTool, getCollectToolPrefill }
}
```

### 4.6 前端 TypeScript 类型

```typescript
// web/src/app/cmdb/types/collectTool.ts

export type Protocol = 'snmp' | 'ipmi'
export type SnmpAction = 'test_connection' | 'raw_collect' | 'get_oid'
export type IpmiAction = 'test_connection' | 'ipmi_collect'
export type Action = SnmpAction | IpmiAction

export type SnmpVersion = 'v2' | 'v2c' | 'v3'
export type SecurityLevel = 'authNoPriv' | 'authPriv'
export type IntegrityProtocol = 'sha' | 'md5'
export type PrivacyProtocol = 'aes' | 'des'

export interface SnmpCredential {
  version: SnmpVersion
  community?: string         // v2/v2c
  username?: string          // v3
  level?: SecurityLevel      // v3
  integrity?: IntegrityProtocol  // v3 authNoPriv/authPriv
  authkey?: string           // v3 authNoPriv/authPriv
  privacy?: PrivacyProtocol  // v3 authPriv
  privkey?: string           // v3 authPriv
}

export interface IpmiCredential {
  username: string
  password: string
  privilege?: 'callback' | 'user' | 'operator' | 'administrator'
  cipher_suite?: string
}

export interface CollectToolExecuteRequest {
  protocol: Protocol
  action: Action
  access_point_id: string
  target: string
  port: number
  credential: SnmpCredential | IpmiCredential
  oid?: string      // protocol=snmp 且 action=get_oid 时必填
  task_id?: number  // 预填场景下传入，用于后端解密原始凭据
}

export type DebugStage = 'connect' | 'auth' | 'collect' | 'timeout' | 'param' | 'unknown'

export interface CollectToolExecuteResponse {
  request_id: string
  protocol: Protocol
  action: Action
  executor: string
  success: boolean
  stage?: DebugStage
  summary?: string
  raw_log: string
  duration_ms: number
  meta: { target: string; port: number }
}

export interface CollectToolPrefillResponse {
  task_id: number
  protocol: Protocol
  can_prefill: boolean
  prefill?: {
    access_point?: { id: string; name: string }
    target?: string
    port?: number
    credential?: Partial<SnmpCredential> | Partial<IpmiCredential>
  }
}

// 前端执行状态机
export type ExecStatus = 'idle' | 'running' | 'success' | 'error'
```

---

## 5) 前端交互规格

### 5.1 SNMP 表单字段与联动规则

| 字段 | 必填 | 显示条件 |
|------|------|---------|
| Target IP | 是 | 始终显示 |
| SNMP Port | 是 | 始终显示，默认 `161` |
| 接入点 | 是 | 始终显示，Select 下拉 |
| Version | 是 | 始终显示，v2 / v2c / v3 |
| Community | v2/v2c 时必填 | version = v2 或 v2c |
| Security Name | v3 时必填 | version = v3 |
| Security Level | v3 时必填 | version = v3，选项与现有任务一致：`authNoPriv` / `authPriv` |
| Hash Algorithm | 条件必填 | version=v3 |
| Auth Password | 条件必填 | version=v3 |
| Priv Protocol | 条件必填 | version=v3 且 level = authPriv |
| Priv Password | 条件必填 | version=v3 且 level = authPriv |

- **不显示 Timeout 输入项。**
- 前端表单内部字段命名沿用现有 `snmpTask.tsx`：`version/snmp_port/level/username/integrity/authkey/privacy/privkey`，提交执行请求前再归一化到 collect tool 请求体。
- 密码字段提供明文/脱敏切换按钮（👁）。

### 5.2 SNMP 执行按钮

| 按钮 | 触发操作 | 额外交互 |
|------|---------|---------|
| 测试连通性 | `action=test_connection` | 直接发起请求，固定探测 `1.3.6.1.2.1.1.1.0` |
| 获取原始数据 | `action=raw_collect` | 直接发起请求，固定遍历 `1.3.6.1.2.1` |
| 获取OID数据 | `action=get_oid` | 先弹出 OidModal，用户输入 OID 并确认后发起请求 |
| 暂停 | - | 停止前端轮询与计时，不影响后台执行 |

`OidModal` 规格：
- 单行文本输入，placeholder: `例如：1.3.6.1.2.1.1.1.0`
- 前端格式校验：`/^[\d.]+$/`，不通过时内联提示"OID 格式不正确"
- 按钮：确认（触发请求）/ 取消

### 5.2.1 采集工具权限

- 页面访问：依赖菜单 `collection_tool` 的 `View` 权限决定页面可见与前端访问态。
- 后端接口：
  - `GET /cmdb/api/collect_tool/prefill/` 需要 `collection_tool-View`
  - `GET /cmdb/api/collect_tool/result/` 需要 `collection_tool-View`
  - `POST /cmdb/api/collect_tool/execute/` 需要 `collection_tool-Execute`
- 前端按钮：所有诊断执行按钮均要求当前路由具备 `Execute` operation；仅有 `View` 时可看页面与历史结果区，但不能提交诊断。

### 5.3 IPMI 表单字段

| 字段 | 必填 | 说明 |
|------|------|------|
| Target IP | 是 | |
| Port | 是 | 默认 `623` |
| 接入点 | 是 | Select 下拉 |
| Username | 是 | |
| Password | 是 | 明文/脱敏切换 |
| Privilege | 是 | Select 下拉，默认 `administrator` |
| Cipher Suite | 否 | 文本输入，不填时不传 |

- **不显示 Timeout 输入项。**
- **显示 privilege 输入项，默认值为 `administrator`。**

执行按钮：

| 按钮 | 触发操作 | 额外交互 |
|------|---------|---------|
| 测试连通性 | `action=test_connection` | 直接发起请求，执行轻量 IPMI 会话校验 |
| 执行采集 | `action=ipmi_collect` | 直接发起请求 |
| 暂停 | - | 停止前端轮询与计时，不影响后台执行 |

### 5.4 执行状态机

```
IDLE
  ↓ 点击测试连通性 / 获取原始数据（或 OidModal 确认）
RUNNING
  • 按钮变为禁用状态
  • 显示计时器（格式 Timer: 00:00）
  • 显示 "● Running"
  ↓ 收到响应 / HTTP 超时
SUCCESS（success=true）
  • 显示 "✓ Success"
  • ResultPanel 展示 raw_log
  • "导出文本"按钮可用
ERROR（success=false）
  • 显示 "✗ Failed"
  • ResultPanel 顶部展示 summary（红色 banner）
  • ResultPanel 展示 raw_log（若有）
  • "导出文本"按钮可用（若有 raw_log）
  ↓ 点击暂停 / 修改参数后再次执行
IDLE
```

### 5.5 导出文本

- 纯前端实现，`Blob` + `URL.createObjectURL` 下载。
- 文件名格式：`collection_log_{protocol}_{ip}_{yyyyMMddHHmmss}.txt`
- 内容：`raw_log` 原始文本，不做任何额外包装。

---

## 6) 影响范围与改动点

### 前端改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `featureLibrary/collectionTool/page.tsx` | 新增 | 主页面，读取 searchParams，Tab 切换 |
| `featureLibrary/collectionTool/components/SnmpTool.tsx` | 新增 | SNMP 表单，v3 动态联动，三个执行按钮 |
| `featureLibrary/collectionTool/components/IpmiTool.tsx` | 新增 | IPMI 表单，两个执行按钮 |
| `featureLibrary/collectionTool/components/ResultPanel.tsx` | 新增 | raw log 展示、导出按钮 |
| `featureLibrary/collectionTool/components/OidModal.tsx` | 新增 | OID 输入弹窗 |
| `featureLibrary/collectionTool/hooks/useCollectTool.ts` | 新增 | 执行状态机、计时器、结果管理 |
| `collection/profess/components/taskDetail.tsx` | 修改 | 失败摘要区域新增跳转入口 |
| `api/collectTool.ts` | 新增 | API 请求函数 |
| `types/collectTool.ts` | 新增 | TypeScript 类型 |
| `locales/zh.json` / `en.json` | 修改 | 新增文案 key |

### CMDB 后端改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `views/collect_tool.py` | 新增 | CollectToolViewSet（execute + prefill） |
| `services/collect_tool_service.py` | 新增 | 业务逻辑（校验、接入点解析、NATS 调用） |
| `serializers/collect_tool.py` | 新增 | 请求/响应序列化 |
| `urls.py` | 修改 | 注册 `/cmdb/api/collect_tool/` 路由 |
| `apps/rpc/stargazer.py` | 修改 | 新增 `collection_tool_debug()` 方法 |

### Stargazer 改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `service/nats_server.py` | 修改 | 注册 `debug_snmp` / `debug_ipmi` handler |
| `service/debug/protocol_debug_service.py` | 新增 | 统一入口，按 action 分发 |
| `service/debug/snmp_debug.py` | 新增 | bulkwalk + snmpget 实现 |
| `service/debug/ipmi_debug.py` | 新增 | IPMI 采集实现 |

### 数据库

- **无 schema 变更，无新表。**

---

## 7) 测试方案

### 后端单元测试

**`prefill` 接口：**
- 失败任务（SNMP v2c）可返回 target、port、access_point、community（脱敏）
- 失败任务（SNMP v3 authPriv）可返回完整 v3 凭据字段（密码脱敏）
- 失败任务（IPMI）可返回 target、port、username（密码脱敏）
- task_id 不存在时返回 `can_prefill=false`
- 接入点无法解析时 `access_point` 留空，其余可解析字段照常返回

**`execute` 接口（Mock Stargazer NATS）：**
- SNMP `test_connection` 使用固定 OID 组装 NATS payload，不要求前端传 `oid`
- SNMP v2c `raw_collect` 参数校验通过，正确组装 NATS payload
- SNMP v3 `get_oid` oid 格式校验：合法值通过，含字母值拒绝
- IPMI `test_connection` 执行轻量查询，超时与认证失败正确映射为 `stage=timeout/auth`
- IPMI `ipmi_collect` cipher_suite 选填：不传时 NATS payload 不含该字段
- `access_point_id` 不存在时返回 `stage=param`
- 密码为 `"••••••"` 且 task_id 有效时正确注入解密后的明文
- 密码为 `"••••••"` 且 task_id 无效时返回 `stage=param`
- NATS 超时时返回 `stage=timeout`

### Stargazer 单元测试

**`snmp_debug`：**
- `run_snmp_test_connection` v2c 成功，返回固定 OID 单行结果
- `run_snmp_test_connection` v3 认证失败，stage=auth
- `run_bulk_walk` v2c 成功，raw_log 格式正确
- `run_bulk_walk` v3 认证失败，stage=auth，summary 包含错误关键词
- `run_bulk_walk` 网络不可达，stage=connect
- `run_get_oid` 有效 OID 返回多行 bulkwalk 结果
- `run_get_oid` OID 不存在返回 stage=collect

**`ipmi_debug`：**
- `run_ipmi_test_connection` 连接成功，raw_log 返回轻量查询结果
- `run_ipmi_test_connection` 认证失败，stage=auth
- `run_ipmi_debug` 连接成功，raw_log 包含设备信息
- `run_ipmi_debug` 认证失败，stage=auth
- 未传 privilege 时默认使用 administrator；传入其他合法 privilege 时按传入值执行
- cipher_suite 不传时正常执行

### 前端测试

- 现有 SOID 页面保持不变，采集工具以独立一级页面进入，不与 SOID 页面合并为页面组
- 页面入口可见，URL 含 `protocol=snmp` 时自动切换到 SNMP Tab
- `taskId` 存在时自动调用 prefill，表单回填，密码字段显示 `••••••`
- prefill 失败时展示"无法自动带入"提示
- SNMP 表单字段与联动和现有 `snmpTask.tsx` 保持一致：Version=`v2/v2c/v3`，v3 使用 `level/integrity/privacy/authkey/privkey`
- "测试连通性"按钮点击后按当前表单参数发起请求，SNMP 不额外弹 OID 输入框
- "获取OID数据"弹窗：OID 格式校验，确认后发起请求
- IPMI "测试连通性"按钮可见，并触发 `action=test_connection`
- 执行状态机：RUNNING → SUCCESS / ERROR 状态展示正确
- 导出文件名格式正确，内容为纯 raw_log

### 联调回归

- CMDB → NATS → Stargazer → 真实网络设备，全链路 SNMP `test_connection` 成功
- CMDB → NATS → Stargazer → 真实网络设备，全链路 SNMP `raw_collect` 成功
- CMDB → NATS → Stargazer → 真实服务器，全链路 IPMI `test_connection` 成功
- CMDB → NATS → Stargazer → 真实服务器，全链路 IPMI `ipmi_collect` 成功
- 切换接入点后，请求路由到正确 Stargazer 节点
- `raw_collect` 300s 内正常返回；超时场景下前端展示超时结果
- 失败任务跳转后一键执行全链路闭环

---

## 8) 发布与回滚策略

### 发布顺序

1. **Stargazer**：发布 `debug_snmp` / `debug_ipmi` NATS handler 与 debug service。
2. **CMDB 后端**：发布 `CollectToolViewSet`、service、RPC 方法。
3. **CMDB 前端**：发布采集工具页面与失败任务跳转入口。

顺序原因：Stargazer handler 先上线，CMDB 后端才能正常调用；CMDB 后端先于前端上线，前端上线时接口已就绪。

### 回滚策略

| 异常场景 | 回滚动作 |
|---------|---------|
| 前端页面异常 | 回退前端版本，后端与 Stargazer 可保留（不影响现有功能） |
| CMDB 后端接口异常 | 回退后端版本，移除 `collect_tool` 路由注册 |
| Stargazer handler 异常 | 移除 `debug_snmp` / `debug_ipmi` 注册，重启 Stargazer |
| 全链路不可用 | 按"前端 → 后端 → Stargazer"逆序回滚 |

- 无数据库迁移，所有回滚不涉及 schema 处理。
- 回滚后现有采集任务功能（`CollectModels` / `exec_task` 链路）不受影响。

---

## 9) 待确认项（需人工确认后再实现）

- **`/cmdb/api/collect/nodes/` 返回字段名**：该接口透传 `node_mgmt` 的 NATS 响应，字段结构不在 CMDB 层定义。前端 Select 展示节点名称、传递节点 ID 所需的字段名（如 `id`、`name`），需对照现有 `profess/page.tsx` 接入点 Select 实现确认，直接复用相同取值逻辑即可。

- **pysnmp asyncio API**：现有 `SnmpFacts` 使用 `pysnmp.entity.rfc3413.oneliner.cmdgen`（同步 API），Stargazer 是 Sanic（asyncio）环境。新的 debug handler 是 async 函数，需确认 bulkwalk/snmpget 实现是使用 `pysnmp.hlapi.asyncio` 还是用 `asyncio.to_thread()` 包装同步调用，避免阻塞 event loop。

- **pyghmi 超时机制（已确认，无需人工介入）**：pyghmi `Command.__init__` 不接受 connect timeout 参数，内部通过重试机制控制（`maxtimeout=2s`，初始包 0.5s 随机 jitter）。强制超时需在 Stargazer 执行层用 `asyncio.wait_for()` 包裹整个 `get_inventory()` 调用，超时后 cancel 协程，保证 30s 内必定返回结果，不会挂起 handler。实现方式：
  ```python
  result = await asyncio.wait_for(
      asyncio.to_thread(command.get_inventory),
      timeout=30
  )
  ```
  超时触发 `asyncio.TimeoutError`，映射为 `stage=timeout`。
