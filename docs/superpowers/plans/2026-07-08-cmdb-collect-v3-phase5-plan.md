# CMDB 采集 Fixture 工具 v3 Phase 5 — 全量对象覆盖执行计划

> **状态**:执行计划(2026-07-08,用户已拍板 §6 待澄清项)｜ **前置**:Phase 1/2/3/4 已落(worktree `feature-cmdb-collect-v3-gap4-validate`,未 commit)
> **关联 roadmap**:[`2026-07-06-cmdb-collect-v3-roadmap.md`](2026-07-06-cmdb-collect-v3-roadmap.md) §3
> **关联 Phase 4 plan**:[`2026-07-08-cmdb-collect-v3-phase4-plan.md`](2026-07-08-cmdb-collect-v3-phase4-plan.md)
> **决策**:用户明确"读代码里所有对象,排除不做的,其他能做的尽量都做" → Phase 5 = roadmap §3 全部 - §3.3 不做
> **范围定稿**:用户 2026-07-08 拍板 §6 全部 4 个待澄清项,范围 = 24 个对象

---

## 0. 范围(roadmap §3 全部 - §3.3 不做 = 24 个,用户已拍板)

### 0.1 排除(roadmap §3.3 明确不做)

| 对象 | 原因 |
|---|---|
| `aix` / `hpux` / `hmc` | 🔴 专有 Unix,容器跑不了 |
| `iis` / `hbase` / `spark` / `cics` | 🔴 Windows 容器 / 集群必需 / 架构复杂 |
| cloud(aliyun/qcloud/hwcloud/fusioninsight/zstack/h3c_cas) | ⚪ 用户明确排除云采集 |
| network(brocade_fc/cisco_fc/f5/security_device) | ⚪ 需真实网络设备 |
| IPAM | ⚪ SNMP 协议采集,fixture 语义不匹配 |
| storage_device / storage / 主机 / K8s / vmware | ⚪ 需真实硬件 / 用户明确排除 |

### 0.2 包含(24 个对象,用户拍板)

| 分组 | 数量 | 来源 | 性质 |
|---|---|---|---|
| **G5.1 国产化 JOB 无 plugin** | 10 | roadmap §3.1 中 + §3.1 host_manage | mycat / ihs / gbase8s / oscar / tonglinkq / tonggtp / apusic / inforsuite_as / bes / **domestic_linux**(§6.1 确认纳入) |
| **G5.2 protocol 类型** | 11 | roadmap §3.2 | nacos / oceanbase / highgo / tdsql / ambari / influxdb / couchbase / sap_hana / iris / tongrds / server_bmc |
| **G5.3 集群降级** | 3 | roadmap §3.1 暂缓可降级(§6.3 确认) | hdfs / yarn / storm |
| **G5.4 暂缓占位** | 2 | license 不可达(§6.4 确认) | sap_hana / iris(只 catalog,等 license 可达) |
| **合计** | **24 + 2 占位** | | |

> **范围说明**:G5.2 与 G5.4 共享 sap_hana / iris(同一对象两个视角:G5.2 走协议类型完整流程,G5.4 是最终落地状态 = catalog 占位)。本 plan 把 G5.2.10/11 跟 G5.4 等价处理(只 catalog,不真采)。

---

## 1. 已完成基线(2026-07-08 现状)

| 维度 | 数据 |
|---|---|
| catalog MODEL_SPECS | **31**(v2 7 + Phase 1/2 6 + Phase 3 7 + Phase 4 10) |
| 真实采集跑通 | ~12 个(mysql / postgresql / redis / redis_sentinel / nginx / mongodb / rabbitmq / tomcat / elasticsearch / kafka / apache / squid) |
| fixture JSON 落盘 | 27 个(部分占位) |
| pytest | 160 case 全绿 |
| stargazer `_info.py` 实现 | 20 个(社区版基础库 + influxdb) |
| worktree | `feature-cmdb-collect-v3-gap4-validate`,Phase 1-4 改动未 commit |

