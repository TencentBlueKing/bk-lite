# 凭据补充后的 CMDB 采集接入方案复核

> 本文为前一轮历史复核。其中按 SSH/执行驱动推导类型及“全部入口可用”的结论已被撤回；当前依据见[纠正后的类型目录](cmdb-collection-credential-type-mapping.md)和[118 项原表单清单](../specs/changes/cmdb-collection-credential-guidance/all-118-entry-credential-audit.md)。

日期：2026-09-15。最新状态：四项类型/字段补充已进入社区代码；编辑认证方式时的必需秘密校验已在本地修复并通过回归。CMDB 双来源、tree 分类/实际类型、任务引用保存、下发解析与 key 转换、前端额外连接字段、Region/PC 测试/SNMP-IPMI 调试入口及 CMDB 引用统计已在工作区实现，仍未部署或完成真实目标逐插件验收。存量任务凭据统一按“一次性认证”识别、回显、修改和下发，原端口与任务内加密凭据保留；已有凭据在下发时查最新值，不新增自动轮换推送机制。10 项工作及剩余验收见 §7。

118 项功能复核已发现明确的采集端缺口：Dell PowerStore/HPE 3PAR 缺 Agent 实现，18 个企业协议占位入口虚构成功，目录内 19 个通用 JOB 入口误发现。对应逐行结果见[功能验证记录](cmdb-collection-plugin-validation-2026-09-15.md)；这些缺口不因凭据类型和 key 转换已完成而算可用。

最新决策：按用户要求，18 个企业占位插件同样以现有配置和旧采集页面为凭据接入基线；已有字段足以先确定类型和 key 转换，不再以执行器占位阻塞方案。旧表单存在的问题在后续逐插件测试中一并修正。全版本接入方案可进入实施，字段依据与 18 项映射见 §9；真实采集测试状态仍据实记录。

## 1. 更新基线与覆盖范围

| 项目 | 本次状态 |
|---|---|
| 社区代码 | 已 fetch `origin`，将社区协作仓库 `origin/master` 的 `6e3e1559c` 合并到当前 `feature_windyzhao` |
| 凭据补充提交 | `08f31ad5c`：补齐采集复用所需内置类型，并调整编辑留空保留秘密的行为 |
| 本地合并提交 | `07254f39b`；原本地提交 `27528cb13` 保留，合并无冲突，未推送 |
| 企业代码 | 当前企业检出版本已加入通用协议秘密环境变量、OpenStack 域/Redfish TLS 与 SmartX/FusionCompute 额外字段的参数适配；尚未部署 |
| 对象覆盖 | 当前合并对象树 118 项：社区 45、企业 73；目录外入口、合并平台和多执行器分支继续纳入 |
| 运行环境 | 未部署服务、未刷新实际业务库的内置目录、未修改实际凭据或连接真实采集目标 |

逐对象类型、分类、剩余字段及实现限制见[全量分类目录](cmdb-collection-credential-type-mapping.md)。本轮同步的网络配置文件采集新增 SSH/Telnet 分支，仍使用 `network/network_cli`，不增加对象树条目或独立凭据类型。

## 2. 凭据管理补充验收与反馈清单

### 2.1 已补齐的定义

| 编号 | 原需求 | 当前代码 | 是否还需要补类型/字段 |
|---|---|---|---|
| CRED-01 | SSH 加密私钥口令 | `ssh.passphrase` 已加入，按私钥模式显示；支持秘密加密和留空保留 | 已补齐；编辑必填校验已本地修复，见 R01 |
| CRED-02 | OpenStack 用户名、密码、用户域 | 新增 `openstack`；`user_domain_name` 必填，未提供时默认 `Default` | 已补；CMDB 仍需向执行器传实际域，不能固定默认值 |
| CRED-03 | SNMP 条件必填 | V2C community、V3 用户和安全等级、相应认证/隐私算法与秘密的条件已加入 | 已补齐；编辑升级安全等级的必填校验已本地修复，见 R01 |
| CRED-04 | 独立 Redfish 类型 | 新增主机分类 `redfish`，字段为 username/password | 已补；需区分实际类型 key 和 BMC 连接表单参数 |
| 原有类型 | 分类共用与已有账户类型 | 当前共 13 种类型，7 个分类，16 个分类归属 | 不为每个数据库、每个云资源子对象重复新增相同认证类型 |

证据：[类型定义](../server/apps/system_mgmt/services/credential_builtin.py)、[字段校验](../server/apps/system_mgmt/services/credential_schema.py)、[加密与公开字段](../server/apps/system_mgmt/services/credential_crypto.py)。代码中的定义数量不等于每个部署环境已经成功内置的数量。

### 2.2 仍需反馈或落实的事项

