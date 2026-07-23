# CMDB SOID 权威目录丰富与安全同步设计

## 背景

CMDB 通过 SNMP `sysObjectID`（下文简称 SOID）精确匹配 `OidMapping`，进而确定网络设备的品牌、型号和 CMDB 模型。当前权威文件 `server/apps/cmdb/support-files/systemoid.json` 收录 1,966 条记录，但主体数据长期未系统更新，品牌命名、型号质量和验证状态不统一，部分主流新设备无法命中。

现有 `init_oid` 还存在存量升级缺口：数据库只要存在任意 `built_in=True` 记录，默认初始化就整体跳过。因而仅更新 JSON 只能惠及全新部署，无法自动丰富已有环境；使用 `--force` 则会先删除全部内置记录再重建，存在不必要的空窗和记录身份变化。

本设计在不改变采集运行链路、数据库结构和 API 合同的前提下，建立可追溯、可验证、可安全升级的 SOID 权威目录。

## 目标

1. 依据厂商官方产品 MIB 和文档，纠正并丰富主流网络设备 SOID。
2. 中国政企市场优先，同时覆盖国际主流厂商。
3. 仅覆盖现有 `switch`、`router`、`firewall`、`loadbalance` 四类 CMDB 模型。
4. 让新部署和存量升级通过同一幂等流程获得一致的内置目录。
5. 全面纠正有官方证据的内置映射，同时保护用户自定义映射和目录外历史识别能力。
6. 通过离线校验和自动化测试防止格式错误、来源冲突、误分类与破坏性同步。

## 非目标

- 不新增 AP、无线控制器、服务器、存储、UPS 等 CMDB 模型。
- 不改变 `CollectNetworkMetrics` 的精确 OID 匹配和未知设备回退逻辑。
- 不使用企业号前缀、`sysDescr` 或字符串相似度进行模糊识别。
- 不在部署、启动、同步或测试阶段访问互联网。
- 不提交厂商原始 MIB 文件，也不建设自动下载厂商 MIB 的长期流水线。
- 不自动删除目录外的历史内置 OID。

## 现状约束

- `OidMapping.oid` 是唯一字段，现有表结构已能表达本需求，不需要迁移。
- 采集对象初始化时从 `OidMapping` 全量构建精确匹配字典；数据库中的品牌、型号和 `device_type` 会直接进入采集结果。
- 未命中 SOID 时，现有逻辑返回未知品牌、未知型号和默认 `switch`。该行为虽然可进一步改进，但不属于本次范围。
- `batch_init` 会调用 `init_oid`，因此 `init_oid` 必须既适合新装初始化，也适合每次升级时安全重放。
- 用户通过 SOID 管理 API 创建的记录为 `built_in=False`，必须拥有高于内置目录的优先级。

## 总体方案

采用“版本化权威目录 + 离线校验 + 非破坏幂等同步”方案。

```text
厂商官方 MIB/文档
        │ 开发期人工核验与提取
        ▼
systemoid.json + systemoid.meta.json
        │ 离线加载、规范化、冲突校验
        ▼
OID 目录差异（新增/更新/未变/用户覆盖/目录外遗留）
        │ transaction.atomic + 批量 ORM
        ▼
OidMapping
        │ 现有精确匹配逻辑
        ▼
CollectNetworkMetrics
```

### 组件边界

#### 权威目录 `systemoid.json`

继续保留现有 JSON 对象结构，以数字点分 OID 为 key。现有消费方依赖的字段保持不变：

- `OID`
- `FirstTypeId`
- `FirstTypeName`
- `SecondTypeId`
- `SecondTypeName`
- `model`
- `brand`

每条记录增加两个不参与落库的追溯字段：

- `source_id`：指向元数据文件中的来源定义。
- `verification`：仅允许 `verified` 或 `legacy-compatible`。

文件按 OID 各数字段的数值顺序稳定排列，避免词典序导致 `...1.10` 排在 `...1.2` 前，并降低后续审查噪声。

#### 元数据文件 `systemoid.meta.json`

