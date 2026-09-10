# CMDB 特征库端口指纹与统一数据库扫描

Status: implemented

## Problem Statement

扫描任务今天要按 MySQL / PostgreSQL / MSSQL 分别勾选、分别准备账号，管理员得先猜网段里是哪种库。非默认端口更只能写在凭据表单里，和特征库无关。SOID 已经能教网络设备指纹，端口侧没有对等的登记处，也无法用「先看端口、再用同一套库账号去试」把三种库收成一次扫描。

## Solution

把特征库下沉一层：一页两个 Tab，网络设备 SOID 与端口指纹并列。端口指纹描述「这个 TCP 端口可能是哪种模型」；一种数据库可以有多条端口，同一端口也可以指向多种类型。扫描任务只勾选「数据库」，凭据只留用户名/密码池；探测哪些端口、试哪种插件，完全读特征库。登录成功仍建成 `mysql` / `postgresql` / `mssql` CI。端口有响应但账号全失败则留下未匹配行：可以给该类型再登记别的端口（不影响本次）。生成采集和推监控仍只给真正登录成功的命中。InfluxDB 继续单独勾选，不走端口预判。

## User Stories

1. As a CMDB 管理员, I want 在特征库用 Tab 同时管理 SOID 和端口指纹, so that 网络指纹和端口指纹在同一个入口，而不必猜该去哪个子页。
2. As a CMDB 管理员, I want 为同一种数据库登记多个端口、并为同一端口登记多种类型, so that 非默认端口和端口复用都能教给扫描。
3. As a CMDB 管理员, I want 扫描任务只勾「数据库」并填一套用户名/密码, so that 不必先猜网段里是 MySQL 还是 PostgreSQL。
4. As a CMDB 管理员, I want 扫描只探特征库里三种数据库的端口，中间件指纹即使已登记也不连, so that 这一轮能把库扫完，特征库仍能先放下一次的中间件类型。
5. As a CMDB 管理员, I want 同一 IP 上多种数据库类型都登录成功时留下多条命中和多个 CI, so that 一台机器上的多个库不会互相覆盖。
6. As a CMDB 管理员, I want 端口开着但账号全失败时在未匹配里按预判类型看到 IP 和端口, so that 我知道这里有库，只是还没登进去。
7. As a CMDB 管理员, I want 在数据库未匹配组头给该类型新增端口指纹, so that 下次扫描会探到非默认端口，而不改掉已有映射、也不认领本次失败行。
8. As a CMDB 管理员, I want 打开旧的三族 SQL 扫描任务时自动看成「数据库」并合并账号池, so that 已保存的任务还能用。

## Implementation Decisions

- 新增端口指纹实体，与 OID 映射表并列，不把端口塞进 SOID 行。字段：端口、协议（本轮固定 TCP）、目标类型（已有 CMDB 模型 ID）、是否内置。唯一约束是 `(端口, 目标类型)`，端口本身不唯一。内置三条：`3306 → mysql`、`5432 → postgresql`、`1433 → mssql`。初始化对齐 OID 目录：内置可随种子更新，用户行不覆盖、不可删除内置行。
- 目标类型下拉使用已有库 / 中间件模型 ID（至少三种数据库，以及专业采集里已有的中间件与其它库模型）。扫描「数据库」的白名单固定为 `mysql`、`postgresql`、`mssql`；白名单以外的指纹只展示、不探、不建扫描命中。InfluxDB 即使有人登记端口，本轮 Influx 扫描族也不读这张表。
- 菜单「SOID特征库」改名为「特征库」，仍进入现有特征库路由。页面两个 Tab：网络设备 SOID（现表不动）、端口指纹（端口、协议、类型、内置、删除用户行）。不启用空的扫描特征占位页。采集工具菜单不动。编辑不是主路径：改类型则删用户行再新增。
- 未匹配组头「添加指纹」打开新增表单，类型预填为该组，端口空白。保存只写端口指纹，不回写本次命中、不重跑本枪。仅带查询参数打开特征库时切到端口 Tab 并可按类型筛选，不自动弹出新增，对齐 SOID 的 `oid` 只检索不弹窗。
- 扫描任务勾选变为网络 / 主机 / 物理机 / `database` / `influxdb`。`database` 凭据形状为 SQL 用户名/密码池，不含端口和库类型。表单说明探测端口来自特征库。Influx 仍用自己的 token/URL 池。
- 任务上 `families` 存 `database`；凭据挂在 `credentials.database`。加密按 SQL 密码字段处理（与现有 mysql 密码字段集合一致），不能把 `database` 当成采集模型去查插件。读取或保存时若仍看到 `mysql` / `postgresql` / `mssql`，合并成 `database`：账号按条目保留，同一用户名不同密码视为不同钥匙。
- 触发时勾了 `database` 并不建名为 `database` 的族执行。按特征库白名单拆最多三枪，`model_id` 仍为 `mysql` / `postgresql` / `mssql`，每枪端口只取该类型已登记端口，同一套账号复制给三枪。某类型没有端口则跳过该枪。特征库当时没有任何数据库端口时，其它已勾选族照常打枪，并提示没有可探数据库端口。指纹变更只影响下一次执行。
- 不改 Stargazer 调度与 `collect_info` 契约。进度分母、接纳、收口墙钟仍按现有扫描规格。登录成功的写 CI、自动推监控、自动生成采集仍只处理 `success` 且带命中凭据的行；未匹配不会被自动建成 CI。
- 库 CI 身份保持扫描纳管已锁口径：`(模型, IP, 端口)`。同一端口多种数据库类型都登录成功，则两条命中、两个 CI。一种成功一种失败各算各的。
- 「失败不进清单」增加有界例外，且只作用于上述三枪：凭据结果为 `failed` 且 `error_code` 属于已有鉴权失败集合时，对该 `(族执行, IP, 端口)` upsert **一条** `status=failed`、`credential_id` 为空的命中。`unreachable`、超时、以及没有鉴权 `error_code` 的普通 `failed` 只计进度。随后若出现 `success`，删除该失败占位，只保留成功行。大网段上未监听的端口不得因此铺满清单。
- `unmatch_reason` 仍由序列化计算、不新增命中字段。在命中交互规格的 `unknown_soid` / `empty_soid` 之外增加 `credential_failed`：三库族、`cmdb_model_id` 为空、且为上述鉴权失败占位行。其它族口径不变。
- 未匹配仍是一个顶层 Tab，执行未终态时不拆出。终态后未匹配内分两块：网络按 SOID 分组（命中交互规格不变）；数据库按预判类型（族 `model_id`）分组，子行是 IP+端口。数据库组头只有添加指纹。数据库未匹配不建 CI、不转入已匹配。
- 「生成采集」「推送监控」只作用于登录成功的命中（已匹配 Tab，以及网络未匹配 Path 2）。数据库未匹配勾选时这两个按钮禁用；接口在缺少命中凭据时拒绝。任务级自动推 / 自动生成同样忽略 `credential_failed` 行。
- 混选网络未匹配与数据库未匹配时：网络仍选手选四类设备类型再推或采；数据库未匹配行跳过，不建 CI。
- 端口指纹走 CMDB 内部 API，权限对齐特征库新增/删除，不经 OpenAPI 网关对外暴露。
- 登录成功后的生成采集 `model_id` 仍是 `mysql` / `postgresql` / `mssql`，不是 `database`，以便沿用现有采集插件与监控插件名。

