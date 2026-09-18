# 18 个入口的 Stargazer 认证补查与修正

日期：2026-09-16。本报告修正上一轮仅凭企业目录占位类得出“18 项无法确认”的结论。此次同时检查社区 Stargazer 原始配置采集类、企业插件清单、存储 monitor_plugins 及对应采集任务；也只读核对了另一份本地企业仓库，未发现 ZStack/XSKY 的真实配置采集实现。

结论：**15 项已有认证依据并补齐字段接入；其中 6 项复用现有实际采集调用，9 项只具备认证参数契约、配置采集实现仍缺失。剩余 3 项的具体认证路径尚未确认。** 参数测试通过不等同于真实设备采集通过。本次不新增凭据类型，复用已内置的用户名密码、SNMP、平台账户。

## 逐项依据与结果

| 对象 | Stargazer 依据 | 凭据／一次性认证字段 | 动态参数／默认端口 | 修正及真实能力边界 |
|---|---|---|---|---|
| ZStack `zstack` | [源码](../enterprise/agents/stargazer/enterprise/plugins/inputs/zstack/zstack_info.py) | 未确认；保留旧声明，不计为字段接入完成 | 端口；8080 | 仅占位类，缺真实 API 认证调用 |
| F5 `f5` | [源码](../agents/stargazer/plugins/inputs/network/snmp_facts.py) | SNMP `snmp` → version/community 或 V3 用户、安全级别、算法与密钥 | 端口；161 | 复用 SnmpFacts；已有凭据不重复填写认证字段；保留端口 |
| 安全设备 `security_device` | [源码](../agents/stargazer/plugins/inputs/network/snmp_facts.py) | SNMP `snmp` → version/community 或 V3 用户、安全级别、算法与密钥 | 端口；161 | 复用 SnmpFacts；已有凭据不重复填写认证字段；保留端口 |
| Couchbase `couchbase` | [源码](../agents/stargazer/plugins/inputs/couchbase/couchbase_info.py) | 用户名密码 `sql` → `user/password` | bucket（可选）；8091 | 继承原生字段读取；原生采集体仍是 stub，明确报未实现 |
| SAP HANA `sap_hana` | [源码](../agents/stargazer/plugins/inputs/sap_hana/sap_hana_info.py) | 用户名密码 `sql` → `user/password` | 端口；30015 | 继承原生字段读取；原生采集体仍是 stub，明确报未实现 |
| InterSystems IRIS `iris` | [源码](../agents/stargazer/plugins/inputs/iris/iris_info.py) | 用户名密码 `sql` → `user/password` | namespace（默认 USER）；1972 | 继承原生字段读取；原生采集体仍是 stub，明确报未实现 |
| TongRDS `tongrds` | [源码](../agents/stargazer/plugins/inputs/tongrds/tongrds_info.py) | 用户名密码 `sql` → `user/password` | 端口；6379 | 继承原生字段读取；原生采集体仍是 stub，明确报未实现 |
| TDSQL `tdsql` | [源码](../agents/stargazer/plugins/inputs/tdsql/tdsql_info.py) | 用户名密码 `sql` → `user/password` | 端口；3306 | 复用原生 TDSQL 的 pymysql 连接 |
| IBM Storwize `ibm_storwize` | [源码](../enterprise/agents/stargazer/enterprise/monitor_plugins/swiz/api.py) | 平台账户 `platform_api` → `username/password` | verify_tls；7443 | 从错误 AK/SK 改为平台账户；依据监控认证实现补参数读取，CMDB 配置采集体仍未实现 |
| IBM DS `ibm_ds` | [源码](../enterprise/agents/stargazer/enterprise/plugins/inputs/ibm_ds/ibm_ds_info.py) | 未确认；保留旧声明，不计为字段接入完成 | 端口；443 | 仅占位类；DS5K/DS8000 管理机路径不同，不能直接把管理机 SSH 认证等同于阵列认证 |
| EMC Symmetrix `emc_symmetrix` | [源码](../enterprise/agents/stargazer/enterprise/monitor_plugins/vmax/api.py) | 平台账户 `platform_api` → `username/password` | verify_tls；8443 | 从错误 AK/SK 改为平台账户；依据监控认证实现补参数读取，CMDB 配置采集体仍未实现 |
| 宏杉存储 `macrosan` | [源码](../enterprise/agents/stargazer/enterprise/monitor_plugins/macrosan/api.py) | SNMP `snmp` → version/community 或 V3 用户、安全级别、算法与密钥 | 端口；161 | 从错误 AK/SK 改为 SNMP；复用 SnmpFacts 的基础系统信息采集 |
| NetApp Cluster `netapp_cluster` | [源码](../agents/stargazer/plugins/inputs/netapp_ontap/netapp_ontap_info.py) | 平台账户 `platform_api` → `username/password` | verify_tls；443 | 从 AK/SK 改为平台账户，复用 ONTAP REST 实现；输出 netapp_cluster 结果 key |
| Oracle ZFS `oraclezfs` | [源码](../enterprise/agents/stargazer/enterprise/monitor_plugins/oraclezfs/api.py) | 平台账户 `platform_api` → `username/password` | verify_tls；215 | 从错误 AK/SK 改为平台账户；依据监控认证实现补参数读取，CMDB 配置采集体仍未实现 |
| Infinidat `infinidat` | [源码](../enterprise/agents/stargazer/enterprise/monitor_plugins/infinibox/api.py) | 平台账户 `platform_api` → `username/password` | verify_tls；443 | 从错误 AK/SK 改为平台账户；依据监控认证实现补参数读取，CMDB 配置采集体仍未实现 |
| 磁带库 `tape_library` | [源码](../agents/stargazer/plugins/inputs/network/snmp_facts.py) | SNMP `snmp` → version/community 或 V3 用户、安全级别、算法与密钥 | 端口；161 | 复用 SnmpFacts；已有凭据不重复填写认证字段；保留端口 |
| XSKY `xsky` | [源码](../enterprise/agents/stargazer/enterprise/plugins/inputs/xsky/xsky_info.py) | 未确认；保留旧声明，不计为字段接入完成 | 端口；443 | 仅占位类；没有可确认的 API/Token/AKSK 消费代码 |
| Ambari `ambari` | [源码](../agents/stargazer/plugins/inputs/ambari/ambari_info.py) | 用户名密码 `sql` → `user/password` | port → ambari_port；8080 | 继承原生字段读取；原生采集体仍是 stub，明确报未实现 |