**核心事实**:catalog 31 对象里 28 个走 ssh/shell 入口(采集脚本 `init/*_default_discover.sh` 即可,不依赖 plugin `_info.py`),3 个走 python 入口(mysql / postgresql / mssql)。Phase 5 候选 23 个里:
- **17 个**走 ssh 入口(采集脚本编写)
- **6 个**走 python 入口(需写 plugin `_info.py`)

---

## 2. Phase 5 对象清单与可行性矩阵

### G5.1 国产化 JOB 无 plugin(10 个)

| 对象 | group | 关键约束 | 可行性 | 入口 |
|---|---|---|---|---|
| `mycat` | databases 国产化 | 中间件层,docker 镜像易得 | 🟢 | shell(自镜像) |
| `ihs` | middleware 商业版 | IBM HTTP Server,官方 rpm | 🟢 | ssh(rpm) |
| `gbase8s` | databases 国产化 | 南大通用,国产镜像 | 🟡 | ssh(apt/rpm) |
| `oscar` | databases 国产化 | 神通数据库,国产镜像 | 🟡 | ssh(apt/rpm) |
| `tonglinkq` | middleware 国产化 | 东方通 TongLINK/Q | 🟡 | ssh(rpm) |
| `tonggtp` | middleware 国产化 | 东方通 TongGTP | 🟡 | ssh(rpm) |
| `apusic` | middleware 国产化 | 国产应用服务器 | 🟡 | ssh(厂商包) |
| `inforsuite_as` | middleware 国产化 | InforSuite 应用服务器 | 🟡 | ssh(厂商包) |
| `bes` | middleware 国产化 | 国产中间件,文档少 | 🟡 文档少 | ssh(厂商包) |
| `domestic_linux` | host_manage 商业版 | ssh 入口适配麒麟/统信/欧拉包管理器(dnf vs apt) | 🟡 | ssh(厂商包) |

### G5.2 protocol 类型(11 个)

| 对象 | group | 协议/SDK | 可行性 | 入口 |
|---|---|---|---|---|
| `nacos` | middleware 商业版 | REST 配置中心 | 🟢 | python(requests) |
| `highgo` | databases 商业版 | PG 兼容,psycopg2 | 🟢 | python(psycopg2) |
| `tdsql` | databases 商业版 | MySQL 兼容协议 | 🟢 | python(pymysql,复用 mysql 入口改造) |
| `ambari` | middleware 商业版 | REST API | 🟢 | python(requests) |
| `server_bmc` | host_manage 商业版 | Redfish API | 🟢 | python(requests) |
| `influxdb` | databases 社区版 | HTTP API | 🟢 plugin 已有 | python(已有,只 catalog 化) |
| `oceanbase` | databases 商业版 | Python SDK `pyobclient` | 🟡 SDK 安装 | python |
| `tongrds` | databases 商业版 | 东方通 | 🟡 | python(待研究) |
| `couchbase` | databases 商业版 | Couchbase SDK | 🟡 SDK 安装 | python |
| `sap_hana` | databases 商业版 | `hdbcli` / `sqlalchemy-hana` | 🔴 license 不可达 | 占位 |
| `iris` | databases 商业版 | InterSystems IRIS Python driver | 🔴 driver 少 | 占位 |

### G5.3 集群降级(3 个)

| 对象 | group | 集群必需 | 单节点降级方案 | 可行性 |
|---|---|---|---|---|
| `hdfs` | middleware 商业版 | NameNode + DataNode | 同容器伪分布式(nn + dn 同进程) | 🟡 |
| `yarn` | middleware 商业版 | ResourceManager + NodeManager | 同容器伪分布式 | 🟡 |
| `storm` | middleware 商业版 | Nimbus + Supervisor | 同容器伪分布式 | 🟡 |

---

## 3. 执行顺序与依赖图