| 编号 | 事项与当前证据 | 应补处理 | 归属 / 性质 |
|---|---|---|---|
| R01 | 原编辑路径跳过全部秘密必填检查，导致模式切换缺少新秘密也能保存 | 已修复：完成留空保留与私钥口令处理后，对最终字段按新模式执行必填校验；无需解密存量秘密；失败不保存 | 本地已完成，9 个新增回归用例通过；沿用 API invalid/400 错误契约 |
| R02 | OpenStack/Redfish 的首选 key 被自定义类型占用时分别改用 `openstack_account` / `redfish_bmc`；两者均被占用则跳过 | tree 绑定实际目录中可用的内置 key，并核对内置身份和字段契约；两者均不可用则标记缺失。不可误用首选 key 的同名自定义类型 | CMDB 与凭据管理；接入契约补充，不是再加一套类型 |
| R03 | 存量任务使用手填凭据，用户要求统一按“一次性认证”处理 | 读取时归一化为一次性认证，编辑默认选中该模式；保存沿用原任务加密凭据和端口，并写入认证来源标记；不迁入公共凭据管理 | 纳入 C03/C05 的存量兼容，不另做端口迁移 |
| R04 | `platform_api` 仍含可选 port/verify_tls，`network_cli` 仍含可选 port | CMDB 仅从仓库选择该插件的认证字段；端口/TLS 明确以任务连接参数为准，禁止无差别字典合并覆盖用户输入。保留字段的其他使用方另行核对 | CMDB 为主；字段归属与合并规则。无需为了本需求直接删掉公共类型字段 |
| R05 | 用户确认旧手填任务不受凭据管理更新影响；已有凭据模式按下发时查询的设计处理 | 每次实际下发查最新凭据并校验停用状态；沿用既有任务下发触发方式，不要求新 revision 字段或自动更新通知 | 已收敛至正常下发接入，不作为独立改造；已下发配置在下一次下发前保持原内容 |
| R06 | 新私钥输入、passphrase 留空时会清掉旧口令；只将 passphrase 留空则保留旧口令 | 文案区分两种情况；验收覆盖换为无口令私钥。若需单独清除口令，须显式定义清除操作，不能把一般“留空”解释为清空 | 凭据管理；交互语义完善，不是缺少采集字段 |

R01 修复前最小复现（隔离测试库，未接入真实节点；以下两例修复后均拒绝保存）：

| 用例 | 前置记录 | 编辑操作 | 预期 | 实际 |
|---|---|---|---|---|
| SSH 切换方式 | password 模式，已有 username/password，无 private_key | 仅将 auth_method 改为 key，不提交 private_key | 拒绝并要求私钥 | 保存成功 |
| SNMP 升级安全等级 | v3/noAuthNoPriv，已有 username，无 auth_password/priv_password | 改为 authPriv，选择 SHA/AES，不提交两个秘密 | 拒绝并要求认证和隐私秘密 | 保存成功 |

这两例共用同一根因。修复保留“编辑未改变认证要求，原秘密已存在时可留空”，不会要求所有编辑都重新输入秘密。正式回归用例位于 [test_credential_service.py](../server/apps/system_mgmt/tests/test_credential_service.py)，覆盖缺字段、空字符串、部分秘密补齐、已有秘密复用、反向切换与失败记录不变。此前已经保存的不完整凭据不做批量数据修改，再次编辑时需补齐当前模式的必填项；回滚代码不涉及数据格式或迁移。

证据：[凭据服务](../server/apps/system_mgmt/services/credential_service.py) 中的 `BUILTIN_KEY_FALLBACKS`、`_builtin_seed_key`、`update_credential`、`_drop_passphrase_after_key_rotation`、`_public_credential`、`resolve_credential`。

### 2.3 不需要继续新增的凭据

| 项目 | 处理 |
|---|---|
| SmartX 专用类型/source | 继续复用 cloud/platform_api；source 留表单，默认 LOCAL；非默认值的下发仍需补齐 |
| FusionCompute 专用类型/user_type | 继续复用 cloud/platform_api；user_type 留表单，默认 0；非默认值的下发仍需补齐 |
| 网络配置文件 Telnet | 复用 network/network_cli；协议、端口由表单选择，enable_password 已有 |
| MySQL 等数据库端口、库名/服务名 | 连接参数留采集表单，不扩入公共账号类型 |
| 云平台 Region、项目、订阅、API 地址和版本 | 按插件契约放任务参数；不能因为不在仓库里就认定无法采集 |
| SSH/JOB 采集的数据库与中间件 | 绑定 host/ssh，不因软件名称额外创建数据库账号类型 |
| K8S 当前引导采集、IP 探活 | 当前链路不强加手工目标凭据；改变协议后再按真实认证需要处理 |
| 企业协议占位插件 | 以当前配置和旧表单作为接入契约，18 项全部纳入映射，不新增未经表单证明的凭据字段；后续实测发现问题一并改正，见 §9 |

## 3. 接入主链路与责任边界

以下是方案约束。主要接线已在工作区实现；生产目录、外部 Monitor 引用计数、真实节点与目标仍须联调和验收。

1. **插件声明**：按具体模型、执行驱动、协议和 OS，声明凭据分类、支持的认证方式、实际类型 key、字段转换及剩余表单项。tree 原有执行驱动 `type` 保留，使用独立字段表达凭据绑定。
2. **表单选择**：保留“一次性认证 / 已有凭据”。已有凭据使用分类、类型、组织和停用条件筛选；只显示公共信息，不向浏览器回传秘密。选择后继续显示端口/TLS/Region/库名和额外认证选项。
3. **任务保存**：已有凭据保存仓库 ID 和剩余参数，不复制秘密；一次性认证沿用任务内加密保存，以兼容周期采集。一次性认证表示不进入公共仓库，并不表示只执行一次。切换来源时只提交当前来源的认证数据。
4. **执行前解析**：后端下发边界以任务有效组织和执行身份查询仓库，验证可用性、类型和支持的认证方式；无权限、停用、删除或字段不全则明确失败，不静默退回其他认证来源。
5. **参数构建**：将仓库认证字段按当前插件转换 key 和枚举值，再与允许的剩余表单参数组装并校验。表单不得覆盖仓库管理的核心秘密；仓库残留端口/TLS 不得覆盖表单连接配置。
6. **下发节点**：组装结果进入现有 NodeParams/秘密环境变量交付路径，不回写仓库秘密到任务记录、普通配置文本或日志。连接测试、Region 查询等执行前辅助接口使用同一解析与转换规则。
7. **后续下发**：已有凭据每次下发查询最新值并检查可用性；存量手填任务按一次性认证读取任务内凭据下发。沿用现有任务下发机制及候选命中/冷却规则；不增加凭据变更自动推送。任务删除、更换凭据后的引用计数随实际引用变化。

