# CMDB 扫描中间件族（SSH / Agent）

Status: ready

## Problem Statement

扫描已经能按网段发现网络设备、主机、物理机和三类 SQL 库，但中间件还只能靠专业采集、对着已知对象跑 JOB 脚本。管理员想在同一张扫描任务里勾上中间件，用现有发现脚本把进程找出来写进 CMDB。CMDB 中间件采集是 SSH 或 Agent 在机器上 `ps` / 读配置；监控中间件却是 stub_status、Tomcat Manager、Exporter 这类 URL。两边凭据不是同一套，扫描不能假装填了 SSH 就能建监控采集。

## Solution

扫描任务新增一个「中间件」族，界面上只勾一次，运行时拆成现有 JOB 插件。发现脚本不新写，复用 Stargazer 里主机 / 中间件采集同一套 `*_info`。凭据与专业采集对齐：留空走节点管理 Agent 本地执行，填写则 SSH 远程执行。扫描后写入中间件 CI、按同通道生成 CMDB 采集任务。监控这一期只到「已发现、未建采」，不自动创建 Telegraf / Exporter。

## User Stories

1. As a CMDB 管理员, I want 在扫描任务上勾选「中间件」而不再为每种中间件单独填凭据, so that 一次扫描能发现网段里的 Nginx / Tomcat 等实例。
2. As a CMDB 管理员, I want 主机和中间件凭据可留空, so that 已纳管 Agent 的机器不填 SSH 也能发现；填了 SSH 则对未纳管机器远程执行同一份脚本。
3. As a CMDB 管理员, I want 同时勾主机和中间件时只维护一份 SSH（或都走 Agent）, so that 不必为中间件再抄一套账号。
4. As a CMDB 管理员, I want 清单按「一台机器上的每个监听端口」落行, so that 同一主机上的多个 Nginx / Tomcat 不会被压成一行。
5. As a CMDB 管理员, I want 把命中写入 CMDB 并生成持续采集任务, so that 发现结果能进资产台账，且后续刷新仍走 SSH 或 Agent 同一条通道。
6. As a CMDB 管理员, I want 中间件命中不能用扫描凭据推监控, so that 不会把 SSH 或 Agent 误当成 stub_status / Manager / Exporter。
7. As a CMDB 管理员, I want 表单和清单上看到 Agent / SSH 提示, so that 我知道空凭据扫不到没装 Agent 的地址，也知道监控还要二次补齐。

## Implementation Decisions

### 族与类型

- 任务 `families` 增加 `middleware`，与网络 / 主机 / 物理机 / `database` / InfluxDB 并列。保存仍存这一份族名，不把 nginx 等写进 `families`。
- 第一期运行时拆成 7 个 JOB 类型：`nginx`、`tomcat`、`kafka`、`zookeeper`、`rabbitmq`、`consul`、`etcd`。界面不做类型子勾选。触发时不一次打满 7 枪，由扫描工作队列按 IP 切批、同时只飞一批（见 `specs/changes/cmdb-scan-work-queue/spec.md`）。
- `driver_type` 为 job，插件名仍是各模型现有 `nginx_info` 等。扫描外壳（IP 段、凭据池、凭据结果 subject）与现有扫描一致，不改发现脚本，不新增统一中间件扫描器。
- 端口特征库里即使已有 redis 等中间件端口，发现本体仍是 JOB 脚本，不按数据库那样做协议登录。工作队列可用常见监听端口做 TCP 过滤，探测全空则不过滤。
- Redis / Mongo / ES 仍挂在采集树数据库下，不进本族。Apache / MinIO / IIS 等 Beta 不进。

### 凭据：空则 Agent，填写则 SSH

- 网络 / 数据库 / InfluxDB 仍至少一把凭据。主机、中间件允许空池。
- 不增加「Agent / 无 Agent」单选。选择方式与专业采集相同：不填凭据 = Agent；填写用户名/密码/密钥 = SSH。
- 同时勾主机和中间件：主机有 SSH 则中间件复用该池，表单不再出第二份 SSH；两者都空则都走 Agent。
- 凭据存在 `credentials.middleware` 一份，不按 nginx / tomcat 分存。加密字段与主机 SSH 相同。
- 空池触发时按一把占位凭据接纳（与 Stargazer 空池变成单条空凭据再补 `credential-id` 的行为对齐），不得 `ADMIT_FAILED`。
- 云区域：勾了主机仍必填。只勾中间件且空凭据（Agent）也必填，因为节点按 IP + 云区域匹配。只勾中间件且填了 SSH 时云区域仍可选。
- Agent 仍对任务网段逐 IP 询问节点管理：有 Agent 则 `local.execute`；没有则只计进度、不进清单。不改成「只扫已纳管节点列表」。没装 Agent 的地址空凭据扫不到。

### 提示文案（中英都要有）

- 主机 / 中间件凭据区：`凭据可不填；留空时走节点管理 Agent 在目标机本地执行发现脚本。填写后走 SSH 远程执行。用户名和密码均可为空。` 英文对齐现有 `Collection.hostCredentialOptionalTip`。
- 只勾中间件且凭据为空时，云区域旁：`Agent 模式按 IP + 云区域匹配已纳管节点，未安装 Agent 的地址不会出现在清单中。`
- 清单凭据列：SSH 显示账号标签；Agent 显示 `Agent`。
- 中间件「推监控」禁用：`中间件监控需要 URL / Exporter 等凭据，扫描阶段不自动创建采集。`
- 主机族展示名不再叫「主机 SSH」。