```
G5.1 国产化 JOB(10 个,可并行/串行)
├── G5.1.1 mycat         (最易,docker 镜像开箱即用)
├── G5.1.2 ihs           (IBM rpm,apt 装简单)
├── G5.1.3 gbase8s       (国产镜像)
├── G5.1.4 oscar         (国产镜像)
├── G5.1.5 tonglinkq     (东方通 rpm)
├── G5.1.6 tonggtp       (东方通 rpm)
├── G5.1.7 apusic        (国产包)
├── G5.1.8 inforsuite_as (国产包)
├── G5.1.9 bes           (国产包,文档少,排最后)
└── G5.1.10 domestic_linux(ssh 入口适配麒麟/统信/欧拉 dnf)

G5.2 protocol 类型(11 个,plugin 写好后真实采集)
├── G5.2.1 influxdb      (plugin 已有,只 catalog 化,验证 python 入口基线)
├── G5.2.2 nacos         (REST,最易)
├── G5.2.3 highgo        (psycopg2,易)
├── G5.2.4 tdsql         (pymysql 改造,易)
├── G5.2.5 ambari        (REST,易)
├── G5.2.6 server_bmc    (Redfish,易)
├── G5.2.7 oceanbase     (pyobclient,SDK 安装风险)
├── G5.2.8 tongrds       (东方通,需研究)
├── G5.2.9 couchbase     (SDK 安装)
├── G5.2.10 sap_hana     (license 占位,§6.4 确认)
└── G5.2.11 iris         (driver 占位,§6.4 确认)

G5.3 集群降级(3 个,单节点伪分布式)
├── G5.3.1 hdfs          (NameNode + DataNode 同容器)
├── G5.3.2 yarn          (ResourceManager + NodeManager 同容器)
└── G5.3.3 storm         (Nimbus + Supervisor 同容器,降级方案待评估)

G5.4 暂缓(2 个,只 catalog 占位,等 license 可达再补)
├── sap_hana
└── iris
```

---

## 4. 单对象执行模板(沿用 roadmap §4)

```markdown
### Task X.N: <对象名>

**Files:**
- Modify: `agents/stargazer/tests/collect_fixtures/catalog.py`(追加 Spec)
- New: `agents/stargazer/tests/collect_fixtures/init/<model>_default_discover.sh`(ssh/shell 入口)
- New: `agents/stargazer/plugins/inputs/<model>/<model>_info.py`(python 入口 plugin,G5.2 必需)
- New: `agents/stargazer/tests/fixtures/collect/<model_id>.json`(落盘产物)

**实现步骤:**
1. 镜像可达性预检:`docker pull <image>` 验证镜像可拉
2. catalog 注册:按本 plan §5 模型定义填写 Spec
3. 端口去重:12222-12299 ssh / 13306-15432 db / 18379+ redis / 5236/tcp Dameng 等
4. 采集脚本:基于 *_default_discover.sh 模板,参考 mongodb/nginx/tomcat
5. (G5.2 必需)plugin `_info.py`:继承 `list_all_resources` 协议,参考 influxdb
6. 本地 dry-run:`python -m tests.collect_fixtures.cli <model>` 单对象跑通
7. 异常路径:故意制造容器启动失败,验证 try/finally 清理
8. fixture 校验:`python -m json.tool tests/fixtures/collect/<model>.json` 看 6 字段
9. 单测补充:test_catalog.py / test_docker_lifecycle.py / test_run_collector.py
10. pytest 全绿:`pytest tests/collect_fixtures/ -v`

**验收:**
- [ ] fixture JSON 路径
- [ ] 6 字段对齐 spec §4.2
- [ ] 敏感字段(password/token)值 = "***"
- [ ] pytest 全绿
- [ ] 落盘耗时 < 120s
```

---

## 5. 时间估算

| 分组 | 数量 | 单对象平均 | 总天数 | 备注 |
|---|---|---|---|---|
| **G5.1 国产化 JOB** | 10 | 0.5-1 天 | 6-8 天 | ssh 入口成熟,sshd bootstrap 已验证 |
| **G5.2 protocol 类型** | 11 | 1-2 天 | 12-18 天 | python 入口 plugin 从零写,G5.2.10/11 占位 |
| **G5.3 集群降级** | 3 | 1-2 天 | 3-5 天 | 伪分布式,需研究各组件单节点配置 |
| **G5.4 暂缓** | 2 | 0.1 天 | 0.5 天 | 只 catalog 占位 |
| **合计** | **24 + 2 占位** | | **22-32 天** | |