任务内已有 `cred_...` 候选标识和仓库 `crd-...` 凭据 ID 含义不同。代码使用 `credential_source`（`inline` / `vault`）表达一次性认证 / 已有凭据，使用独立字段 `vault_credential_id` 保存仓库 ID；保留原 `credential_id` 和 `credential_version` 作为任务候选身份与版本。不能凭 ID 前缀猜测来源。

连接参数沿用当前目标身份和归一化规则。原来逐候选填写的参数在编辑和保存时不应丢失；也不能绕过现有目标解析，擅自将不同端口当作同一目标的认证轮询。

存量任务按“一次性认证”兼容的具体规则：

| 环节 | 行为 |
|---|---|
| 识别 | 历史任务没有认证来源标记且没有仓库引用时，统一识别为一次性认证；原任务候选 ID 不当作仓库 ID |
| 编辑回显 | 默认选中“一次性认证”；保留原账号、端口及其他参数，秘密沿用现有掩码回显与保留机制，不返回明文 |
| 保存修改 | 写入一次性认证来源标记，沿用任务内加密存储；未修改的秘密按现有编辑契约保留，不要求重新填写 |
| 未编辑任务 | 读取和下发时同样按一次性认证处理，不要求先逐条保存或批量重写秘密 |
| 切换已有凭据 | 用户主动切换并选择有效仓库凭据后，才改为保存仓库 ID；保留适用的额外表单参数，清除旧来源认证数据 |
| 周期执行 | 原有采集周期继续生效；一次性认证不等于只执行一次 |

显式声明“已有凭据”但仓库 ID 缺失的任务应报错，不能当作历史任务退回一次性认证。

### 3.1 key/值转换示例

| 入口 | 仓库字段 | 下发适配要求 |
|---|---|---|
| SQL 直连 | username/password | 使用 `user` 的执行器将 username 转为 user；使用 username 的保留；不能对全部插件统一改名 |
| SNMP | security_level、auth_protocol、auth_password、priv_protocol、priv_password | 按 CMDB 契约转 level/integrity/authkey/privacy/privkey，并转换算法大小写；设备、拓扑分支分别核验 |
| 云 AK/SK | access_key/secret_key | 按各平台实际 AK/SK 参数名称转换，不由前端猜测 |
| Azure | client_id/client_secret/tenant_id | 按现有执行器转 username/password 等字段；subscription 等连接范围仍来自表单 |
| OpenStack | username/password/user_domain_name | 保留用户域并透传；project_id/Region/地址来自表单 |
| 平台账户 | username/password | vCenter 等历史 accessKey/accessSecret 字段实际上承载账户密码，应绑定 platform_api 而非 cloud AK/SK |
| 网络配置文件 | username/password/enable_password | 核心字段按现有实现；SSH/Telnet 协议和端口从任务连接参数加入 |

这张表用于说明规则，不替代 118 个入口及额外执行分支的逐项字段映射和验证。

## 4. 工作区已接通的环节与联调状态

| 环节 | 当前证据 | 实施时应完成 |
|---|---|---|
| tree 类型关联 | [collect_object_tree](../server/apps/cmdb/services/collect_object_tree.py) 按对象/驱动/协议返回 `credential_category` 和目录中真实可用的 `credential_type_keys`；备用 key 及字段契约均校验 | 业务库刷新内置目录后核对实际返回 |
| 任务引用存储 | [候选池服务](../server/apps/cmdb/services/collect_credential_pool_service.py) 与 [序列化](../server/apps/cmdb/serializers/collect_serializer.py) 支持双来源、剩余字段与旧数据；切换来源清除旧认证值 | 用实际数据库和多候选任务复测保存/编辑 |
| 解析与转换 | [下发解析器](../server/apps/cmdb/services/collect_vault_resolver.py) 在 BaseNodeParams 构建时解析全部仓库候选，校验目录类型并转换 key；旧手填来源继续原路下发 | 对每个真实采集器核对参数和结果 |
| 权限上下文 | 保存绑定操作者、domain/current_team；周期下发按绑定上下文重新由系统管理核验；手工辅助入口按当前操作者核验 | 用户失效、组织变化及多组织联调 |
| 引用统计 | CMDB responder 已按 `vault_credential_id` 计数；[引用统计服务](../server/apps/system_mgmt/services/credential_ref_count.py) 仍依赖真实 Monitor responder | PostgreSQL JSON 查询及 Monitor 联调；不可伪造零引用 |
| 后续下发读取 | 每次参数构建重新 resolve，停用/越权/类型失配拒绝；旧手填任务不关联仓库 | 实际节点下一次下发行为验证 |
| 前端 | 采集表单已提供来源切换、CredentialPicker 筛选、额外字段与编辑回显；18 个企业旧表单描述已补 | 浏览器交互与全插件逐项测试 |

## 5. 全版本逐插件验收边界

全量行清单沿用[分类目录 §2、§3](cmdb-collection-credential-type-mapping.md)。每一个插件及其实际分支均须记录以下结果，不能用同类代表测试代替：