元数据与运行数据分离，包含：

- `schema_version`：目录结构版本。
- `catalog_version`：本次目录内容版本。
- `allowed_device_types`：四类允许值。
- `brand_aliases`：历史品牌名到规范展示名的映射。
- `sources`：来源编号、厂商、官方 URL、MIB/文档名称、版本或发布日期、核验日期。

来源 URL 只在元数据中保存一次，避免在数千条记录中重复。若同一个产品 MIB 覆盖多个型号，多条 SOID 可复用同一 `source_id`。

#### 目录加载与同步单元

在 CMDB 服务层提供独立单元，负责：

1. 加载权威目录和元数据。
2. 将记录转换为固定的目录数据结构。
3. 执行完整校验并生成稳定的差异结果。
4. 在调用方提供的事务边界内批量新增或更新 `OidMapping`。

该单元不依赖采集插件、不访问网络、不修改 CMDB 实例，也不处理 API 权限。`init_oid` 只负责解析命令参数、调用该单元和输出统计。

#### 管理命令 `init_oid`

默认执行安全同步，不再因已有内置记录而整体跳过。新增 `--dry-run`；保留 `--force` 兼容既有自动化，但其语义调整为强制重新比较完整目录，仍不得删除记录。

## 目录规范

### OID

- 必须是无前导点、无尾随点、无空白的数字点分格式。
- JSON key 必须与记录中的 `OID` 完全一致。
- 必须位于合法的 ASN.1 OID 数字空间；厂商产品 OID 的企业号根必须能在 IANA Private Enterprise Numbers 注册表中对应到该厂商或其合法历史主体。
- `.0` 不做机械裁剪。只有厂商文档或真实设备证据明确表明其属于返回的 sysObjectID 时才保留。
- 不允许把普通监控指标、表节点、Trap 节点或 `sysObjectID.0` 查询对象本身误作产品身份 OID。

### 设备类型

`FirstTypeId` 只允许：

- `Switch`
- `Router`
- `Firewall`
- `loadbalance`

落库时沿用现有行为转换为小写。设备类型必须由厂商产品系列或产品 MIB 明确支持；不得仅凭企业号、OID 前缀或型号名称关键词推断。

### 品牌

品牌使用稳定、可读的规范展示名，例如 `Huawei`、`H3C`、`Ruijie`、`Cisco`、`Palo Alto Networks`。历史名称和大小写变体进入 `brand_aliases`，不继续作为新目录值使用。

收购或品牌迁移场景以设备实际报告的产品 MIB 和当前可识别品牌为准；若同一硬件系列跨品牌发布，必须由不同 SOID 或明确来源区分，不能仅依据企业号统一改名。

### 型号

- 优先使用厂商正式产品型号。
- 官方产品 MIB 只给出稳定 symbol 时，可以保留该 symbol。
- 不使用 OID 字符串充当已验证型号。
- 不从聚合站、论坛或搜索摘要猜测营销型号。
- 无法公开确认但现网可能依赖的历史记录保留原值，并标记为 `legacy-compatible`。

### 验证状态

- `verified`：OID、品牌、型号和设备类型均有可追溯的官方依据。
- `legacy-compatible`：来自既有目录，暂时缺少稳定的公开官方依据；为保护现网识别而保留，不得作为复制或推导新记录的依据。

## 厂商覆盖策略

### 第一优先级：中国政企常见厂商

Huawei、H3C、Ruijie、ZTE、Sangfor、Hillstone、DPtech、Topsec、Venustech、NSFOCUS、Qi-Anxin。

### 第二优先级：国际主流厂商

Cisco、Juniper、Aruba/HPE、Arista、Fortinet、Palo Alto Networks、F5、Extreme、Nokia。

### 第三优先级：现有历史品牌

Brocade、Force10、Netscreen、Nortel、Maipu、博达等。第三优先级主要完成兼容性校验、规范命名和有证据的纠错，不以扩大旧型号数量为目标。

### 来源优先级

