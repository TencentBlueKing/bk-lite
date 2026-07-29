# CMDB 配置采集凭据协议指引

Status: done

快速了解当前实现链路与模块设计，请先阅读
[`docs/cmdb-collection-credential-guidance.md`](../../../docs/cmdb-collection-credential-guidance.md)。

## Problem Statement

专业采集任务的表单统一把连接信息称为“凭据”，但没有说明采集器实际使用的连接协议。用户看到“账户、密码、端口”时，无法判断应填写目标主机的 SSH 账户、数据库账户、设备管理账户，还是云厂商 API 密钥。

当前前端进一步把 `task_type` 当作表单类型：`host/db/middleware` 进入 SSH 表单，`protocol` 进入 SQL 表单，`cloud` 进入统一 AK/SK 表单。`task_type` 只是任务执行分类，并不等于真实协议，因此已经产生可验证的错误：

- InfluxDB 实际通过 HTTP(S) API 采集，却显示 SQL 用户、密码和 3306 端口；
- FusionInsight 实际通过 HTTPS API 和 HTTP Basic 认证，却显示云 AK/SK；
- OceanStor 实际通过 DeviceManager HTTPS REST 和设备账户认证，却显示云 AK/SK；
- 华为云 SDK 还需要 Project ID，现有云表单没有表达；
- SSH、数据库直连和 SNMP 等不同凭据在同一套通用标签下缺少来源说明。

只在“凭据”旁增加一段通用文案不能解决问题：提示必须来自插件的真实连接契约；复杂协议的表单字段也必须与采集器实际入参一致。

## Solution

保留现有“凭据”区块和多凭据数据结构，不拆分“连接设置”和“认证信息”。用户点击“凭据”标题旁现有的 `?` 图标后，打开 Ant Design Popover，查看当前插件的连接协议、凭据类型、填写说明和默认端口。原有“最多配置 3 个凭据，系统按顺序试探”的说明并入 Popover 的“多凭据策略”区域。

简单对象由采集对象目录提供语义化凭据元数据，前端按协议模板渲染提示；复杂对象由前端按 `model_id` 提供专用表单和专用说明，不建立通用动态表单引擎。插件目录没有元数据时显示明确的兜底说明，不根据 `task_type` 猜测协议。

同时修正已确认的表单与采集契约缺口，使提示内容和实际采集行为一致，首期覆盖 InfluxDB、SNMP、主流公有云、FusionInsight 和 OceanStor。

## User Stories

1. As a 配置采集用户, I want to know the real connection protocol before entering credentials, so that I can choose the correct account.
2. As a 配置采集用户, I want protocol-specific labels and defaults, so that I do not submit SSH credentials to an HTTP API or database credentials to a device API.
3. As an InfluxDB administrator, I want Operator Token to be optional and its risk explicit, so that basic collection does not require an instance-wide administrative token.
4. As a network administrator, I want one SNMP explanation covering V2C and V3 field dependencies, so that I can configure complex V3 credentials without scattered help icons.
5. As a cloud/platform administrator, I want provider-specific credential names and required fields, so that the form matches the provider API contract.
6. As a plugin maintainer, I want simple plugins to declare credential semantics independently from execution classification, so that new plugins do not inherit an incorrect form from `task_type`.

## Implementation Decisions

### 1. `task_type` 与连接协议分离

- `task_type` 继续表示任务调度和执行分类，不作为用户可见协议，也不作为凭据表单的最终事实来源。
- 简单插件在采集对象目录中声明：

| 字段 | 语义 |
| --- | --- |
| `credential_protocol` | 用户可理解的协议标识，如 `ssh`、`mysql`、`postgresql`、`sql_server` |
| `credential_kind` | 凭据来源，如 `host_account`、`database_account` |
| `credential_default_port` | 插件默认端口；没有固定端口时省略 |
| `credential_tip_key` | 可选的插件级说明覆盖键 |

- 这些字段是展示与表单选择的语义元数据，不承载密钥，不替代 `encrypted_fields`，也不改变后端任务存储结构。
- 协议名称面向用户，使用 “SQL Server”“HTTP API”“SSH”等名称，不暴露 `pyodbc`、`requests`、SDK 内部类等实现细节。
- 不增加运行时注册机制。缺少元数据且没有静态描述时，不得从 `task_type` 推断并伪装成已知协议；创建表单明确提示插件尚未声明凭据协议，并阻止使用错误认证方式创建任务。