Couchbase 8091、TongRDS 6379 来自各自插件清单的 target_policy；SAP HANA 30015、IRIS 1972、Ambari 8080 来自原生构造器。Storwize 7443、VMAX 8443、Oracle ZFS 215 有对应监控配置／测试证据。用户实际部署端口仍可覆盖。

## 已修正的具体问题

1. 企业同名空实现覆盖了社区原始字段读取；TDSQL 还覆盖了已有 pymysql 采集。现在恢复复用，账号从统一凭据 `username` 转为原始 `user`，端口和可选参数继续来自任务。
2. 宏杉实际现有实现使用 SNMP，不是 AK/SK；Storwize、EMC Symmetrix、NetApp Cluster、Oracle ZFS、InfiniBox 的现有实现使用平台账号，也不是 AK/SK。
3. Ambari 页面此前是 SSH 22，但原始参数为 API 账户及 ambari_port 8080；已修正页面、NodeParams 和插件预检策略。IRIS namespace 与 Couchbase bucket 在一次性认证、已有凭据两种模式均保留并下发。
4. SNMP V3 的凭据库安全级别为小写，旧 SnmpFacts 按驼峰比较；且旧校验强制所有 V3 模式填写两种密钥。现已统一大小写，并按 noAuthNoPriv／authNoPriv／authPriv 分别校验和构建认证对象。
5. F5、安全设备、磁带库、宏杉的企业元数据补齐 community/authkey/privkey 加密声明；使用真实 ORM 验证存储加密、解密和 API 掩码。
6. F5、宏杉使用 SNMP 预检；相关异步插件明确 execution_mode。SAP HANA、IRIS、Storwize、EMC 等的 plugin.yml 默认端口与表单同步。
7. 无实际采集体的入口明确报 NotImplementedError，不再把传入地址拼成一条“成功采集”的虚构资产。对 3 项未确认认证契约的入口也明确失败，避免继续误报成功。

## 还缺什么

- **9 项认证字段已确认、采集体未实现**：Couchbase、SAP HANA、IRIS、TongRDS、Ambari、IBM Storwize、EMC Symmetrix、Oracle ZFS、Infinidat。无需因此新增凭据类型；本次字段接入已补，真实产品采集还需要实现和设备验证。
- **3 项认证路径仍未确认**：ZStack、IBM DS、XSKY。IBM DS 需明确 DS5K／DS8000 的具体系列和管理机接入方式；ZStack／XSKY 需要真实配置采集源码或确认使用的 API 认证契约。当前目录只有占位代码，不能因补上几个属性就声称已确认。
- 用户如指另一份 Stargazer 代码，应给出该源码本地路径；本次未从产品名称猜测 Token、AK/SK 或设备密码。

## 验证与部署

新鲜验证结果见下方最终记录。对 15 项逐一构造真实源采集类并验证字段读取；TDSQL 核对真实连接调用参数，NetApp 核对实际 HTTP auth 调用，SNMP 核对 V2/V3 安全对象及结果映射。Server 测试覆盖凭据引用解析、附加字段、秘密环境变量与全 118 项目录边界；未连接真实设备。

本次不新增 migration，不新增内置凭据 key。需同时部署社区前端、社区后端、企业后端和包含这些源插件的 Stargazer 产物。当前 `agents/stargazer/enterprise` 是另一份运行副本，本次没有用全量复制覆盖它。之前错误填写 AK/SK 的宏杉任务需要改填 SNMP；其他改为平台账户的入口需选择正确类型，旧一次性账户别名按现有回显逻辑保留。

### 最终验证记录

| 检查 | 新鲜结果 |
|---|---|
| 社区＋企业后端全 118 项凭据／节点参数回归 | 1091 通过；2 无凭据入口跳过；2 企业 Agent 本地运行副本产物缺失预期失败；1 SQLite JSON contains 基线测试排除 |
| 前端表单／Picker／描述符 | 13 文件，330 通过 |
| Stargazer 原始字段、SNMP 条件认证、连接参数、预检策略 | 129 通过 |
| 旧企业插件注册及未实现状态回归 | 2 通过 |
| TypeScript 类型检查 | 通过 |
| 修改的生产前端文件 ESLint | 通过 |
| 主仓库及企业子模块 diff --check | 通过 |

Agent 验证命令（在 `agents/stargazer` 执行）：

```sh
.venv/bin/python -m pytest tests/test_enterprise_credential_readers.py tests/test_enterprise_placeholder_collectors.py tests/test_snmp_facts_probe.py tests/test_snmp_connectivity_check.py tests/test_enterprise_api_form_fields.py tests/test_collection_request_builder.py tests/test_yaml_target_policy.py tests/test_remaining_collect_objects_plugins.py -q
```

新增源码读取测试显式加载 `enterprise/agents/stargazer/enterprise`，避免误测忽略目录中的旧运行副本。各项测试均使用虚构凭据及模拟请求，不访问真实设备；未执行生产凭据初始化或更新运行节点。