本轮每项的本地证据、确定缺口及真实目标状态已记入[118 项功能验证记录](cmdb-collection-plugin-validation-2026-09-15.md)。其中 Agent 实现缺失、占位采集器虚构成功和通用 JOB 误发现都属于已复现的功能缺陷，不能仅标为“缺测试环境”。

| 验收维度 | 每个插件必须验证 |
|---|---|
| 凭据管理 | 分类与实际类型匹配；创建、编辑留空、切换认证模式、加密存储、权限、停用及后端 resolve |
| 表单与任务 | 两种认证来源；额外字段持续可填；已有凭据只保存 ID 与剩余参数；存量任务默认一次性认证、修改保存与未编辑直接下发；秘密掩码不覆盖原值；多候选完整性 |
| 执行前转换 | 精确 key、枚举值、默认值和必填校验；不同驱动/OS/协议各自断言，验证秘密不泄漏 |
| 下发与运行 | 实际节点参数和秘密注入；下次下发读取更新值/拒绝停用凭据；候选版本、命中及冷却；连接失败的可定位反馈 |
| 采集结果 | 真实目标认证成功，根对象/子对象/关系完整；一次性认证与已有凭据结果一致 |
| 辅助入口 | 涉及连接测试、Region/项目查询、网络拓扑时，分别核对同一引用与转换规则 |

企业代码中的 18 个协议占位入口：ZStack、F5、安全设备、Couchbase、SAP HANA、InterSystems IRIS、TongRDS、TDSQL、IBM Storwize、IBM DS、EMC Symmetrix、宏杉存储、NetApp Cluster、Oracle ZFS、Infinidat、磁带库、XSKY、Ambari，均按 §9 的现有配置/旧表单基线接入，不再列为映射待明确。每项仍分别测试凭据管理、key 转换、表单与执行；原有表单或执行器错误一并修正，执行器占位不能算作真实采集测试通过。

另有企业脚本仍是通用 ps/uname 摘要，具体受影响对象已在分类目录标注；AIX、HP-UX、国产 Linux 等合并平台分支也须单独核对真实执行内容。凭据认证成功不能替代业务字段采集成功。

## 6. 本次实际验证结果

| 验证 | 结果 | 解释 |
|---|---|---|
| 社区/企业对象树静态复核 | 118 项，企业 73 项；目录外/合并平台分支另列 | 是覆盖清点，不是真实采集测试 |
| 原有后端：schema、crypto、credential_service、网络配置文件 NodeParams | 47 通过、22 setup error | 服务测试被 SQLite 迁移错误阻断：`NewSessionEventRelation has no field named 'event'` |
| credential_service 使用隔离库 `--nomigrations` 复测 | 21 通过、1 失败 | 剩余失败为 SQLite 不支持 JSON contains；不是已确认的凭据业务缺陷，仍需支持该查询的数据库复验 |
| 前端 fields.secretRequired / normalizeFields | 2 个测试文件、5 个用例通过 | 使用 Node 24；证明这些组件用例通过，不代表 CMDB 交互已接入 |
| 修复前两项编辑缺失秘密探针 | 修复前均失败；修复后原探针 2 项通过 | 真实 ORM 服务测试，确认 R01 修复 |
| 修复后服务/schema/crypto 回归 | 58 通过、1 项排除；其中新增 9 项回归通过 | 仍用隔离 SQLite 与 `--nomigrations`；排除上一轮确认不支持的 JSON contains 查询用例 |
| 修复覆盖率 | credential_service 80%；新增校验语句和异常分支均覆盖 | 未改变加密、鉴权、日志和 API 状态码契约 |
| 格式检查 | isort、flake8 通过；Black 检查仍报告原有格式差异 | 差异在原有字典推导和日志模板，不在新增代码；保留无关格式 |
| 全量插件实际目标采集 | 未执行 | 本地映射/转换测试不替代真实目标认证与对象采集；不能标记验收通过 |
| 本轮社区映射/转换与保存/节点参数 | 116 个认证入口分别有分类绑定、目录字段匹配与执行前 key 转换用例；保存、tree、节点参数、网络双通道、辅助接口合计 496 项定向测试通过，另排除 1 项 SQLite 不支持 JSON `contains` 的既有统计用例 | 使用隔离 SQLite/`--nomigrations` 与模拟仓库 RPC；包括调试工具“入队仅 ID、执行端解析”回归，验证参数契约，不证明真实目标认证 |
| 本轮合并对象树逐入口参数验证 | 118 个入口分别验证实际插件/配置制品/K8S 执行路径与类型绑定；116 个需认证入口分别由真实 NodeParams 工厂模拟仓库 ID 查询并渲染节点配置；2 个无认证入口的仓库解析用例跳过 | 企业定向套件合计 264 通过、2 跳过、2 预期失败（Dell PowerStore/HPE 3PAR 缺 Agent 实现）；证明服务端参数边界，不证明真实目标可用 |
| Stargazer Agent 清单/脚本/采集器 | 全部 120 个现有清单与 123 条执行分支分别验证：242 通过、1 预期失败 | MySQL JOB 额外分支引用不存在的 Linux/Windows 脚本；Nginx/Consul model_id 元数据已修复 |
| Stargazer 完整运行链路 | HTTP→Redis→Runtime→Plugin→NATS 用例 14 通过、1 跳过 | 测试使用本机临时 Redis 和模拟插件/NATS，不能代替 118 个具体目标 |
| 企业占位功能探针 | 18 个协议采集器在空目标时仍返回虚构成功；22 个通用 JOB 脚本在只有无关进程时仍输出产品对象；40 项均逐个复现并记为预期失败 | 通用 JOB 中 3 项是目录外合并平台分支；目录内为 19 项，功能不完整 |
| 现有 Stargazer 采集专项回归 | 复测 722 通过、48 失败、6 跳过、1 预期失败；上次同范围为 721 通过、49 失败 | 40 项是旧模块/mock 路径，8 项涉及 PC/Windows/主机回调断言；另有事件循环负载阈值一次波动，详见功能验证记录；不归并为本需求通过 |
| 18 个企业旧表单入口 | 每项分别模拟仓库引用并检查 NodeParams header 与秘密环境变量；OpenStack/Redfish/SmartX/FusionCompute 另有专项 | 原执行器占位不能算真实采集通过；旧表单和目标返回值仍需逐项实测 |
| 本轮前端 | 双来源/Region/Redfish/SNMP 及旧表单描述共 42 项定向用例通过 | 全仓 TypeScript 检查受当前工作区其他模块既有错误阻断；浏览器实际交互和真实对象仍待验收 |