### 2. 唯一帮助入口

- 只保留“凭据”标题旁现有 `?` 作为入口；不在插件卡片增加协议徽标，不在表单顶部增加常驻 Alert，不给每个字段重复增加 `?`。
- 交互使用 `Popover` 的 click trigger。点击外部关闭；图标可获得键盘焦点，可使用 Enter/Space 打开并用 Esc 或失焦关闭。
- 简单协议使用固定四行：
  1. 连接协议
  2. 凭据类型
  3. 填写说明
  4. 默认端口
- 原 `credentialPoolTip` 作为“多凭据策略”追加在四行之后；不支持多凭据或只允许一个凭据的表单不展示该段。
- 中英文文案进入 `web/src/app/cmdb/locales/zh.json` 和 `en.json`，不得把面向用户的完整说明散落硬编码在 JSX 中。

### 3. 帮助定义的模块边界

- `CredentialDescriptor` 不使用运行时注册表。所有稳定描述集中写在前端独立文件 `credentialDescriptors.ts` 的静态常量中，按简单协议、复杂对象 `model_id` 和 PC 操作系统类型组织。
- 建立一个纯函数凭据帮助解析模块，输入为 `modelItem`，从静态描述解析并输出统一的 `CredentialHelpDefinition`。
- `CredentialPoolEditor` 只负责展示传入的帮助定义和凭据池策略，不识别 `model_id`，不维护插件映射。
- 简单协议模板按 `credential_protocol` 解析；复杂对象由专用任务组件使用其静态 `model_id` 描述，不由后端 Schema 动态生成帮助或表单。
- 当前页面实际使用的是专业采集目录下的本地 `credentialPoolEditor.tsx`；Storybook 使用另一个重复实现。实施时把共享编辑器收敛为一个真实组件，让业务页面与 Storybook 引用同一实现，避免帮助内容和交互再次漂移。

### 4. 简单协议首期模板

| 协议 | 凭据类型 | 填写说明 | 默认端口 |
| --- | --- | --- | --- |
| SSH | 目标主机操作系统账户 | 填写可通过 SSH 登录目标主机并执行只读采集命令的账户 | 22 |
| MySQL | MySQL 数据库账户 | 填写可连接目标实例并读取配置/元数据的数据库账户 | 3306 |
| PostgreSQL | PostgreSQL 数据库账户 | 填写可连接目标实例并读取配置/元数据的数据库账户 | 5432 |
| SQL Server | SQL Server 数据库账户 | 填写可连接目标实例并读取配置/元数据的数据库账户；数据库默认 `master` | 1433 |

- 主机、中间件和以 JOB 执行的数据库插件仍可共用 SSH 表单，但提示必须明确这是“目标主机操作系统账户”，不能写成应用账户。
- 插件覆盖可以调整填写说明和端口，不能改变采集器真实协议。

### 5. 复杂对象策略

- SNMP、InfluxDB、IPMI、WinRM、vSphere、网络配置文件、云平台等由专用任务组件维护帮助定义和字段联动。
- 复杂对象允许不使用固定四行，但仍通过同一个“凭据 `?`”Popover 展示。
- 不构建由后端 JSON Schema 驱动的通用动态凭据表单。复杂结构可在前端按 `model_id` 写死；字段、校验、回填和提交转换必须放在该对象的专用配置模块中。

### 6. SNMP

SNMP Popover 一次说明全部版本和字段关系：

- V2/V2C：填写团体字和端口，默认 UDP 161；
- V3 `authNoPriv`：填写用户名、认证密码和哈希算法；
- V3 `authPriv`：在 `authNoPriv` 基础上继续填写加密算法和加密密钥；
- 表单继续根据版本和安全级别动态显示字段，不增加字段级帮助图标。

### 7. InfluxDB

InfluxDB 使用独立表单，不再进入 SQL 通用表单：

- 连接协议为 HTTP 或 HTTPS，默认 HTTP；
- 默认端口 8086；
- 不显示账户字段；
- 提供“校验证书”开关，默认开启；关闭时显示明确风险提示；
- `Operator Token` 为可选字段。未填写时只采集 `/health` 或 `/ping` 可获得的版本、地址和协议等基础信息；填写后才访问 `/api/v2/config` 采集完整运行配置；
- Popover 必须说明 Operator Token 是 InfluxDB 2.x 实例级高权限凭据，只在用户确实需要完整配置时使用；
- InfluxDB 1.x 只承诺基础识别，不伪造配置字段。