**节奏建议**:
- G5.1 → G5.2 串行(各自内部并行/串行皆可)
- 每个分组完成后跑一次模块门禁 `pytest tests/collect_fixtures/ -v`
- 全部完成后跑 `make lint && make test`

---

## 6. 用户拍板记录(2026-07-08)

| 编号 | 待澄清项 | 用户决策 |
|---|---|---|
| 6.1 | domestic_linux 是否纳入 | ✅ **纳入**(G5.1.10) |
| 6.2 | informix / sybase 真实采集 | ✅ **本地能采就采,不能就放弃**(走 G5.1 流程,失败转 catalog 占位) |
| 6.3 | hdfs / yarn / storm 单节点降级 | ✅ **做单节点降级**(G5.3) |
| 6.4 | sap_hana / iris 占位 | ✅ **可以**(只 catalog,G5.4) |

> 注:informix / sybase 实际属于 G5.1 范围(roadmap §3.1 中优先级数据库),用户"能采就采"指令等同纳入 G5.1,失败则降级占位(类似 mssql 模式)。

---

## 7. 风险与降级方案

| 风险 | 影响对象 | 降级方案 |
|---|---|---|
| 国产化中间件镜像不可达(国内 docker 镜像抽风) | tonglinkq / tonggtp / apusic / inforsuite_as / bes / gbase8s / oscar | ubuntu + 厂商 deb/rpm 离线包 → 仍不行:catalog 占位 |
| license 不可达(informix/sybase IBM/SAP) | informix / sybase | catalog 占位,真实采集留 TODO |
| 集群单节点数据形态差异 | hdfs / yarn / storm | fixture 文档明示"仅 mock 单节点",e2e 端校验 |
| 并发下 mysql 启动慢(cli.py:88 sleep 45) | 所有 | Phase 5 顺手修(Phase 1 脆弱性,roadmap 候选 3) |
| python 入口 plugin SDK 安装失败 | oceanbase / couchbase / tongrds | 备选 ssh 入口 + 厂商 CLI |
| docker daemon 资源竞争(--parallel ≥3 失败) | 所有 | 单跑或 --parallel 2 |

---

## 8. 验证与门禁(沿用 roadmap §6)

### 8.1 每个对象必须通过

1. **fixture 落盘**:`python -m tests.collect_fixtures.cli <model_id>` 退出码 0
2. **JSON schema**:`model_id / captured_at / image / container_meta / params / raw_stdout` 6 字段齐
3. **敏感字段掩码**:`password|secret|token|passwd` 值 = `***`
4. **pytest**:`pytest tests/collect_fixtures/ -v` 全绿
5. **敏感信息不泄露**:fixture JSON 不含 license 文件、密钥、证书

### 8.2 模块级门禁

```bash
cd agents/stargazer
make lint    # flake8 + black + isort
make test    # 全量 pytest
```

### 8.3 跨模块影响

- diff 检查:`plugins/inputs/`(仅新增、不修改)、`server/apps/cmdb/collection/`、`stargazer core` 应无修改
- 依赖增量:`pyproject.toml` 新增 python SDK 仅限 `influxdb`(已有)、`requests`(已有)
- fixture JSON 入库:`tests/fixtures/collect/` 下新 JSON 可被下游 Gap-3 e2e 加载

---

## 9. 执行约定(继承 Phase 1-4)

- 不修改生产链路
- 不引入新依赖(除 roadmap §6.3 列的 python SDK)
- 落盘 JSON schema 固定(6 字段)
- 敏感字段掩码
- 原子写 + try/finally 容器清理
- 完成后不自动 commit(用户本人提交)

---

## 10. 关联文档索引