### 命中与收口

- 凭据回传仍按主机计进度。JOB 成功时通道端口常常是 22，不能当成中间件业务端口。
- 收口后按该 family_run 的现有 mapping 拉指标，按 `listen_port`（或脚本等价字段）拆成多条 success 命中。唯一键：`family_run（模型）+ host + listen_port + credential_id`。
- snapshot 写入 inst_name、ip、port、version、安装/配置/日志路径等该模型已有字段。`cmdb_model_id` 即 nginx / tomcat 等。
- **禁止把 VictoriaMetrics 空结果当成「没有中间件」去删 JOB success 命中。** 凭据回传成功先于 VM 落盘；实测 nginx/consul 脚本已成功、稍后 `nginx_info_gauge` / `consul_info_gauge` 可读。空指标时必须保留命中，通道口 22 改成该类型默认监听口；有指标再按 listen_port 拆行。只有 JOB 失败 / 不可达才不进清单。收口不等死固定窗口：先落命中并结束任务，路径字段由后续补齐写入 snapshot。
- 失败 / 不可达 / 无 Agent：只计进度。中间件不做数据库那种鉴权失败未匹配，也没有 SOID 分类。

### 写 CI 与生成采集

- 写 CI 只信 snapshot。中间件身份为（模型, IP, 端口）。允许新增。
- `run host` 仅当图上已有同 IP 主机时创建；只扫中间件时不因此新建主机。
- 生成采集按扫描通道：SSH 命中带上命中那份 SSH；Agent 命中生成空凭据任务，后续刷新继续走 Agent。
- 中间件按模型合并任务（一张 nginx 任务可挂多个实例），不要套 Influx 单端点一张任务。`model_id` 是具体中间件，不是 `middleware`。
- 已作为实例挂在其他非本扫描采集上则跳过，沿用现有覆盖判断。

### 推监控

- 不把中间件加入监控带凭据建采适配名单。中间件勾选推监控：服务层跳过并返回明确 reason；前端按钮不可用。
- 不猜测 `http://ip:port/stub_status` 等 URL，不把 SSH 写入监控配置。
- 主机 + SSH：维持现有 Host Remote。
- 主机 + Agent：禁止 `push_with_credential`。仅当能解析到节点时走无凭据关联 / Agent 主机模板；否则跳过并说明。

## Testing Decisions

只测外部行为：任务能否保存和触发、空池是否按 Agent 接纳、清单是否按端口拆行、写 CI / 生成采集通道是否与 SSH/Agent 一致、中间件能否被推监控。不测脚本内部 `ps` 细节、不启真实 Stargazer、不测抽屉像素。

测试缝沿用现有扫描测试，不新开运行时：

- 扫描任务校验：`middleware` 合法；主机 / 中间件允许空池；网络 / 数据库 / InfluxDB 空池仍拒绝；Agent 中间件缺云区域拒绝；SSH 中间件可不填云区域。
- 扫描触发（mock 接纳）：`middleware` 拆出 7 个 JOB family_run 与插件名；空池不 `ADMIT_FAILED`；主机有 SSH 时中间件复用该池；端口特征库中间件端口仍不出现在数据库枪里。
- 收口 / 写 CI：多 `listen_port` 拆多行；JOB success 在指标空时仍保留（通道口改默认监听口），不得删除；同 IP 主机存在才建 run 关联。收口不阻塞等 VM；缺路径时异步补齐 snapshot。
- 生成采集：SSH 行带密码字段；Agent 行凭据为空。
- 推监控：中间件行 skipped；主机 Agent 不走带凭据 Host Remote。
- 前端类型检查覆盖：族勾选、空凭据提示、云区域提示、清单列、推监控禁用文案、主机展示名。

Prior art：`test_scan_trigger_service.py`、`test_scan_views.py`、`test_scan_write_ci_service.py`、`test_scan_collect_generate.py`、`test_scan_push_monitor.py`、`test_scan_finalize_service.py`、`test_port_fingerprint.py`。

## Out of Scope

- 新写发现脚本或合并成一个「全中间件」扫描器。
- 界面上再勾选 Nginx / Tomcat 等子类型。
- 用端口特征库做 TCP 协议探测来发现中间件。
- 自动拼装监控 URL / JMX / Exporter，或把中间件纳入 `CMDB_CREATE_ADAPTED_MODEL_IDS`。
- Redis / Mongo / ES、以及采集树 Beta 中间件。
- 把 Agent 扫描改成只针对已纳管节点列表、不再填网段。
- 改 Stargazer 调度、凭据中心、扫描常驻周期。
- 改专业采集本身的空凭据语义。

## Further Notes

- 扫描纳管主规格仍是 `cmdb-scan-discovery`。本文打开其中明确后置的「中间件 JOB」。
- 端口指纹规格 `cmdb-scan-port-fingerprint` 仍规定中间件指纹可登记但不被数据库族探测；本轮发现不读那张表当探测端口。
- 命中抽屉规格 `cmdb-scan-hit-interaction` 仍是已匹配 / 未匹配两个顶层 tab。中间件只进已匹配，不新增未匹配原因。
- 产品判断：扫描负责配置事实（进程、端口、路径）；监控采集是另一套连接凭据，第一期允许停在未建采。
