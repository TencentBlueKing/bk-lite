# 118 个采集入口：原始表单恢复与凭据类型分类

> 后续确认：原表单字段继续保留，56 个 SSH JOB 的已有凭据绑定现改为 SSH，PC 使用 WinRM／SSH；以下原始绑定属于历史记录。当前分类及兼容规则见[最新内置目录](../../../docs/cmdb-collection-credential-type-mapping.md)。

> Stargazer 后续补查：15 项认证依据已确认，3 项待确认；有效类型修正及采集实现边界见[最新逐项结论](../../../docs/cmdb-18-stargazer-auth-followup-2026-09-16.md)。

> 2026-09-16 更新：最新脚本依据、有效表单修正及 18 项待确认清单见[118 项逐插件复核](../../../docs/cmdb-collection-script-credential-audit-2026-09-16.md)。下文原字段保留历史证据，当前有效配置以新复核表为准。

日期：2026-09-15。**本文替代此前“按 credential_binding 选择表单”的审计结论。**

## 基线与恢复边界

- 覆盖实际合并目录的 118 个入口：社区 45、企业增量 73（含企业覆盖同 ID 的最终目录定义）。
- 已提交的专用表单，以社区提交 `f68c495ca` 的 `credentialDescriptors.ts` 和各 Task 组件为依据；此前凭据接入期间的工作区猜测不作为原表单证据。
- 未有专用描述的入口，恢复提交 `b1a3fd34c` 的专业采集页面 `taskMap` 所使用的原通用组件。后新增入口只有通用路由可供参照的，明确记为“原通用 taskMap”，不声称找到过该插件独立发布的专用页面。
- 118 行均记录具体组件、认证／连接字段和来源。PC 的 Windows/macOS 分支、SNMP 的 V2/V3 条件字段另行保留。
- 一次性认证的表单选择由入口及组件契约决定；下文两个 FC 入口按用户后续明确要求，以真实执行脚本修正；`credential_binding`、凭据类型列表和用户选择的凭据不能改变它。
- 原表单本来就有 55 个 HostTask 入口，另有 1 个 ConfigFileTask。它们只要求账号、密码、端口；凭据管理复用“用户名密码”类型，按主机／数据库／中间件归属，不再一律绑定主机 SSH 密码／私钥类型。

## 按脚本确认的 FC 修正

用户明确要求以插件脚本调整 Brocade FC、Cisco FC。两者 `plugin.yml` 均声明 JOB 执行器与 `plugins.script_executor.SSHPlugin`，使用 SSH 用户名、密码和端口；脚本没有 SNMP 调用。现在两项表单均为账号、密码、端口（默认 22），已有凭据选择“网络／用户名密码”，认证值由凭据提供，端口留在采集表单。

历史快照保留 `original_form=snmp`，另记 `effective_form=ssh` 和修正依据，避免覆盖历史证据。历史 55 个 HostTask 入口之外新增这 2 个修正入口；2026-09-16 又按脚本将 Nacos 改为 HTTP API 表单，当前 HostTask 为 56 个。旧注册字段 `task_type=snmp` 保留以兼容存量任务／注册映射；实际执行由 `driver_type=job` 指定，前端由显式 `credential_protocol=ssh`、`credential_kind=host_account` 和默认端口选择表单。

脚本目前只使用 `ps`、`uname` 做基础探测，尚非 FC 厂商专用命令。本次认证与节点参数链路已验证，未宣称真实 FC 设备采集内容验证通过。

## 分类与字段分工

主表中的 `sql` 是现有系统管理“用户名密码”类型的英文 key，**并不强制插件使用 SQL 协议**。保留这个已有 key，扩展分类，避免重建同字段类型。相同认证字段共用类型；采集协议和表单不从类型名推导。

任务保存 `vault_credential_id`；执行前查询系统管理凭据、按插件转换 key，再合并端口等表单参数。`credential_id` 是原有任务候选 ID，不与凭据库 ID 混用。已有凭据列表只显示名称。