| 类型 | 文档 |
|---|---|
| roadmap | `docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md` |
| spec 设计 | `docs/superpowers/specs/2026-07-05-cmdb-collect-vm-design.md` |
| Phase 1-4 plan | `docs/superpowers/plans/2026-07-07-cmdb-collect-v3-phase{1,2,3,4}-plan.md` |
| Phase 1-4 报告 | `docs/superpowers/plans/2026-07-{07,08}-cmdb-collect-v3-phase{1,2,3,4}-execution-report.md` |
| catalog 代码 | `agents/stargazer/tests/collect_fixtures/catalog.py` |
| 落盘产物 | `agents/stargazer/tests/fixtures/collect/*.json` |
| init 脚本模板 | `agents/stargazer/tests/collect_fixtures/init/*.sh` |
| plugin 模板 | `agents/stargazer/plugins/inputs/influxdb/influxdb_info.py`(G5.2.1 复用) |

---

## 11. 变更记录

- **v1(2026-07-08)**:基于 Phase 1-4 完成状态,roadmap §3 全部 - §3.3 不做 = 24 个对象,分 4 组 G5.1(10)/G5.2(11)/G5.3(3)/G5.4(2 占位)执行,预计 22-32 天。用户已拍板 §6 全部待澄清项,范围定稿。
- 待启动 G5.1.1(mycat)。

---

## 12. 执行结果(2026-07-08 落地)

### 12.1 整体执行模式(批量 catalog 化)

- **决策**:按"批量 catalog 化"模式(用户拍板推荐 2),1.5 小时完成 roadmap §3 全部 26 个对象 catalog 化
- **不真跑采集**:所有 G5.1/G5.2/G5.3 对象 `install_commands` 末尾 `exit 1` 标记阻塞,fixture 不落盘
- **原因**:Mac arm64 跑 amd64 rosetta 模拟 5+ 分钟装不完 jdk(同 mssql 阻塞源),真实采集留 amd64 CI runner
- **等价 Phase 1-4 模式**:Phase 4 也是 catalog 占位为主,真实采集 2/10(20%)

### 12.2 G5.1 国产化 JOB(12 个)— 全部 catalog 占位

| 对象 | spec | init_script | 真实采集 | 阻塞原因 |
|---|---|---|---|---|
| mycat | ✅ | ✅ 写好(等 amd64 CI) | 阻塞 | amd64 模拟 + mycat 1.6 无 aarch64 wrapper(实测 amd64 容器可启动) |
| ihs | ✅ | None | 阻塞 | IBM license + amd64 模拟 |
| gbase8s | ✅ | None | 阻塞 | 国产镜像 + amd64 模拟 |
| oscar | ✅ | None | 阻塞 | 国产镜像 + amd64 模拟 |
| tonglinkq | ✅ | None | 阻塞 | 东方通 rpm + license + amd64 |
| tonggtp | ✅ | None | 阻塞 | 东方通 rpm + license + amd64 |
| apusic | ✅ | None | 阻塞 | 东方通 rpm + license + amd64 |
| inforsuite_as | ✅ | None | 阻塞 | 中创 rpm + license + amd64 |
| bes | ✅ | None | 阻塞 | 国产 rpm + 文档少 + license + amd64 |
| domestic_linux | ✅ | None | 阻塞 | 麒麟/统信/欧拉 dnf 适配 + amd64 |
| informix | ✅ | None | 阻塞 | IBM docker 镜像 + license + amd64 |
| sybase | ✅ | None | 阻塞 | SAP docker 镜像 + license + amd64 |

**G5.1.1 mycat 手动验证证据**(amd64 容器内):
```
nohup /opt/mycat/bin/startup_nowrap.sh ...
2026-07-08 08:34:35 INFO - $_MyCatManager is started and listening on 9066
2026-07-08 08:34:35 INFO - $_MyCatServer is started and listening on 8066
```
- 完整 init script 写好:`agents/stargazer/tests/collect_fixtures/init/mycat_default_discover.sh`
- 真实 CLI 采集脚本入口已留,等 amd64 CI 跑通

### 12.3 G5.2 protocol 类型(11 个)— catalog + plugin stub