后端原有用例运行方式（在 server 目录，测试专用变量，不读取业务 .env）：

```sh
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=credential-review-test ENABLE_CELERY=true \
.venv/bin/python -m pytest \
apps/system_mgmt/tests/test_credential_schema.py \
apps/system_mgmt/tests/test_credential_crypto.py \
apps/system_mgmt/tests/test_credential_service.py \
apps/cmdb/tests/test_network_config_file_node_params.py \
-o addopts='' --no-cov -q --envfile=/dev/null
```

服务测试隔离迁移复测仅选择 `test_credential_service.py` 并增加 `--nomigrations`。本次临时复现文件为 `/tmp/test_credential_completion_review.py`，结果日志为 `/tmp/credential-completion-probes-20260915.log`；可按 §2 的操作重建用例，不依赖临时文件长期存在。

当前 R01 已完成本地修复；R03/R05 已按用户澄清收敛，不再作为新增阻塞项。后续按 §7 接入统计推进，按 §5 验收每个插件。R06 不作为新增凭据类型的前置条件。不重复要求系统管理添加已经交付的四项定义。

## 7. CMDB 接入统计与实际类型绑定

### 7.1 “实际内置类型”具体指什么

它与认证字段 key 转换是两件事：前者决定选出哪类凭据，后者决定选出的凭据如何组成执行参数。

| 凭据类型 | 正常创建的 key | 同名被自定义类型占用时 |
|---|---|---|
| OpenStack | `openstack` | 内置类型使用 `openstack_account` |
| Redfish | `redfish` | 内置类型使用 `redfish_bmc` |
| 其他类型 | 沿用目录中的既有 key | 不凭类型名称猜测同名自定义类型可用 |

例如部署库里 `openstack` 是用户自定义类型、真正的内置 OpenStack 是 `openstack_account`，CMDB 固定传 `type=openstack` 就查错了。内置时的保护逻辑已存在，不需要再改用户自定义类型。

建议在后续 CMDB 接入中这样处理：

1. 后端通过系统管理公开的 `list_types` 服务读取类型元数据；同进程复用现有服务即可，不直接读凭据秘密，不新增数据库字段。
2. 插件映射声明支持的分类与类型 key：OpenStack 候选为 `openstack`、`openstack_account`；Redfish 候选为 `redfish`、`redfish_bmc`。按实际目录中的 `is_builtin`、分类及认证字段定义筛选，排除同名自定义类型。
3. tree 返回可用的实际类型 key 集合 `credential_type_keys`。通常只有一个；若首选、备用两个内置类型都存在，则允许两者。集合为空时提示该类型未内置，保留一次性认证。当前无需认证的插件不因此新增认证表单。
4. 前端将实际 key 传给 CredentialPicker。沿用当前单类型参数：一个可用类型时直接绑定；多个时显示类型选择，再传当前类型 key；不修改公共查询接口为多类型查询。
5. 保存及下发时校验所选凭据的实际类型属于插件允许集合。然后才做例如 `username → user` 的认证字段转换。

以上绑定步骤已在工作区实现；仍需部署环境确认真实目录实例、权限和停用状态。

### 7.2 按工作项统计

共 **10 项 CMDB 接入工作**，其中前端 2 项、后端 7 项、全链路验收 1 项；不等于 10 个接口或 10 个插件。C01–C09 的主要代码已在工作区实现，C10 的真实目标逐插件验收仍待进行。下面的完成标准继续作为验收边界。