1. 厂商官方产品 MIB 或官方 MIB 下载页面。
2. 厂商官方产品版本 MIB 参考文档、MIB 查询工具或产品支持列表。
3. IANA PEN 注册表，仅用于验证企业号根，不用于推导具体产品型号或类型。
4. 真实设备的 `sysObjectID` 与 `sysDescr` 对照，只能作为已有客户样本的补充证据；进入内置目录前仍应尽量取得厂商资料。

需要登录且无法稳定引用的厂商资料不能作为自动新增的唯一依据。第三方开源 NMS、论坛和聚合 OID 站只能用于发现候选，不能作为 `verified` 的最终来源。

## 同步数据流

### 校验阶段

同步前一次性完成以下校验：

1. JSON 结构和 schema 版本有效。
2. key 与 `OID` 字段一致，OID 格式合法且唯一。
3. 必填字段非空，设备类型属于允许集合。
4. 品牌已经是规范名，不是未转换别名。
5. `source_id` 存在，验证状态合法。
6. `verified` 来源具备厂商、官方 URL、资料名称和核验日期。
7. 同一 OID 不存在品牌、型号或设备类型冲突。

任一校验失败即抛出 `CommandError`，不得进入数据库事务。

### 差异阶段

以 OID 为键，将目录与数据库划分为：

- `create`：数据库不存在。
- `update`：数据库存在且 `built_in=True`，业务字段与目录不同。
- `unchanged`：数据库内置值与目录一致。
- `custom_override`：数据库存在且 `built_in=False`。
- `stale_builtin`：数据库存在内置记录，但目录中不存在。

差异结果的排序稳定，便于 `--dry-run`、日志和测试比较。

### 写入阶段

- 使用 `transaction.atomic` 包裹本次写入。
- `create` 使用分批 `bulk_create`。
- `update` 只更新 `model`、`brand`、`device_type` 和必要的维护字段；不改 OID，不替换记录主键。
- `unchanged` 不执行 `save` 或 `bulk_update`，避免无意义刷新时间。
- `custom_override` 始终跳过，并在结果中列出数量和 OID。
- `stale_builtin` 只报告，不删除、不降级、不改为用户记录。

数据库异常导致整个事务回滚。提交成功后输出 `新增/更新/未变化/用户覆盖/目录外遗留` 五类计数。

### 参数语义

- 默认：校验、生成差异并写入安全变更。
- `--dry-run`：校验并输出完整差异摘要，零数据库写入。
- `--force`：为兼容旧调用保留，强制重新读取和比较完整目录；其写入规则与默认模式相同，绝不执行删除重建。
- `--dry-run --force`：允许组合，仍为零写入。

## 兼容性与失败处理

- 采集精确匹配、未知 OID 回退、API 序列化、权限和数据库模型均不改变。
- 新部署和升级环境均走相同同步算法，目录内置结果一致。
- 用户自定义记录具有最高优先级；即使目录新增相同 OID，也不覆盖用户值。
- 目录外内置记录保留，避免升级后存量设备从已识别退化为未知。
- 全面纠正只修改权威目录中有证据的 `built_in=True` 记录。纠正 `device_type` 后，设备会在下一次采集按正确模型归类；不迁移或重写既有 CMDB 实例。
- 同步不使用远程请求，官方站点不可用不会影响部署。
- 日志不得包含 SNMP 凭据、客户地址或真实设备返回内容；只输出目录 OID、差异类型、来源编号和计数。

## 测试设计

实现遵循 TDD，先稳定复现“已有内置记录导致新增目录项无法同步”的缺陷，再编写最小实现。

### 目录纯测试

- JSON 和元数据可解析。
- OID 格式、key/字段一致、数值排序和唯一性正确。
- 必填字段、允许类型、规范品牌、来源引用与验证状态正确。
- `verified` 记录具备完整来源元数据。
- 普通指标 OID、Trap OID 和明显无效型号被拒绝。
- `.0` 记录必须具备明确来源或保留理由。
- 第一、第二优先级厂商各选择代表性现代型号作为防回退样本。
- 当前 1,966 条 OID 均能在新目录中找到明确处置，不允许无说明消失。

