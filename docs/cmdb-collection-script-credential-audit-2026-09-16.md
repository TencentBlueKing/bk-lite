# 118 个采集入口：脚本、凭据与任务表单核对

> 最新类型约定：56 个 SSH JOB 已由用户名密码改绑 SSH，PC 维持 WinRM／SSH 分支，旧引用兼容。见[最新内置分类及逐项列表](cmdb-collection-credential-type-mapping.md)。本文历史数据库漏配记录保留原值，当前 118 行绑定已更新。

> 后续补查已完成：原“18 项无法确认”修正为“15 项有认证依据、3 项待确认”，详见[18 项 Stargazer 补查](cmdb-18-stargazer-auth-followup-2026-09-16.md)。其中 9 项仍缺配置采集体，不能计为真实采集可用。

日期：2026-09-16。覆盖社区版 45 个、企业版增量 73 个入口。以本工作区合并 tree、前端实际 CredentialDescriptor、企业源码及社区 Agent 清单／脚本为依据；历史表单证据仍保留在原核对表，本文记录脚本复核后的有效配置。

## 本轮修正

| 对象 | 脚本证据与修正结果 |
|---|---|
| 网络设备配置文件 | Scrapli 使用账号、密码、可选 enable_password。2026-09-17 改为 `network/ssh`（仅密码认证），仍由任务选择 SSH/Telnet；旧平台账户引用保留兼容。端口、传输协议、可选特权密码留在已有凭据表单。下发前读凭据 ID，合并特权密码；额外密码加密存储、回显掩码，编辑掩码保留、空值清除。 |
| F5、安全设备、磁带库、宏杉 | 已通过社区 Stargazer 的 SnmpFacts 确认并补齐 SNMP 认证消费，已有凭据只补端口；仅 Network 显示拓扑采集选项。 |
| Brocade FC、Cisco FC、Informix | 实际为 SSHPlugin + JOB：账号、密码、端口 22；FC 绑定网络／SSH，Informix 绑定数据库／SSH。JOB 内部是基础探测，认证通道可确认，产品采集内容不能确认。 |
| OceanBase | pymysql；数据库 user/password，默认 2881，修正原 3306。 |
| HighGo、Greenplum、Kingbase、OpenGauss、Vastbase | 继承 PostgreSQL 采集器；数据库 user/password，默认 5432，修正原 3306。 |
| Nacos | HTTP API；改为平台账号密码表单，默认 8848，补 scheme；TLS 校验偏好传递到实际 Session。类型仍复用中间件／用户名密码。 |
| server_bmc | Redfish API；改为 Redfish 表单，默认 443；TLS 校验偏好传递到实际 Session。 |
| Dell Unity、NetApp ONTAP、HDS VSP、Pure Array、Dell PowerStore、HP 3PAR | 实际 HTTPS API 使用 username/password；将旧 AK/SK 表单改为平台账号表单，默认 443，保留后端旧字段别名兼容。 |
| Azure | 一次性认证补 tenant_id、subscription_id；已有凭据从 OAuth 类型获取 tenant/client，表单补 subscription_id。 |
| OpenStack | 一次性认证补 user_domain_name（默认 Default）和可选 project_id；已有凭据提供域，项目由任务填写，两种模式均下发。 |

选择凭据后只显示名称，任务保存 `vault_credential_id`，执行前读取并转换 key。`credential_id` 保留为候选记录 ID。已修正选择默认类型时未记录 `vault_type_key` 的问题。凭据管理提供的认证字段不重复显示；端口及本插件需要的额外参数保留。

## 118 项完整表

“脚本读取”列包含认证入口，JOB 指远程通道；SNMP 条件字段按版本显示。表单列列出认证和连接参数，已有凭据模式隐藏类型管理的字段，保留其余字段。类型与协议分别核对，不通过凭据类型猜测协议。链接指向当前源码，不代表所有脚本已经具备厂商专用采集能力。