| 编号 | 归属 | 工作项 | 当前入口 / 范围 | 完成标准 |
|---|---|---|---|---|
| C01 | 后端 | 全插件凭据映射 | 社区常量/注册、企业 collect、目录外与多驱动分支 | 每个入口明确分类、类型、支持认证方式、认证字段与剩余字段 |
| C02 | 后端 | tree 与实际类型绑定 | `collect_object_tree.py`、系统管理 `list_types` | 返回可用实际 key；覆盖首选、备用、自定义占用和缺失状态 |
| C03 | 前端 | 两种认证来源与选择 | `credentialPoolEditor.tsx`、公共 CredentialPicker | 一次性认证/已有凭据切换；存量任务默认选中一次性认证；组织、类型筛选；多候选和编辑回显 |
| C04 | 前端 | 剩余字段与提交格式 | `credentialDescriptors.ts`、各 Task 表单、`useTaskForm.ts`、`formatTaskValues.ts` | 选择已有凭据后额外字段仍可填、可保存；不提交隐藏来源的认证值 |
| C05 | 后端 | 保存引用及旧任务兼容 | `collect_serializer.py`、`collect_credential_pool_service.py`、`collect_service.py`、采集模型 | 无来源和仓库引用的旧任务默认一次性认证，修改时保存来源标记；原凭据/端口保留并继续加密；已有凭据只保存仓库 ID 和剩余参数；区分候选 ID 与仓库 ID |
| C06 | 后端 | 下发时查询凭据 | 采集下发服务、RPC resolve、`BaseNodeParams` 前置构建 | 每次下发读取最新值，带有效身份/组织；校验类型、权限、停用和缺失；覆盖全部候选 |
| C07 | 后端 | key/枚举转换与组装 | 社区 NodeParams、企业 collect 及对应采集器契约 | 逐插件转换字段和值，合并表单参数并验证；进入既有节点秘密注入路径 |
| C08 | 后端 | 辅助接口复用 | Region/项目查询、连接测试、`collect_tool_service.py` 等实际辅助入口 | 支持引用 ID，后端解析并复用相同转换；浏览器不取得仓库秘密 |
| C09 | 后端 | CMDB 引用统计 | CMDB NATS responder 与系统管理引用统计接口 | 新增/修改/删除任务、更换凭据的引用准确；旧手填任务不计为仓库引用。Monitor 消费者属于联调边界，不扩大为本轮 Monitor 改造 |
| C10 | 验收 | 全插件逐项验证 | 118 项入口 + 目录外/协议/OS/驱动分支 | 每项覆盖仓库凭据、key 转换、表单、下发及真实对象/关系；无法执行的项明确记录原因 |

### 7.3 按采集对象分类统计

下面是采集对象目录的 9 个分类，不是凭据管理的 7 个分类；两者通过插件映射关联。

| 采集对象分类 | 社区 | 企业新增 | 合计 |
|---|---:|---:|---:|
| 容器 | 2 | 0 | 2 |
| 虚拟化 | 1 | 11 | 12 |
| 网络 | 2 | 4 | 6 |
| IP 管理 | 1 | 0 | 1 |
| 数据库 | 8 | 21 | 29 |
| 存储 | 3 | 13 | 16 |
| 云平台 | 4 | 2 | 6 |
| 主机管理 | 5 | 3 | 8 |
| 中间件 | 19 | 19 | 38 |
| 总计 | 45 | 73 | 118 |

逐项名录见分类目录与 §5，18 个原占位入口的旧表单映射见 §9；Oracle、network_topo、aliyun 别名、AIX/HP-UX/国产 Linux 合并分支、PostgreSQL/MySQL 的 JOB 分支继续额外覆盖。118 是目录入口数，不代表已完成或可直接执行的测试数量。

## 8. 再次复核补齐的实施规则

这些规则归入原有 C01–C10，不增加新的改造项目。主要代码已接入，实际部署与逐插件验收未完成。

| 事项 | 实施规则 | 对应工作项 |
|---|---|---|
| 认证来源切换 | 一次性认证切到已有凭据并成功保存后，删除旧任务内核心认证值，仅保留仓库 ID 和允许的剩余参数；从已保存的仓库引用切回一次性认证时要求填写认证值，不读取仓库秘密回填，不恢复已删除的旧密码。取消编辑不改持久化数据 | C03/C05 |
| 多候选 | 对原本支持多候选的插件，每条候选独立保存来源，允许两种来源混用；沿用原数量上限、顺序和候选 ID。按来源分别校验，不用原先“所有字典字段必须相同”的判断拒绝混合来源；完整解析后再进入既有执行器，不丢弃后续候选。一个引用解析失败时，本次参数构建失败，不以跳过坏引用的方式静默改变配置 | C03/C05/C06 |
| 秘密继承 | 只有同一候选、同为一次性认证且认证方式兼容时，编辑掩码才能保留原秘密；切换来源或改变认证方式时按新模式校验。现有 `format_update_credential` 会合并旧字典，接入时必须按来源分支处理，防止仓库模式仍存着旧密码 | C05 |
| 剩余认证字段 | 每个插件明确仓库负责字段与表单负责字段；剩余字段若属于秘密，也纳入任务已有加密/掩码/环境变量注入机制。仓库管理的核心字段缺失时拒绝执行，不在表单里暗中补一份同名密码；端口、TLS 和 Region 等由表单负责 | C01/C04/C05/C07 |
| 执行身份与组织 | 保存或更换仓库引用时，由后端记录通过权限校验的绑定操作者身份及当次明确的 current_team；不保存浏览器 token，也不将多组织任务的第一个 team 当作执行组织。自动下发按该身份重新核验当前用户状态、组织权限及凭据权限；身份失效则拒绝解析。普通参数编辑不自动更换绑定身份；改变绑定或组织时重新校验。手工测试使用当前有权操作者的上下文 | C05/C06/C08 |
| 表单失效状态 | 改插件、执行方式、OS、类型或组织后，重新检查所选引用，失配时清空选择并保留仍适用的连接参数；编辑中发现凭据停用、删除或不可见时，保留可定位的引用状态并要求处理，不自动切回一次性认证，不展示不可见凭据的名称或字段 | C02/C03/C04 |
| 无需认证入口 | K8S 当前引导采集、IP 探活等沿用原行为，不强制选择一种凭据；InfluxDB 等可选认证入口继续支持原无认证路径。逐插件测试标明“不适用”的认证项，不能因此省略其采集验证 | C01/C04/C10 |
| 凭据更新边界 | 仓库秘密不复制进任务，也不以持久化秘密快照计算版本；每次真正下发取最新值。候选来源、绑定 ID 或任务内参数发生变化时沿用现有本地版本机制。已有节点配置是否被替换由原下发机制负责；本需求不承诺仓库修改立即影响运行节点 | C05/C06/C07 |