## Testing Decisions

只测外部行为：种子与唯一约束、任务族折叠、触发拆枪与端口过滤、鉴权失败占位与成功替换、未匹配原因、失败行推/采被拒。不测抽屉像素、Ant Design 内部状态、Stargazer 内部调度。不启真实 Stargazer。

测试缝（沿用扫描与 OID 现有缝）：

- 端口指纹服务 / API：内置三条、用户新增、`(端口, 类型)` 冲突、拒绝删除内置、中间件类型可保存。
- 扫描任务读写：旧三族合并为 `database`；`database` 凭据按 SQL 密码字段加密脱敏。
- 扫描触发（mock `collect_info`）：`database` 拆出的族 `model_id` 与端口列表；无数据库端口则跳过 SQL 枪；中间件端口不出现在请求里；同一套账号复制给各枪。
- 凭据结果服务：鉴权失败 upsert 一条空凭据命中；成功删除占位；`unreachable` 无清单行。
- 命中序列化：`unmatch_reason=credential_failed`。
- 扫描服务层：生成采集 / 推监控在无 `credential_id` 时拒绝。
- 扫描 API：新动作的成功摘要与非法选择，沿用现有 ViewSet + `APIRequestFactory`。
- 前端以类型检查覆盖 Tab、任务勾选与未匹配分组；不强制为抽屉补 Playwright。

Prior art：`test_init_oid_command.py`、`test_scan_identity.py`、`test_scan_classify_service.py`、`test_scan_views.py`、`test_scan_credential_event_nats.py`、`test_scan_trigger_service.py`。

## Out of Scope

- 把扫描合成真正的 `database` 族执行，或改 Stargazer 做独立 TCP 预检。
- 中间件 / Redis / Oracle 等登录扫描与对应凭据池。
- InfluxDB 改走端口指纹预判。
- 端口指纹与 SOID 合成一张通用特征表。
- 数据库未匹配上生成采集、推监控、按预判类型建 CI，或为失败行再填一套账号。
- 同一端口多种类型登录成功时做冲突消解（只留一个）。
- 改采集「未知当 switch」、凭据中心、Redfish、云 / K8s / IPAM 扫描族。
- OpenAPI 网关暴露端口指纹或扫描新动作。

## Further Notes

讨论对齐见 grilling；实现以本文为准。扫描纳管主规格仍是 `cmdb-scan-discovery`。命中抽屉与网络未匹配两条路仍是 `cmdb-scan-hit-interaction`；本文只把 `unmatch_reason` 增补 `credential_failed`，并在未匹配 Tab 内增加数据库分组。入口不要占用空的 `featureLibrary/scanFeature` 页。