| 分类 | 该分类可供 CMDB 使用的内置类型 |
|---|---|
| 主机 | 用户名密码 `sql`、WinRM `winrm`、IPMI `ipmi`、Redfish `redfish`；PC macOS 用 SSH `ssh` |
| 数据库 | 用户名密码 `sql`、API Token `token` |
| 中间件 | 用户名密码 `sql` |
| 网络 | SNMP `snmp`、HTTPS 平台账户 `platform_api`、用户名密码 `sql`（FC SSH 脚本） |
| 存储 | SNMP `snmp`、AK/SK `cloud`、HTTPS 平台账户 `platform_api` |
| 云平台 | AK/SK `cloud`、HTTPS 平台账户 `platform_api`、OpenStack `openstack`、OAuth 客户端 `oauth_client` |
| 其他 | 保留系统管理原 API Token／网关密钥用途，不绑定这 118 个入口 |

共复用 **11 种认证类型**（含 PC macOS 的 SSH）；系统管理原有 network_cli、网关密钥类型继续保留，共 13 个内置 key。本轮补的是 `sql` 的主机、网络归属、`snmp` 的存储归属、`cloud` 的存储归属，及逐入口绑定；不新增 118 个重复定义。

## 118 个入口逐项核对

“字段”写的是一次性认证表单的原字段 key，包含端口等连接参数；这些连接参数不要求内置在凭据中。SNMP 字段按版本／安全级别显示，并非同时必填。CloudTask 的 `regionId` 提交时转换为 `regions`，华为云 `projectId` 转换为 `project_id`。