引用统计还需明确一个已有外部依赖：系统管理 `assert_credential_unreferenced` 在 CMDB 或 Monitor 任一计数查询失败时会拒绝删除/转移凭据。CMDB 接入只实现自己的 responder，不伪造 Monitor 的零引用；联调时须有真实的 Monitor 计数响应。该服务不可用时，保留原拒绝行为并记录为外部依赖，不能将未知统计判为无引用。

### 8.1 方案与验收的完成判断

| 范围 | 当前结论 | 完成所需证据 |
|---|---|---|
| 公共接入方案 | 主流程与必要分支已明确，可进入实施 | C01–C09 实施并通过对应存储、权限、转换、前端与下发测试 |
| 社区与企业中契约明确的插件 | 逐入口分类、转换代码与模拟参数回归已在工作区完成 | 各入口在真实环境独立验证两种认证来源、辅助接口、节点参数和实际采集结果 |
| 企业 18 个协议占位入口 | 已按现有配置/旧表单确定映射，补齐页面描述并逐项测试模拟 NodeParams 参数，见 §9 | 逐项实测并修正旧表单、下发及执行器不一致，记录真实结果 |
| 通用摘要脚本及合并平台分支 | 凭据类型可对应不代表业务采集完整 | 核对真实业务输出、根/子对象和关系；单独登记尚未实现或缺目标环境的项 |
| 本次交付状态 | 方案、编辑校验与 CMDB 主要接线已在工作区完成；实际目标全量验收未完成 | 全量验收逐项记录通过/失败/阻塞/不适用；无结果的项不得视为通过 |

因此不新增旧端口迁移、自动轮换推送等要求，也不重复要求补已交付的四类定义。18 个原占位入口同样按旧表单接入；已知差异作为开发及逐插件测试时的修正项，不再作为方案前置阻塞。


## 9. 按现有配置和旧采集表单确定的 18 项映射

用户已明确：以之前配置采集页面的字段为依据推进；如有错误，在后续逐插件测试中一并修正。这里区分“表单/字段依据存在”与“执行器已完成真实采集”，不再因后者未完成而搁置前者。

### 9.1 查到的实际依据

- 当前 [credentialDescriptors.ts](../web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialDescriptors.ts) 中 ZStack 已声明 PlatformApiTask，字段 username/password/port/verify_tls，默认端口 8080。
- 历史提交 `b1a3fd34c`（凭据描述改造 `cae36df3f` 的父提交）的专业采集 page.tsx 明确按 task_type 分派：cloud→CloudTask，protocol→SQLTask，snmp→SNMPTask，middleware→HostTask。它们分别有 accessKey/accessSecret/regions、user/password/port、SNMP 字段、username/password/port。
- 18 项的 task_type 来自 [企业对象定义](../enterprise/server/apps/cmdb_enterprise/collect/new_collect_object_definitions.py)；各插件 plugin.yml 有连接预检配置；[GenericProtocolNodeParamsMixin](../enterprise/server/apps/cmdb_enterprise/collect/remaining_node_params.py) 有通用凭据参数构建。
- 原先其余 17 项未声明 credential descriptor，现已按旧表单补齐并在前端定向用例中逐个命中；仍需在浏览器和真实目标上逐项核对原表单及执行器的差异。

### 9.2 逐项接入表