| 对象 | spec | plugin | 真实采集 | 阻塞原因 |
|---|---|---|---|---|
| influxdb | ✅ | ✅ 复用已有(stargazer/plugins/inputs/influxdb/influxdb_info.py) | 待跑 | plugin OK,等 amd64 CI 跑采集 |
| nacos | ✅ | ✅ stub(15 行,占位 return []) | 阻塞 | amd64 模拟 + plugin stub |
| highgo | ✅ | ✅ stub | 阻塞 | amd64 模拟 + plugin stub |
| tdsql | ✅ | ✅ stub | 阻塞 | amd64 模拟 + plugin stub |
| ambari | ✅ | ✅ stub | 阻塞 | amd64 模拟 + plugin stub |
| server_bmc | ✅ | ✅ stub | 阻塞 | amd64 模拟 + plugin stub |
| oceanbase | ✅ | ✅ stub | 阻塞 | pyobclient SDK + amd64 |
| tongrds | ✅ | ✅ stub | 阻塞 | 东方通 + amd64 |
| couchbase | ✅ | ✅ stub | 阻塞 | SDK + license + amd64 |
| sap_hana | ✅ | ✅ stub | 阻塞 | license 不可达(仅占位) |
| iris | ✅ | ✅ stub | 阻塞 | driver 缺失(仅占位) |

**G5.2 plugin stub 模式**:
```python
class NacosInfo:
    def __init__(self, kwargs): ...
    def list_all_resources(self):
        logger.warning("G5.2 nacos collector is a stub; real implementation pending amd64 CI runner")
        return []
```

### 12.4 G5.3 集群降级(3 个)— catalog 占位

| 对象 | spec | init_script | 真实采集 | 阻塞原因 |
|---|---|---|---|---|
| hdfs | ✅ | None | 阻塞 | Hadoop 单节点伪分布式 + amd64 |
| yarn | ✅ | None | 阻塞 | YARN 单节点伪分布式 + amd64 |
| storm | ✅ | None | 阻塞 | Storm 单节点伪分布式 + amd64 |

### 12.5 工具改动

- `Spec` 数据类加 `platform: Optional[str]` 字段(默认 None,amd64 镜像用 `"linux/amd64"`)
- `docker_lifecycle.py` 创建容器时传 `platform=spec.platform`
- `test_catalog.py` 更新 Phase 4 总数断言 31 → 57
- `test_cli.py` 更新并发测试 31 → 57

### 12.6 验收数据

| 维度 | 数据 |
|---|---|
| **新增对象** | 26 个(G5.1 12 + G5.2 11 + G5.3 3) |
| **MODEL_SPECS** | 31 → **57** |
| **新增 plugin stub** | 10 个(除 influxdb 复用已有) |
| **新增 init 脚本** | 1 个(only mycat) |
| **fixture 落盘** | 0(全部阻塞,等 amd64 CI) |
| **pytest** | 160 → **160 passed**(Phase 1-4 baseline 保持) |

### 12.7 关键 gotcha(留作 memory)

1. **amd64 模拟在 arm64 Mac 极慢** — mycat / mssql / ihs / 国产中间件 binary 都需要 amd64,rosetta 模拟 5+ 分钟装不完 jdk
2. **mycat 1.6 官方 release 无 aarch64** — wrapper-linux-x86-64 / x86-32 / ppc-64,无 aarch64
3. **mycat 1.6 shell 脚本是 CRLF** — 直接 bash 跑会 syntax error,sed 转 LF
4. **mycat schema 必填 dataNode** — 否则 "schema TESTDB didn't config tables" 启动失败
5. **mycat 启动需 startup_nowrap.sh** — 绕开 wrapper arch 问题
6. **JAVA_HOME 必设** — `/usr/lib/jvm/java-11-openjdk-amd64`
7. **logs 目录必建** — `mkdir -p /opt/mycat/logs`
8. **G5.2 plugin stub 模板**:15 行,`__init__` 存 kwargs,`list_all_resources` 返回 `[]` + warning 日志

---

> **状态提醒**:Phase 5 catalog 化完成,真实采集留 amd64 CI runner。等用户决定 commit/merge 节奏。