| # | 版本 | 对象 | 原组件 | 一次性认证原字段 | 已有凭据分类／类型 | 原表单证据 | 备注 |
|---|---|---|---|---|---|---|---|
| 001 | 社区版 | K8S `k8s_cluster` | 无手工认证表单 | — | 无需凭据 | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 002 | 社区版 | Docker `docker` | HostTask（账号密码） | `username`、`password`、`port` | `host/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 003 | 社区版 | vCenter `vmware_vc` | VMTask | `username`、`password`、`port`、`ssl` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 004 | 企业版 | ZStack `zstack` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 005 | 企业版 | 华三 UIS `h3c_cas` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 006 | 企业版 | 云宏 WinSphere `winsphere` | WinSphereTask | `user`、`password`、`https_port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 007 | 企业版 | OpenStack `openstack` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/openstack` | f68c495ca 已提交专用描述 | 历史原表单缺少用户域；2026-09-16 已按脚本补用户域和项目字段，见最新复核表 |
| 008 | 企业版 | SmartX `smartx` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 009 | 企业版 | ManageOne `manageone` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 010 | 企业版 | FusionCompute `fusioncompute` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 011 | 企业版 | 深信服 HCI `sangforhci` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 012 | 企业版 | 深信服 SCP `sangforscp` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 013 | 企业版 | Nutanix HCI `nutanixhci` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 014 | 企业版 | 浪潮 InCloud Rail `inspurincloudrail` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 015 | 社区版 | NetWork `network` | SNMPTask | `version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey` | `network/snmp` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 016 | 社区版 | 网络设备配置文件 `network_config_file` | NetworkConfigFileTask | `username`、`password`、`port`、`transport_protocol`、`enable_password` | `network/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 017 | 企业版 | Brocade FC `brocade_fc` | 原 SNMPTask → HostTask（经脚本确认修正） | `username`、`password`、`port`（默认 22） | `network/sql` | 原 taskMap 为 SNMP；现 plugin.yml 为 SSHPlugin + JOB | 按用户要求以实际脚本为准；一次性／已有凭据下发通过 |
| 018 | 企业版 | Cisco FC `cisco_fc` | 原 SNMPTask → HostTask（经脚本确认修正） | `username`、`password`、`port`（默认 22） | `network/sql` | 原 taskMap 为 SNMP；现 plugin.yml 为 SSHPlugin + JOB | 按用户要求以实际脚本为准；一次性／已有凭据下发通过 |
| 019 | 企业版 | F5 `f5` | SNMPTask | `version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey` | `network/snmp` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 020 | 企业版 | 安全设备 `security_device` | SNMPTask | `version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey` | `network/snmp` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 021 | 社区版 | IP 发现 `ip_discovery` | 无手工认证表单 | — | 无需凭据 | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 022 | 社区版 | Mysql `mysql` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 023 | 社区版 | 【BETA】InfluxDB `influxdb` | InfluxdbTask | `token`、`scheme`、`port`、`verify_tls` | `database/token` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 024 | 社区版 | PostgreSQL `postgresql` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 025 | 社区版 | 【BETA】MSSQL `mssql` | SQLTask（user/password） | `user`、`password`、`port`、`database` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 026 | 社区版 | Redis `redis` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 027 | 社区版 | 【BETA】MongoDB `mongodb` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 028 | 社区版 | 【BETA】Elasticsearch `es` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 029 | 社区版 | 【BETA】HBase `hbase` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 030 | 企业版 | OceanBase `oceanbase` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 031 | 企业版 | 瀚高HighGo `highgo` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 032 | 企业版 | Informix `informix` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 033 | 企业版 | Sybase `sybase` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 034 | 企业版 | Couchbase `couchbase` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 035 | 企业版 | MyCAT `mycat` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 036 | 企业版 | SAP HANA `sap_hana` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 037 | 企业版 | InterSystems IRIS `iris` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 038 | 企业版 | Redis Sentinel `redis_sentinel` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 039 | 企业版 | GBase 8s `gbase8s` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 040 | 企业版 | 神通 Oscar `oscar` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 041 | 企业版 | TongRDS `tongrds` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 042 | 企业版 | TDSQL `tdsql` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 043 | 企业版 | 达梦数据库 `dameng` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 044 | 企业版 | DB2 `db2` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 045 | 企业版 | TiDB `tidb` | HostTask（账号密码） | `username`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 046 | 企业版 | GBase 8a `gbase8a` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 047 | 企业版 | Greenplum `greenplum` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 048 | 企业版 | 人大金仓 `kingbase` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 049 | 企业版 | openGauss `opengauss` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 050 | 企业版 | Vastbase `vastbase` | SQLTask（user/password） | `user`、`password`、`port` | `database/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 051 | 社区版 | 【BETA】华为存储 `storage` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `storage/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 052 | 社区版 | 【BETA】Dell Unity `dell_unity` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/platform_api` | b1a3fd34c 原通用 taskMap | 恢复原 CloudTask 键；accessKey/accessSecret 实为平台账号密码，转换到 username/password；原 Region 表单仍保留 |
| 053 | 社区版 | 【BETA】NetApp ONTAP `netapp_ontap` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/platform_api` | b1a3fd34c 原通用 taskMap | 恢复原 CloudTask 键；accessKey/accessSecret 实为平台账号密码，转换到 username/password；原 Region 表单仍保留 |
| 054 | 企业版 | IBM Storwize `ibm_storwize` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 055 | 企业版 | IBM DS `ibm_ds` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 056 | 企业版 | EMC Symmetrix `emc_symmetrix` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 057 | 企业版 | 【BETA】Hitachi VSP `hds_vsp` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/platform_api` | b1a3fd34c 原通用 taskMap | 恢复原 CloudTask 键；accessKey/accessSecret 实为平台账号密码，转换到 username/password；原 Region 表单仍保留 |
| 058 | 企业版 | 宏杉存储 `macrosan` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 059 | 企业版 | 【BETA】Pure Storage `pure_array` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/platform_api` | b1a3fd34c 原通用 taskMap | 恢复原 CloudTask 键；accessKey/accessSecret 实为平台账号密码，转换到 username/password；原 Region 表单仍保留 |
| 060 | 企业版 | NetApp Cluster `netapp_cluster` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 061 | 企业版 | Oracle ZFS `oraclezfs` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 062 | 企业版 | Infinidat `infinidat` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 063 | 企业版 | 磁带库 `tape_library` | SNMPTask | `version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey` | `storage/snmp` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 064 | 企业版 | XSKY `xsky` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/cloud` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 065 | 企业版 | 【BETA】Dell PowerStore `dell_powerstore` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/platform_api` | b1a3fd34c 原通用 taskMap | 恢复原 CloudTask 键；accessKey/accessSecret 实为平台账号密码，转换到 username/password；原 Region 表单仍保留 |
| 066 | 企业版 | 【BETA】HPE 3PAR/Primera `hp_3par` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `storage/platform_api` | b1a3fd34c 原通用 taskMap | 恢复原 CloudTask 键；accessKey/accessSecret 实为平台账号密码，转换到 username/password；原 Region 表单仍保留 |
| 067 | 社区版 | 阿里云 `aliyun_account` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `cloud/cloud` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 068 | 社区版 | 腾讯云 `qcloud` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `cloud/cloud` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 069 | 社区版 | 华为云【beta】 `hwcloud` | CloudTask | `accessKey`、`accessSecret`、`regionId`、`projectId` | `cloud/cloud` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 070 | 社区版 | FusionInsight【beta】 `fusioninsight` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/platform_api` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 071 | 企业版 | AWS `aws` | CloudTask | `accessKey`、`accessSecret`、`regionId` | `cloud/cloud` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 072 | 企业版 | Azure `azure` | PlatformApiTask | `username`、`password`、`port`、`verify_tls` | `cloud/oauth_client` | f68c495ca 已提交专用描述 | 原平台表单只有账号密码；tenant_id 由已有凭据提供，subscription_id 留动态表单；一次性认证原缺口保留 |
| 073 | 社区版 | 主机 `host` | HostTask（账号密码） | `username`、`password`、`port` | `host/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 074 | 社区版 | 配置文件 `config_file` | ConfigFileTask | `username`、`password`、`port` | `host/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 075 | 社区版 | 物理服务器 SSH `physcial_server` | HostTask（账号密码） | `username`、`password`、`port` | `host/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 076 | 社区版 | 【BETA】物理服务器 IPMI `physcial_server_ipmi` | IPMITask | `username`、`password`、`port`、`privilege` | `host/ipmi` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 077 | 社区版 | 【BETA】物理服务器 Redfish `physcial_server_redfish` | RedfishTask | `username`、`password`、`port`、`verify_tls` | `host/redfish` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 078 | 企业版 | 服务器BMC `server_bmc` | SQLTask（user/password） | `user`、`password`、`port` | `host/redfish` | b1a3fd34c 原通用 taskMap | 恢复 user/password/port；默认 3306 与节点默认 443 有历史差异 |
| 079 | 企业版 | HMC `hmc` | HostTask（账号密码） | `username`、`password`、`port` | `host/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 080 | 企业版 | PC发现 `pc` | PCTask | `username`、`password`、`port`、`scheme`、`transport`、`certValidation` | `host/winrm` | b1a3fd34c 原通用 taskMap | Windows 原 WinRM；macOS 保留 username、authType、password 或 private_key/passphrase、port；绑定 host/ssh |
| 081 | 社区版 | Nginx `nginx` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 082 | 社区版 | 【BETA】MinIO `minio` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 083 | 社区版 | Zookeeper `zookeeper` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 084 | 社区版 | Kafka `kafka` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 085 | 社区版 | Consul `consul` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 086 | 社区版 | Etcd `etcd` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 087 | 社区版 | RabbitMQ `rabbitmq` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 088 | 社区版 | Tomcat `tomcat` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 089 | 社区版 | Apache `apache` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 090 | 社区版 | ActiveMQ `activemq` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 091 | 社区版 | IIS `iis` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 092 | 社区版 | Tuxedo `tuxedo` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 093 | 社区版 | Memcached `memcached` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 094 | 社区版 | RocketMQ `rocketmq` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 095 | 社区版 | OpenResty `openresty` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 096 | 社区版 | Squid `squid` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 097 | 社区版 | HAProxy `haproxy` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 098 | 社区版 | KeepAlive【beta】 `keepalive` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 099 | 社区版 | Spark `spark` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | f68c495ca 已提交专用描述 | 保留原表单；已有凭据仅替换认证值 |
| 100 | 企业版 | Nacos `nacos` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 恢复 username/password/port（原默认 22）；实际 Nacos API 默认 8848，未擅改表单 |
| 101 | 企业版 | IBM MQ `ibmmq` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 102 | 企业版 | TongLINK/Q `tonglinkq` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 103 | 企业版 | TongGTP `tonggtp` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 104 | 企业版 | IBM HTTP Server `ihs` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 105 | 企业版 | IBM CICS `cics` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 106 | 企业版 | HDFS `hdfs` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 107 | 企业版 | YARN `yarn` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 108 | 企业版 | Storm `storm` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 109 | 企业版 | Ambari `ambari` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 原为 HostTask 账号密码；凭据类型为中间件账号密码，不再允许私钥 |
| 110 | 企业版 | BES `bes` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 111 | 企业版 | Apusic `apusic` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 112 | 企业版 | InforSuite AS `inforsuite_as` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 113 | 企业版 | Ceph `ceph` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 114 | 企业版 | JBoss `jboss` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 115 | 企业版 | Jetty `jetty` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 116 | 企业版 | TongWeb `tongweb` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 117 | 企业版 | WebLogic `weblogic` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |
| 118 | 企业版 | WebSphere `websphere` | HostTask（账号密码） | `username`、`password`、`port` | `middleware/sql` | b1a3fd34c 原通用 taskMap | 保留原表单；已有凭据仅替换认证值 |

## 已确认的历史差异，不算“已验证可采集”

1. **Brocade FC、Cisco FC（认证冲突已修复）**：经用户明确要求按实际 SSHPlugin 脚本修正为用户名、密码、端口表单及 `network/sql` 绑定；一次性／已有凭据均验证至节点最终配置。FC 厂商专用采集命令仍待完善，不计为真实设备采集验证。
2. **Nacos、server_bmc、7 个企业 SQL 入口**：原通用组件的默认端口可能与实际节点默认值不一致。本轮撤回先前新增的 8 条默认端口覆盖，按原表单恢复；用户仍可修改端口。实际端口由插件执行配置核对，后续纠正时应作为单独表单变更。
3. **6 个存储入口**：原通用 CloudTask 带 AK/SK 键及区域交互，实际 NodeParams 使用平台用户名密码。本轮保留表单键并补明确转换，不将这些账户内置为云 AK/SK；原区域交互是否适合设备采集仍是历史缺口。
4. **Azure、OpenStack**：原平台账号表单没有完整表达 OAuth tenant／OpenStack 用户域。已有凭据可提供这些字段，旧一次性表单本身的缺口仍应单独修正，不能把恢复表单与补全新认证方式混为一谈。

## 初始化与存量任务

- 不需要新增数据库结构迁移。需要调用现有 `seed_builtin_types()` 更新内置类型分类；该操作会保留内置类型和凭据实例 ID，已经验证重复执行不新增重复类型。
- 原有一次性认证任务继续按原字段回显、编辑和提交，无需搬迁密码。例外：此前按错误 SNMP 表单创建的两个 FC 任务需重新填写 SSH 用户名、密码、端口，或选择网络分类的用户名密码凭据；SNMP community 无法转换成 SSH 密码。
- 此前错误接入期间若任务选择了 SSH 类型凭据，而新分类要求用户名密码，需要重新选择对应账号密码凭据；不会自动复制秘密或把私钥转换成密码。
- 凭据值仍在下发时读取；接口返回类型和绑定信息不包含秘密。

## 验证记录

- 上轮先按历史表单恢复 SNMP；本轮按用户后续要求核验脚本，新的 FC 执行契约／节点参数回归先出现 4 项失败，修正表单与类型绑定后通过。
- 118 个入口分别渲染一次性认证控件，操作账号／秘密字段，检查回调仍使用原字段名；2 个无需认证入口检查没有凭据描述。
- 后端 118 项原字段不变检查、118 项分类检查、116 项已有凭据 key 转换检查；真实内置类型初始化及幂等检查。
- 新增测试发现 6 个存储入口缺 accessKey/accessSecret、server_bmc 缺 user，补转换后通过。
- 上述验证覆盖表单、类型目录与凭据解析边界，不等于 118 个真实目标全部采集成功。两个 FC 入口的认证冲突已经解除；真实 FC 设备专用采集内容仍未验证。


本轮执行结果：前端相关 12 个测试文件共 292 项通过，其中 118 项逐入口控件渲染／字段修改；后端凭据解析、原表单契约、系统凭据与企业边界合跑 1021 项通过、2 项无需认证跳过、2 项既有 Agent 产物缺失预期失败（dell_powerstore、hp_3par）。两个 FC 入口不再预期失败；另有 2 项脚本声明契约、4 项一次性／已有凭据真实 TOML 下发配置检查，断言用户名、密码引用、端口及无 SNMP 字段。1 个凭据列表用例依赖 SQLite 不支持的 JSON contains 查询，按已确认的环境限制排除。前端 `pnpm type-check` 与本轮修改文件 ESLint 均通过。

本地更新分类可在 Server 环境执行：

```bash
python manage.py shell -c "from apps.system_mgmt.services.credential_service import seed_builtin_types; seed_builtin_types()"
```

这里只初始化类型，不创建真实账号密码，不修改存量一次性任务。随后重启加载后端代码并更新前端。