| # | 版本／对象 | 执行依据 | 脚本读取认证 | 当前表单字段／默认端口 | 已有凭据分类／类型 | 结论 |
|---|---|---|---|---|---|---|
| 001 | 社区版 K8S `k8s_cluster` | protocol / Kubernetes 引导接入 | 无需手工认证 | none：—；端口 — | 无需凭据 | 独立接入流程 |
| 002 | 社区版 Docker `docker` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/docker/docker_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `host/ssh` | 按实际远程执行通道核对 |
| 003 | 社区版 vCenter `vmware_vc` | [protocol / VmwareManage](../agents/stargazer/plugins/inputs/vmware_vc/vmware_info.py) | password、username | vmware：`username`、`password`、`port`、`ssl`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 004 | 企业版 ZStack `zstack` | [protocol / ZstackInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/zstack/zstack_info.py) | 无认证消费 | platform_api：`username`、`password`、`port`、`verify_tls`；端口 8080 | `cloud/platform_api` | 认证路径未确认；明确报未实现 |
| 005 | 企业版 华三 UIS `h3c_cas` | [protocol / H3cCasInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/h3c_cas/h3c_cas_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 006 | 企业版 云宏 WinSphere `winsphere` | [protocol / WinSphereInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/winsphere/winsphere_info.py) | password、user | winsphere：`user`、`password`、`https_port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 007 | 企业版 OpenStack `openstack` | [protocol / OpenStackManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/openstack/openstack_info.py) | accessKey、accessSecret、password、tenant_id、token、user_domain_name、username | platform_api：`username`、`password`、`port`、`verify_tls`、`user_domain_name`、`project_id`；端口 443 | `cloud/openstack` | 已核对认证参数读取 |
| 008 | 企业版 SmartX `smartx` | [protocol / SmartXManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/smartx/smartx_info.py) | accessKey、accessSecret、password、token、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 009 | 企业版 ManageOne `manageone` | [protocol / ManageOneManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/manageone/manageone_info.py) | accessKey、accessSecret、password、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 010 | 企业版 FusionCompute `fusioncompute` | [protocol / FusionComputeManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/fusioncompute/fusioncompute_info.py) | accessKey、accessSecret、password、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 7443 | `cloud/platform_api` | 已核对认证参数读取 |
| 011 | 企业版 深信服 HCI `sangforhci` | [protocol / SangforHCIManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/sangforhci/sangforhci_info.py) | accessKey、accessSecret、password、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 012 | 企业版 深信服 SCP `sangforscp` | [protocol / SangforSCPManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/sangforscp/sangforscp_info.py) | accessKey、accessSecret、password、token、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 013 | 企业版 Nutanix HCI `nutanixhci` | [protocol / NutanixhciManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/nutanixhci/nutanixhci_info.py) | accessKey、accessSecret、password、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 014 | 企业版 浪潮 InCloud Rail `inspurincloudrail` | [protocol / InspurInCloudRailManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/inspurincloudrail/inspurincloudrail_info.py) | accessKey、accessSecret、password、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 015 | 社区版 NetWork `network` | [protocol / SnmpFacts](../agents/stargazer/plugins/inputs/network/snmp_facts.py) | authkey、community、integrity、level、privacy、privkey、username、version | snmp：`version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey`；端口 161 | `network/snmp` | 已核对认证参数读取 |
| 016 | 社区版 网络设备配置文件 `network_config_file` | [protocol / NetworkConfigFileInfo](../agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py) | enable_password、password、username | network_config_file：`username`、`password`、`port`、`transport_protocol`、`enable_password`；端口 22 | `network/ssh` | 已核对认证参数读取 |
| 017 | 企业版 Brocade FC `brocade_fc` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/brocade_fc/brocade_fc_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `network/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 018 | 企业版 Cisco FC `cisco_fc` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/cisco_fc/cisco_fc_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `network/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 019 | 企业版 F5 `f5` | [protocol / F5Info](../enterprise/agents/stargazer/enterprise/plugins/inputs/f5/f5_info.py) | SNMP V2/V3 字段 | snmp：`version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey`；端口 161 | `network/snmp` | 复用现有 Stargazer 调用；认证字段已验证 |
| 020 | 企业版 安全设备 `security_device` | [protocol / SecurityDeviceInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/security_device/security_device_info.py) | SNMP V2/V3 字段 | snmp：`version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey`；端口 161 | `network/snmp` | 复用现有 Stargazer 调用；认证字段已验证 |
| 021 | 社区版 IP 发现 `ip_discovery` | [protocol / IPDiscoveryScanner](../agents/stargazer/plugins/inputs/ip/ip_discovery_scanner.py) | 无需手工认证 | none：—；端口 — | 无需凭据 | 已核对认证参数读取 |
| 022 | 社区版 Mysql `mysql` | [protocol / MysqlInfo](../agents/stargazer/plugins/inputs/mysql/mysql_info.py) | password、user | sql：`user`、`password`、`port`；端口 3306 | `database/sql` | 已核对认证参数读取 |
| 023 | 社区版 【BETA】InfluxDB `influxdb` | [protocol / InfluxdbInfo](../agents/stargazer/plugins/inputs/influxdb/influxdb_info.py) | password、token | influxdb：`token`、`scheme`、`port`、`verify_tls`；端口 8086 | `database/token` | 已核对认证参数读取 |
| 024 | 社区版 PostgreSQL `postgresql` | [protocol / PostgresqlInfo](../agents/stargazer/plugins/inputs/postgresql/postgresql_info.py) | password、user | sql：`user`、`password`、`port`；端口 5432 | `database/sql` | 已核对认证参数读取 |
| 025 | 社区版 【BETA】MSSQL `mssql` | [protocol / MSSQLInfo](../agents/stargazer/plugins/inputs/mssql/mssql_info.py) | password、user | sql：`user`、`password`、`port`、`database`；端口 1433 | `database/sql` | 已核对认证参数读取 |
| 026 | 社区版 Redis `redis` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/redis/redis_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 027 | 社区版 【BETA】MongoDB `mongodb` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/mongodb/mongodb_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 028 | 社区版 【BETA】Elasticsearch `es` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/es/es_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 029 | 社区版 【BETA】HBase `hbase` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/hbase/hbase_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 030 | 企业版 OceanBase `oceanbase` | [protocol / OceanBaseInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/oceanbase/oceanbase_info.py) | password、user、username | sql：`user`、`password`、`port`；端口 2881 | `database/sql` | 已核对认证参数读取 |
| 031 | 企业版 瀚高HighGo `highgo` | [protocol / HighGoInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/highgo/highgo_info.py) | password、user | sql：`user`、`password`、`port`；端口 5432 | `database/sql` | 已核对认证参数读取 |
| 032 | 企业版 Informix `informix` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/informix/informix_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 033 | 企业版 Sybase `sybase` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/sybase/sybase_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 034 | 企业版 Couchbase `couchbase` | [protocol / CouchbaseInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/couchbase/couchbase_info.py) | user/password | sql：`user`、`password`、`port`、`bucket`；端口 8091 | `database/sql` | 认证字段已补；产品采集体未实现 |
| 035 | 企业版 MyCAT `mycat` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/mycat/mycat_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 036 | 企业版 SAP HANA `sap_hana` | [protocol / SapHanaInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/sap_hana/sap_hana_info.py) | user/password | sql：`user`、`password`、`port`；端口 30015 | `database/sql` | 认证字段已补；产品采集体未实现 |
| 037 | 企业版 InterSystems IRIS `iris` | [protocol / IrisInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/iris/iris_info.py) | user/password | sql：`user`、`password`、`port`、`namespace`；端口 1972 | `database/sql` | 认证字段已补；产品采集体未实现 |
| 038 | 企业版 Redis Sentinel `redis_sentinel` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/redis_sentinel/redis_sentinel_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 039 | 企业版 GBase 8s `gbase8s` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/gbase8s/gbase8s_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 040 | 企业版 神通 Oscar `oscar` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/oscar/oscar_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 041 | 企业版 TongRDS `tongrds` | [protocol / TongrdsInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/tongrds/tongrds_info.py) | user/password | sql：`user`、`password`、`port`；端口 6379 | `database/sql` | 认证字段已补；产品采集体未实现 |
| 042 | 企业版 TDSQL `tdsql` | [protocol / TdsqlInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/tdsql/tdsql_info.py) | user/password | sql：`user`、`password`、`port`；端口 3306 | `database/sql` | 复用现有 Stargazer 调用；认证字段已验证 |
| 043 | 企业版 达梦数据库 `dameng` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/dameng/dameng_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 044 | 企业版 DB2 `db2` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/db2/db2_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 045 | 企业版 TiDB `tidb` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/tidb/tidb_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `database/ssh` | 按实际远程执行通道核对 |
| 046 | 企业版 GBase 8a `gbase8a` | [protocol / Gbase8aInfo](../agents/stargazer/plugins/inputs/gbase8a/gbase8a_info.py) | password、user | sql：`user`、`password`、`port`；端口 3306 | `database/sql` | 已核对认证参数读取 |
| 047 | 企业版 Greenplum `greenplum` | [protocol / GreenplumInfo](../agents/stargazer/plugins/inputs/greenplum/greenplum_info.py) | password、user | sql：`user`、`password`、`port`；端口 5432 | `database/sql` | 已核对认证参数读取 |
| 048 | 企业版 人大金仓 `kingbase` | [protocol / KingbaseInfo](../agents/stargazer/plugins/inputs/kingbase/kingbase_info.py) | password、user | sql：`user`、`password`、`port`；端口 5432 | `database/sql` | 已核对认证参数读取 |
| 049 | 企业版 openGauss `opengauss` | [protocol / OpenGaussInfo](../agents/stargazer/plugins/inputs/opengauss/opengauss_info.py) | password、user | sql：`user`、`password`、`port`；端口 5432 | `database/sql` | 已核对认证参数读取 |
| 050 | 企业版 Vastbase `vastbase` | [protocol / VastbaseInfo](../agents/stargazer/plugins/inputs/vastbase/vastbase_info.py) | password、user | sql：`user`、`password`、`port`；端口 5432 | `database/sql` | 已核对认证参数读取 |
| 051 | 社区版 【BETA】华为存储 `storage` | protocol / 待核对 | 未找到清单 | platform_api：`username`、`password`、`port`、`verify_tls`；端口 8088 | `storage/platform_api` | 缺少证据 |
| 052 | 社区版 【BETA】Dell Unity `dell_unity` | [protocol / DellUnityManager](../agents/stargazer/plugins/inputs/dell_unity/dell_unity_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 已核对认证参数读取 |
| 053 | 社区版 【BETA】NetApp ONTAP `netapp_ontap` | [protocol / NetAppOntapManager](../agents/stargazer/plugins/inputs/netapp_ontap/netapp_ontap_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 已核对认证参数读取 |
| 054 | 企业版 IBM Storwize `ibm_storwize` | [protocol / IbmStorwizeInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/ibm_storwize/ibm_storwize_info.py) | username/password | platform_api：`username`、`password`、`port`、`verify_tls`；端口 7443 | `storage/platform_api` | 认证字段已补；产品采集体未实现 |
| 055 | 企业版 IBM DS `ibm_ds` | [protocol / IbmDsInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/ibm_ds/ibm_ds_info.py) | 无认证消费 | cloud：`accessKey`、`accessSecret`、`regionId`；端口 443 | `storage/cloud` | 认证路径未确认；明确报未实现 |
| 056 | 企业版 EMC Symmetrix `emc_symmetrix` | [protocol / EmcSymmetrixInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/emc_symmetrix/emc_symmetrix_info.py) | username/password | platform_api：`username`、`password`、`port`、`verify_tls`；端口 8443 | `storage/platform_api` | 认证字段已补；产品采集体未实现 |
| 057 | 企业版 【BETA】Hitachi VSP `hds_vsp` | [protocol / HdsVspManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/hds_vsp/hds_vsp_info.py) | password、token、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 已核对认证参数读取 |
| 058 | 企业版 宏杉存储 `macrosan` | [protocol / MacrosanInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/macrosan/macrosan_info.py) | SNMP V2/V3 字段 | snmp：`version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey`；端口 161 | `storage/snmp` | 复用现有 Stargazer 调用；认证字段已验证 |
| 059 | 企业版 【BETA】Pure Storage `pure_array` | [protocol / PureArrayManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/pure_array/pure_array_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 已核对认证参数读取 |
| 060 | 企业版 NetApp Cluster `netapp_cluster` | [protocol / NetappClusterInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/netapp_cluster/netapp_cluster_info.py) | username/password | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 复用现有 Stargazer 调用；认证字段已验证 |
| 061 | 企业版 Oracle ZFS `oraclezfs` | [protocol / OraclezfsInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/oraclezfs/oraclezfs_info.py) | username/password | platform_api：`username`、`password`、`port`、`verify_tls`；端口 215 | `storage/platform_api` | 认证字段已补；产品采集体未实现 |
| 062 | 企业版 Infinidat `infinidat` | [protocol / InfinidatInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/infinidat/infinidat_info.py) | username/password | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 认证字段已补；产品采集体未实现 |
| 063 | 企业版 磁带库 `tape_library` | [protocol / TapeLibraryInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/tape_library/tape_library_info.py) | SNMP V2/V3 字段 | snmp：`version`、`community`、`snmp_port`、`username`、`level`、`integrity`、`authkey`、`privacy`、`privkey`；端口 161 | `storage/snmp` | 复用现有 Stargazer 调用；认证字段已验证 |
| 064 | 企业版 XSKY `xsky` | [protocol / XskyInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/xsky/xsky_info.py) | 无认证消费 | cloud：`accessKey`、`accessSecret`、`regionId`；端口 443 | `storage/cloud` | 认证路径未确认；明确报未实现 |
| 065 | 企业版 【BETA】Dell PowerStore `dell_powerstore` | [protocol / PowerStoreManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/dell_powerstore/dell_powerstore_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 已核对认证参数读取 |
| 066 | 企业版 【BETA】HPE 3PAR/Primera `hp_3par` | [protocol / Hp3parManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/hp_3par/hp_3par_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `storage/platform_api` | 已核对认证参数读取 |
| 067 | 社区版 阿里云 `aliyun_account` | [protocol / CwAliyun](../agents/stargazer/plugins/inputs/aliyun/aliyun_info.py) | accessKey、accessSecret、access_key、access_secret、secret_id、secret_key | cloud：`accessKey`、`accessSecret`、`regionId`；端口 — | `cloud/cloud` | 已核对认证参数读取 |
| 068 | 社区版 腾讯云 `qcloud` | [protocol / TencentCloudManager](../agents/stargazer/plugins/inputs/qcloud/qcloud_info.py) | accessKey、accessSecret、access_key、access_secret、secret_id、secret_key | cloud：`accessKey`、`accessSecret`、`regionId`；端口 — | `cloud/cloud` | 已核对认证参数读取 |
| 069 | 社区版 华为云【beta】 `hwcloud` | [protocol / HuaweiCloudManager](../agents/stargazer/plugins/inputs/hwcloud/huaweicloud_info.py) | accessKey、accessSecret、password、username | cloud：`accessKey`、`accessSecret`、`regionId`、`projectId`；端口 — | `cloud/cloud` | 已核对认证参数读取 |
| 070 | 社区版 FusionInsight【beta】 `fusioninsight` | [protocol / FusionInsightManager](../agents/stargazer/plugins/inputs/fusioninsight/fusioninsight_info.py) | accessKey、accessSecret、password、username | platform_api：`username`、`password`、`port`、`verify_tls`；端口 443 | `cloud/platform_api` | 已核对认证参数读取 |
| 071 | 企业版 AWS `aws` | [protocol / AWSManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/aws/aws_info.py) | secret_id、secret_key | cloud：`accessKey`、`accessSecret`、`regionId`；端口 — | `cloud/cloud` | 已核对认证参数读取 |
| 072 | 企业版 Azure `azure` | [protocol / AzureManager](../enterprise/agents/stargazer/enterprise/plugins/inputs/azure/azure_info.py) | accessKey、accessSecret、password、tenant_id、username | platform_api：`username`、`password`、`port`、`verify_tls`、`tenant_id`、`subscription_id`；端口 443 | `cloud/oauth_client` | 已核对认证参数读取 |
| 073 | 社区版 主机 `host` | [job / HostInfo](../agents/stargazer/plugins/inputs/host/host_info.py) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `host/ssh` | 按实际远程执行通道核对 |
| 074 | 社区版 配置文件 `config_file` | [job / ConfigFileInfo](../agents/stargazer/plugins/inputs/config_file/config_file_info.py) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `host/ssh` | 按实际远程执行通道核对 |
| 075 | 社区版 物理服务器 SSH `physcial_server` | [job / PhyscialServerInfo](../agents/stargazer/plugins/inputs/physcial_server/physcial_server_info.py) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `host/ssh` | 按实际远程执行通道核对 |
| 076 | 社区版 【BETA】物理服务器 IPMI `physcial_server_ipmi` | [protocol / PhyscialServerProtocolInfo](../agents/stargazer/plugins/inputs/physcial_server/physcial_server_info.py) | passphrase、password、private_key、user、username | ipmi：`username`、`password`、`port`、`privilege`；端口 623 | `host/ipmi` | 已核对认证参数读取 |
| 077 | 社区版 【BETA】物理服务器 Redfish `physcial_server_redfish` | [protocol / PhyscialServerProtocolInfo](../agents/stargazer/plugins/inputs/physcial_server/physcial_server_info.py) | passphrase、password、private_key、user、username | redfish：`username`、`password`、`port`、`verify_tls`；端口 443 | `host/redfish` | 已核对认证参数读取 |
| 078 | 企业版 服务器BMC `server_bmc` | [protocol / ServerBmcInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/server_bmc/server_bmc_info.py) | password、user、username | redfish：`username`、`password`、`port`、`verify_tls`；端口 443 | `host/redfish` | 已核对认证参数读取 |
| 079 | 企业版 HMC `hmc` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/hmc/hmc_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `host/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 080 | 企业版 PC发现 `pc` | [job / PCInventoryCollector](../enterprise/agents/stargazer/enterprise/plugins/inputs/pc/pc_inventory.py) | SSH 账号密码；PC 分 WinRM/SSH | none：`username`、`password`、`port`、`scheme`、`transport`、`certValidation`；端口 — | `host/winrm` | 按实际远程执行通道核对 |
| 081 | 社区版 Nginx `nginx` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/nginx/nginx_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 082 | 社区版 【BETA】MinIO `minio` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/minio/minio_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 083 | 社区版 Zookeeper `zookeeper` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/zookeeper/zookeeper_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 084 | 社区版 Kafka `kafka` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/kafka/kafka_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 085 | 社区版 Consul `consul` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/consul/consul_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 086 | 社区版 Etcd `etcd` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/etcd/etcd_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 087 | 社区版 RabbitMQ `rabbitmq` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/rabbitmq/rabbitmq_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 088 | 社区版 Tomcat `tomcat` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/tomcat/tomcat_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 089 | 社区版 Apache `apache` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/apache/apache_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 090 | 社区版 ActiveMQ `activemq` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/activemq/activemq_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 091 | 社区版 IIS `iis` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/iis/iis_default_discover.ps1) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 092 | 社区版 Tuxedo `tuxedo` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/tuxedo/tuxedo_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 093 | 社区版 Memcached `memcached` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/memcached/memcached_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 094 | 社区版 RocketMQ `rocketmq` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/rocketmq/rocketmq_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 095 | 社区版 OpenResty `openresty` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/openresty/openresty_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 096 | 社区版 Squid `squid` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/squid/squid_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 097 | 社区版 HAProxy `haproxy` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/haproxy/haproxy_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 098 | 社区版 KeepAlive【beta】 `keepalive` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/keepalived/keepalived_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 099 | 社区版 Spark `spark` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/spark/spark_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 100 | 企业版 Nacos `nacos` | [protocol / NacosInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/nacos/nacos_info.py) | password、user、username | platform_api：`username`、`password`、`port`、`verify_tls`、`scheme`；端口 8848 | `middleware/sql` | 已核对认证参数读取 |
| 101 | 企业版 IBM MQ `ibmmq` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/ibmmq/ibmmq_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 102 | 企业版 TongLINK/Q `tonglinkq` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/tonglinkq/tonglinkq_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 103 | 企业版 TongGTP `tonggtp` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/tonggtp/tonggtp_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 104 | 企业版 IBM HTTP Server `ihs` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/ihs/ihs_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 105 | 企业版 IBM CICS `cics` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/cics/cics_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 106 | 企业版 HDFS `hdfs` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/hdfs/hdfs_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 107 | 企业版 YARN `yarn` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/yarn/yarn_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 108 | 企业版 Storm `storm` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/storm/storm_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 109 | 企业版 Ambari `ambari` | [protocol / AmbariInfo](../enterprise/agents/stargazer/enterprise/plugins/inputs/ambari/ambari_info.py) | user/password | platform_api：`username`、`password`、`port`、`verify_tls`；端口 8080 | `middleware/sql` | 认证字段已补；产品采集体未实现 |
| 110 | 企业版 BES `bes` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/bes/bes_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 111 | 企业版 Apusic `apusic` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/apusic/apusic_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 112 | 企业版 InforSuite AS `inforsuite_as` | [job / SSHPlugin](../enterprise/agents/stargazer/enterprise/plugins/inputs/inforsuite_as/inforsuite_as_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 通道认证可核对；脚本为基础占位探测 |
| 113 | 企业版 Ceph `ceph` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/ceph/ceph_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 114 | 企业版 JBoss `jboss` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/jboss/jboss_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 115 | 企业版 Jetty `jetty` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/jetty/jetty_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 116 | 企业版 TongWeb `tongweb` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/tongweb/tongweb_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 117 | 企业版 WebLogic `weblogic` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/weblogic/weblogic_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |
| 118 | 企业版 WebSphere `websphere` | [job / SSHPlugin](../agents/stargazer/plugins/inputs/websphere/websphere_default_discover.sh) | 远程通道账号密码（SSHPlugin/执行器） | ssh：`username`、`password`、`port`；端口 22 | `middleware/ssh` | 按实际远程执行通道核对 |

## 原 18 项的补查结论

认证依据已确认并补齐 15 项；ZStack、IBM DS、XSKY 仍缺可确认的真实配置采集认证调用。9 项虽然字段契约已补齐，采集体仍缺失。逐项源码与区别见[后续补查](cmdb-18-stargazer-auth-followup-2026-09-16.md)，以该报告为准。

另有 19 个 JOB 的产品脚本是基础 ps/uname 探测，但 SSH 执行通道与凭据参数可核对；这类不与上述 18 项混计。Dell PowerStore、HP 3PAR 在企业源码中存在，但当前本地 Agent 运行副本缺少对应产物，部署完整性检查仍为 2 项预期失败，需随企业 Agent 打包更新。

## 验证与使用

- 118 项均纳入目录、类型／分类与参数边界测试；116 个需要凭据的入口检查已有凭据解析，2 个无凭据入口跳过该项。测试核对最终节点配置／脚本执行参数，不连接真实设备。
- 前端已验证原表单／有效修正、已有凭据过滤与补充字段、创建／回填／提交；实际本地浏览器复核了用户列举对象以及 Nacos、BMC、Azure。全量自动化结果见下方记录。
- 截图中的“未声明凭据协议”在当前本地构建的指定对象中未复现；完整刷新前曾看到旧端口，刷新后正确。不能仅凭截图断定服务端原因，部署必须同时更新社区前端和企业后端。
- 不新增数据库迁移。更新服务后执行已有 `seed_builtin_types()`，将 platform_api 增加网络分类；不会自动创建真实凭据。网络列表仅列出权限范围内、已存在的该类型凭据。然后重启相关后端并刷新前端。
- Nacos、BMC 的 TLS 修正在企业 Agent 源码，需随 Agent 产物部署；本次没有更新运行节点。存量任务不批量转换，一次性认证继续回显；之前错误选择 network_cli 的任务编辑时改选 platform_api。

初始化命令（服务端环境）：

```sh
python manage.py shell -c "from apps.system_mgmt.services.credential_service import seed_builtin_types; seed_builtin_types()"
```

### 前轮验证记录（本轮结果见下文）

| 检查 | 结果／边界 |
|---|---|
| 社区＋企业后端凭据与节点参数测试 | 1071 通过；2 无凭据入口跳过；2 本地 Agent 产物缺失预期失败 |
| SQLite 基线限制 | `test_list_filters_category_type_search_disabled_and_exact_owner` 的 JSON contains 查询在 SQLite 不支持；完整运行确认该 1 项失败后单独排除，不计通过 |
| 前端组件／表单／Picker | 13 个测试文件，314 项通过；包括非 Network 对象不提交拓扑参数 |
| 企业源采集器 Session/TLS 字段 | 8 项通过（Nacos、server_bmc） |
| TypeScript | type-check 通过 |
| 相关生产前端文件 ESLint | 通过 |
| 主仓库、企业子模块 diff --check | 通过 |

后端验证使用隔离 SQLite 数据库及模拟系统管理解密返回／节点下发边界。系统管理内置类型创建、凭据加密与回显使用真实 ORM。没有对真实设备执行采集。原 18 项中 15 项认证字段已核实、3 项未确认，不因此推导真实采集可用。

可重复的主要命令（仓库根目录）：

```sh
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cmdb-test-local ENABLE_CELERY=true server/.venv/bin/python -m pytest -c server/pytest.ini server/apps/cmdb/tests/test_original_form_vault_contract.py server/apps/cmdb/tests/test_collect_vault_resolver.py server/apps/cmdb/tests/test_collect_model_credential_pool.py server/apps/system_mgmt/tests/test_credential_service.py enterprise/server/apps/cmdb_enterprise/tests/test_new_collect_objects_enterprise_boundary.py enterprise/server/apps/cmdb_enterprise/tests/test_vault_node_params.py --nomigrations --no-cov -k 'not test_list_filters_category_type_search_disabled_and_exact_owner'
pnpm --dir web exec vitest run --maxWorkers=2 'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/__tests__' 'src/components/credential-picker/__tests__'
agents/stargazer/.venv/bin/python -m pytest agents/stargazer/tests/test_enterprise_api_form_fields.py -q
pnpm --dir web type-check
```


## 2026-09-16 全入口复核与开发库内置结果

重新扫描社区 45＋企业 73＝118 个入口，核对 tree、有效一次性表单、统一凭据分类、Stargazer 模块及其父类、执行脚本。上文 118 行是逐入口明细。本轮没有把 JOB 一律改成 SSH 凭据类型；`sql` 仍只是系统管理现有的用户名密码类型 key，实际传输由各插件定义。

### 截图中“无可用内置类型”的实际原因

当前开发库虽有 13 个内置类型，但保留了旧分类；代码分类与持久化分类不一致，导致下列 12 个入口过滤结果为空。已在本地服务端所连接的开发库执行现有 `seed_builtin_types()`，13 个类型定义刷新完成，缺失绑定从 5 组降为 0。自定义类型、真实凭据记录及更新时间检查均未改变；未创建真实凭据、未提交采集任务、未下发到节点。

| 缺失的分类／类型 | 受影响入口 | 处理与确认边界 |
|---|---|---|
| 主机／用户名密码 `host/sql` | Docker、主机、配置文件、物理服务器 JOB、HMC | sql 增加 host 分类；执行通道使用登录账户 |
| 网络／用户名密码 `network/sql` | Brocade FC、Cisco FC | sql 增加 network 分类；按 SSHPlugin 使用设备账号密码 |
| 网络／HTTPS 平台账户 `network/platform_api` | 网络设备配置文件 | platform_api 增加 network 分类；SSH/Telnet、端口及特权密码由任务补充 |
| 存储／SNMP `storage/snmp` | 磁带库、宏杉 | snmp 增加 storage 分类；凭据供版本与认证参数，任务保留端口 |
| 存储／AK/SK `storage/cloud` | IBM DS、XSKY | 旧声明可匹配，但真实认证调用仍未确认；不得按此宣称类型已经核实 |

类型可用不代表该组织已经创建了可选凭据。若选择框正常出现但列表为空，还需该类型下存在有使用权限的凭据；这不同于“插件没有可用的内置类型”。

### Agent 提示的边界

- 原“留空时将走 Agent”错误。Stargazer 根据目标 `node_info` 决定在目标 Agent 执行还是从接入点远程登录；空用户名和密码不会自动安装或接入 Agent。
- 仅 JOB 表单显示执行提示。主机类提示改为“目标主机已接入可用 Agent 时可不填；否则需远程登录账户”。已有凭据模式仍需选中凭据。
- Cisco FC、Brocade FC 单独显示 SSH 设备登录提示，填写说明同样不再提示可留空走 Agent。协议插件不会因为复用 HostTask 就显示 Agent 提示。
- 用户名／密码字段帮助不再笼统标记“可选”。本次没有改变执行器的 Agent 路由或存量任务格式。

### 尚未完成的边界

| 类别 | 逐项对象 | 结论 |
|---|---|---|
| 认证方式待确认 | ZStack、IBM DS、XSKY | 现有源码无真实认证消费；保留旧声明并单独标记，不猜新类型 |
| 认证字段明确、配置采集体缺失 | Couchbase、SAP HANA、IRIS、TongRDS、Ambari、IBM Storwize、EMC Symmetrix、Oracle ZFS、Infinidat | 凭据字段接入已核对，无需因此补新类型；真实采集实现另需补齐 |
| 设备专用采集内容缺失 | 上文标记“基础占位探测”的 19 个 JOB（含两个 FC） | 能确认远程通道参数，不等于已能采出厂商资产 |
| 本地运行副本缺产物 | Dell PowerStore、HP 3PAR | 企业源码存在，运行节点需部署对应 Agent 产物；两项部署检查仍为预期失败 |

### 本轮验证

| 检查 | 结果 |
|---|---|
| 社区＋企业后端 118 入口、转换与下发边界、旧分类升级 | 1092 通过；2 无凭据入口跳过；2 Agent 运行副本缺产物预期失败；1 SQLite JSON contains 基线限制排除 |
| 前端一次性／已有凭据、描述符、Picker、提示范围 | 14 个文件，334 通过；新提示回归先复现 4 项失败，修正后通过 |
| Stargazer 字段读取／节点路由／SNMP／预检 | 159 通过；包括有无 node_info × 未提供／空／非空凭据的 6 个路由用例 |
| TypeScript、相关前端 ESLint | 通过 |
| 当前开发库刷新 | 13 类型；缺失绑定 0；自定义类型和凭据记录保持不变 |
| 本地浏览器 Cisco FC 复现验证 | 刷新后显示设备 SSH 提示；切换已有凭据后正常显示选择器及端口，不再显示缺少内置类型；未创建任务 |

本次无需新增数据库迁移。当前开发库已刷新，不需要再次初始化；其他环境部署后执行上文现有 seed 命令即可。真实设备未联调，企业 Agent 运行副本未覆盖更新。