当用户提供 Token 后：

- `/api/v2/config` 返回 401/403 或其他权限错误时，不得静默降级为成功；
- 已获得的基础信息可以保留，但任务必须显示“部分成功”及可定位原因；
- 未提供 Token 的基础采集是正常成功，不得显示权限告警。

实现必须补齐 CMDB `NodeParams` 下发、Stargazer 参数读取和真实链路测试。TLS 校验开关必须真实传入 `requests`，不能只存在于前端。

### 8. 云与平台类型

公有云和私有平台不再共享一套固定 AK/SK 语义：

| 对象 | 实际连接与凭据 |
| --- | --- |
| 阿里云 | 云 SDK；AccessKey ID、AccessKey Secret、Region |
| 腾讯云 | 云 SDK；SecretId、SecretKey、Region |
| 华为云 | 云 SDK；AK、SK、Project ID、Region |
| FusionInsight | HTTPS API；平台用户名、密码、平台地址 |
| OceanStor | DeviceManager HTTPS REST；设备管理员用户名、密码、端口，默认 8088 |

- 阿里云、腾讯云和华为云可以复用同一个云表单框架，但字段标签、必填项、提交映射和帮助定义按 `model_id` 配置。
- FusionInsight 与 OceanStor 使用专用平台表单或同一“HTTPS 平台账户”表单模块的两个显式配置；不得通过 `task_type=cloud` 进入 AK/SK 表单。
- 所有云/API 提示建议使用只读或最小权限凭据；只有 InfluxDB Operator Token 这类已知高权限例外必须突出说明风险。
- 企业扩展插件必须提供自身连接契约；前端不得因其 `task_type=cloud` 自动认定为 AK/SK。
- 修复 FusionInsight 当前错误的 AK/SK NodeParams 映射、补齐 OceanStor NodeParams，并让华为云 Project ID 完整贯通表单、Region 查询和采集下发。

### 9. 凭据安全、回填与兼容

- 凭据仍使用现有 `credential`/凭据池结构、加密字段和 `******` 回填语义，不新增数据库表或 migration。
- 新增密钥字段必须加入对应 `encrypted_fields`，服务端响应继续脱敏，日志和任务摘要不得记录 Token、密码、AK/SK 或认证请求头。
- 编辑任务时，掩码表示“未修改”；复制任务不得复制密钥明文，仍要求用户重新填写。
- InfluxDB Operator Token 允许为空；其他对象的必填规则由各自真实契约决定。
- 现有可正常采集的 SSH、MySQL、PostgreSQL、SQL Server 和 SNMP 任务保持数据兼容。

## Non-goals

- 不重做整个专业采集页面；
- 不把连接地址、端口、TLS 和认证信息拆成两个顶层区块；
- 不引入通用凭据 Schema/Form Builder；
- 不在本变更中设计凭据中心、密钥轮换或跨任务凭据复用；
- 不自动探测协议，不允许用户把插件切换到其不支持的协议；
- 不承诺修复所有企业扩展插件，只为其定义元数据和兜底契约。

## Acceptance Criteria

- 任一支持的简单插件点击“凭据 `?`”都能看到真实协议、凭据类型、填写说明和默认端口；
- 帮助使用 click Popover，键盘可访问，中英文完整，原多凭据策略说明未丢失；
- `task_type` 不再被当作用户可见协议，缺少协议元数据与静态描述时明确阻止错误表单创建；
- SSH/JOB 插件明确要求主机操作系统账户，数据库直连插件明确要求数据库账户；
- SNMP V2C/V3 全部分支在一个 Popover 中说明，动态表单行为不回退；
- InfluxDB 表单只显示 HTTP(S)、8086、证书校验和可选 Operator Token；无 Token 可成功基础采集，有无效 Token 时为部分成功且原因可见；
- 阿里云、腾讯云、华为云显示各自凭据名称，华为云 Project ID 可保存、回填并下发；
- FusionInsight 和 OceanStor 不再显示 AK/SK，实际 NodeParams 与采集器入参一致；
- 新建、编辑、复制任务的掩码和密钥保护行为保持正确；
- 业务页面和 Storybook 使用同一个凭据编辑器实现；
- 后端目录契约测试、NodeParams 测试、Stargazer 采集器测试、前端交互测试、类型检查和 Storybook 构建通过。