| 编号 | 插件 | 表单依据 | 本次绑定分类/类型 | 字段转换规则 | 表单剩余参数 / 配置对照 |
|---|---|---|---|---|---|
| L01 | ZStack `zstack` | 当前 PlatformApiTask：username/password；旧 CloudTask 作为别名兼容 | cloud/platform_api | 仓库 username/password → 当前同名字段；旧 accessKey/accessSecret 归一为账户字段 | 目标地址、port（当前默认 8080）、verify_tls；历史 regions 保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/zstack/plugin.yml)端口：8080 |
| L02 | F5 `f5` | 旧 task_type=snmp → SNMPTask | network/snmp | version v2c→v2；security_level→level；auth_protocol→integrity；auth_password→authkey；priv_protocol→privacy；priv_password→privkey；算法转小写 | snmp_port（旧表单默认 161）、目标；保留已有拓扑选项；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/f5/plugin.yml)预检已改 SNMP/161，自定义端口保留；真实采集器仍待实现 |
| L03 | 安全设备 `security_device` | 旧 task_type=snmp → SNMPTask | network/snmp | version v2c→v2；security_level→level；auth_protocol→integrity；auth_password→authkey；priv_protocol→privacy；priv_password→privkey；算法转小写 | snmp_port（旧表单默认 161）、目标；保留已有拓扑选项；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/security_device/plugin.yml)端口：161 |
| L04 | 磁带库 `tape_library` | 旧 task_type=snmp → SNMPTask | network/snmp | version v2c→v2；security_level→level；auth_protocol→integrity；auth_password→authkey；priv_protocol→privacy；priv_password→privkey；算法转小写 | snmp_port（旧表单默认 161）、目标；保留已有拓扑选项；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/tape_library/plugin.yml)端口：161 |
| L05 | Couchbase `couchbase` | 旧 task_type=protocol → SQLTask：user/password/port | database/sql | username→user；password 保持；Generic NodeParams 接受 user 并派生 username | port、目标；既有库名等专用字段按原表单保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/couchbase/plugin.yml)端口：8091 |
| L06 | SAP HANA `sap_hana` | 旧 task_type=protocol → SQLTask：user/password/port | database/sql | username→user；password 保持；Generic NodeParams 接受 user 并派生 username | port、目标；既有库名等专用字段按原表单保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/sap_hana/plugin.yml)端口：未声明 |
| L07 | InterSystems IRIS `iris` | 旧 task_type=protocol → SQLTask：user/password/port | database/sql | username→user；password 保持；Generic NodeParams 接受 user 并派生 username | port、目标；既有库名等专用字段按原表单保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/iris/plugin.yml)端口：未声明 |
| L08 | TongRDS `tongrds` | 旧 task_type=protocol → SQLTask：user/password/port | database/sql | username→user；password 保持；Generic NodeParams 接受 user 并派生 username | port、目标；既有库名等专用字段按原表单保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/tongrds/plugin.yml)端口：6379 |
| L09 | TDSQL `tdsql` | 旧 task_type=protocol → SQLTask：user/password/port | database/sql | username→user；password 保持；Generic NodeParams 接受 user 并派生 username | port、目标；既有库名等专用字段按原表单保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/tdsql/plugin.yml)端口：3306 |
| L10 | IBM Storwize `ibm_storwize` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/ibm_storwize/plugin.yml)端口：443 |
| L11 | IBM DS `ibm_ds` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/ibm_ds/plugin.yml)端口：443 |
| L12 | EMC Symmetrix `emc_symmetrix` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/emc_symmetrix/plugin.yml)端口：443 |
| L13 | 宏杉存储 `macrosan` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/macrosan/plugin.yml)端口：443 |
| L14 | NetApp Cluster `netapp_cluster` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/netapp_cluster/plugin.yml)端口：443 |
| L15 | Oracle ZFS `oraclezfs` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/oraclezfs/plugin.yml)端口：215 |
| L16 | Infinidat `infinidat` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/infinidat/plugin.yml)端口：443 |
| L17 | XSKY `xsky` | 旧 task_type=cloud → CloudTask：accessKey/accessSecret/regions | cloud/cloud（按旧 AK/SK 表单基线） | 仓库 access_key/secret_key 与旧 accessKey/accessSecret 对应；送 Generic NodeParams 时统一为其接受的 access_key/secret_key | regions、目标；已存 port/api_url 等非秘密参数保留；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/xsky/plugin.yml)端口：8051 |
| L18 | Ambari `ambari` | 旧 task_type=middleware → HostTask：username/password/port | host/ssh（按旧主机表单基线） | username/password 同名；SSH 密钥方式的 private_key/passphrase 经秘密环境变量引用下发；auth_method 一并下发；驱动仍为 protocol | port（旧主机表单默认 22）、目标；[插件配置](../enterprise/agents/stargazer/enterprise/plugins/inputs/ambari/plugin.yml)预检已改远程通道/22，自定义端口保留；真实采集器仍待实现 |

上述是按用户指定基线确定的接入映射，不是对厂商真实认证协议的重新认定。分类统计为：当前平台账户 1 项、旧 SNMP 表单 3 项、旧 SQL 表单 5 项、旧 CloudTask 8 项、旧 HostTask 1 项，共 18 项；没有新增凭据类型。

### 9.3 已发现的差异随实施/测试修正

| 差异 | 本次处理 |
|---|---|
| 8 个存储入口旧页面实际是通用 AK/SK 字段，而非独立平台账户表单 | 先按旧字段绑定 cloud/cloud，旧手填数据仍为一次性认证；对象在存储分类不等于凭据也必须查询 storage。若后续确认实际需要账户密码，再共同改为 storage/platform_api 并调整字段映射，不悄悄把旧 AK/SK 当成已证实的用户名密码 |
| Ambari 的旧表单是 HostTask，但对象驱动为 protocol、原 manifest 为 TLS 8080 | 本阶段预检按旧表单改远程通道/22，host/ssh 的 password/key 两种字段均可下发；驱动保持 protocol，真实采集器仍是占位，不能宣称已在 SSH 执行。后续目标验证若要求 API 登录，再同步改表单、类型绑定与清单 |
| F5 的旧表单和 tree 指向 SNMP，原 manifest 却是 TLS 443 | 本阶段预检按旧 SNMP 表单改 SNMP/161，自定义端口保留；SNMP v2/v3 下发字段已定向测试。真实采集器仍是占位，实际协议待目标验收 |
| Generic NodeParams 未完整下发 SNMP V3 字段，且只给 password 做了环境变量引用 | C07 必须补齐 V3 的版本、安全等级、算法和秘密字段；community/authkey/privkey、AK/SK 等沿用项目秘密注入规范，不能因旧通用透传是明文就照抄 |
| 旧 CloudTask 使用驼峰 AK/SK，Generic NodeParams 仅透传 snake_case AK/SK | 后端兼容旧输入、统一生成执行器接受的 key；已有凭据也走同一适配。认证类型匹配不能代替 key 转换 |
| SQL 旧通用端口与部分 manifest 的默认端口不同，SAP HANA/IRIS 未在 manifest 指定端口 | 存量任务保留原端口；新表单保留原可编辑端口行为，具体默认值按插件逐项测试纠正，不新增凭据字段 |

当前计划可以覆盖全部 118 个入口及额外分支。执行器占位、旧表单字段/默认值错误和无真实目标环境仍需在测试结果中明确记录；“可以按旧表单接入”不等于这些测试已经通过。