### 同步命令测试

- 空库初始化全部内置记录。
- 存量库新增缺失目录项。
- 有差异的内置记录被原地更新。
- 用户自定义冲突保持原值。
- 未变化记录不刷新更新时间。
- 目录外内置记录保留。
- `--dry-run` 不写数据库。
- `--force` 不删除记录。
- 重复执行结果幂等。
- 目录校验失败时零写入。
- 批量写入异常时事务完整回滚。
- 输出五类统计与实际差异一致。

### 采集回归

- `switch`、`router`、`firewall`、`loadbalance` 各选一条纠正后的 SOID，验证品牌、型号和模型映射。
- 未知 SOID 的默认回退保持现状。
- 现有网络采集 E2E 的 Cisco 样本继续通过。
- 用户自定义 OID 在采集时优先于同名内置候选。

### 质量门禁

- 新增和修改代码的行为覆盖率不低于 75%。
- 运行目录纯测试、`init_oid` 定向测试、网络采集定向测试和现有网络 E2E。
- 运行 Server 对应静态检查、迁移一致性检查和仓库要求的后端门禁；若既有环境缺陷阻断全量门禁，必须单列基线问题与已完成的等价验证，不得误报通过。

## 验收标准

1. 当前 1,966 条记录均被标记为 `verified` 或 `legacy-compatible`，或在同一 OID 下依据官方证据完成纠正。
2. 第一、第二优先级厂商中，具备公开官方产品 MIB 的厂商均有来源条目和相应映射；受登录限制的缺口被明确记录，不用第三方数据补数。
3. 目录只包含四类现有 CMDB 模型，且所有 `verified` 记录通过格式、来源和冲突校验。
4. 默认 `init_oid` 能向已有环境新增和更新内置映射，且重复执行幂等。
5. 用户自定义 OID、目录外历史内置 OID和数据库主键不被删除或覆盖。
6. `--dry-run` 可在升级前准确报告变更，`--force` 不再执行破坏性重建。
7. 采集、API、数据库 schema 和未知 OID 回退合同保持不变。
8. 所有定向测试与可运行的 Server 质量门禁通过。

## 发布与回滚

### 发布

1. 先在升级环境运行 `init_oid --dry-run`，审核五类差异及内置 `device_type` 纠正项。
2. 备份 `OidMapping` 表或通过部署数据库快照保留回滚点。
3. 正常执行 `batch_init`，由默认安全同步写入。
4. 抽查四类代表设备的新采集结果，并重点检查被纠正 `device_type` 的 OID。

### 回滚

- 代码和目录可回滚到上一版本。
- 数据回滚使用发布前的 `OidMapping` 备份；不得通过删除全部内置记录再运行旧版初始化来替代正式回滚。
- 用户自定义记录在发布和回滚过程中均不应变化。

## 官方资料入口

- IANA Private Enterprise Numbers：<https://www.iana.org/assignments/enterprise-numbers/>
- Cisco SNMP MIB FAQ 与官方 GitHub 获取说明：<https://www.cisco.com/c/en/us/support/docs/ip/simple-network-management-protocol-snmp/9226-mibs-9226.html>
- Huawei MIB 查询工具：<https://info.support.huawei.com/info-finder/tool/zh/enterprise/mib>
- H3C MIB 文档示例：<https://www.h3c.com/en/d_202303/1808738_294551_0.htm>
- Arista SNMP MIB：<https://www.arista.com/en/support/product-documentation/arista-snmp-mibs>
- Fortinet MIB 文档：<https://docs.fortinet.com/document/fortigate/latest/fortigate-mib-information-overview/293724/fortigate-system-mibs>
- Palo Alto Networks Enterprise MIB：<https://docs.paloaltonetworks.com/resources/snmp-mib-files>
- Aruba/HPE MIB 获取说明：<https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/HTML/snmp_mib/Content/Chp_MIB_sppt/loc-mib-fil-web.htm>
