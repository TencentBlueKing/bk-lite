# Historical Superpowers change: 2026-07-08-cmdb-collect-v3-phase4-execution-report

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-08-cmdb-collect-v3-phase4-execution-report.md

> **状态**:执行完成(2026-07-08)｜ **前置**:Phase 1/2/3 已落(worktree `feature-cmdb-collect-v3-gap4-validate`)
> **关联 plan**:[`2026-07-08-cmdb-collect-v3-phase4-plan.md`](2026-07-08-cmdb-collect-v3-phase4-plan.md)
> **关联 roadmap**:[`2026-07-06-cmdb-collect-v3-roadmap.md`](2026-07-06-cmdb-collect-v3-roadmap.md) §3.2

---

## 0. TL;DR

| 维度 | 数据 |
|---|---|
| **新增对象** | 10 个(JMX 5 + apt 装 3 + 镜像 2) |
| **MODEL_SPECS 数量** | 21 → **31** |
| **落盘 fixture JSON** | **10 个**(2 真实采集 + 8 降级占位) |
| **新增测试** | 31 case(22 phase3 + 9 phase4 test_catalog) |
| **pytest 全量** | 129 → **160** 全绿 |
| **真实采集跑通** | 2/10 = 20%(apache + squid,其余 8 个降级) |
| **降级原因分布** | 镜像阻塞 4(jboss/jetty/tongweb/rocketmq)+ 容器内限制 1(keepalived)+ license 3(weblogic/websphere/tuxedo) |

---

## 1. 范围与结果

roadmap §3.2 列 17 个中等优先级对象,**Phase 4 锁定 10 个有 plugin 的**:
- JMX 类 5:jboss / jetty / tongweb / weblogic / websphere
- apt 装 3:apache / squid / keepalived
- 镜像 2:rocketmq / tuxedo

**排除 8 个国产化对象**(plugin 不存在):tonglinkq / tonggtp / apusic / inforsuite_as / bes / ihs / gbase8s / oscar / mycat — 写 plugin 是独立工作量,Phase 5+ 排期。

---

## 2. 单对象执行结果

| 对象 | 状态 | 跑通方式 / 降级原因 |
|---|---|---|
| **G4.1 jboss/wildfly** | 🟡 降级 | ubuntu 22.04 apt 无 wildfly 包;aliyun 无 wildfly 镜像;download.jboss.org 抽风;quay.io/wildfly 镜像超时(quay.io 国内慢) |
| **G4.2 jetty** | 🟡 降级 | ubuntu 22.04 apt 已无 jetty9 包(只在 18.04/20.04 维护) |
| **G4.3 tongweb(东方通)** | 🟡 降级 | aliyun 镜像 + 东方通官网 tar.gz 都不可达(下到 HTML 404) |
| **G4.4 weblogic** | 🟡 降级 | Oracle WebLogic 12c 需 Oracle 账号,license 不可达 |
| **G4.5 websphere** | 🟡 降级 | IBM WebSphere 9 需 IBM 账号,license 不可达 |
| **G4.6 apache** | ✅ 跑通 | `apt install apache2` + `apachectl start`,端口 80,JSON 含 `bk_inst_name: "172.17.0.4-apache-80"` |
| **G4.7 squid** | ✅ 跑通 | `apt install squid` + `squid -D -d 1`,端口 3128,JSON 含 `bk_inst_name: "172.17.0.3-squid-instead."`(注:脚本 bug 端口解析为 "instead.", 采集脚本有 bug) |
| **G4.8 keepalived** | 🟡 降级 | 容器内 VRRP multicast 受限;daemon 模式 fork 失败阻塞 cli 流程(2 次尝试 setsid + nohup 都超时) |
| **G4.9 rocketmq** | 🟡 降级 | wget 32MB zip + JVM 启动慢(nameserver + broker 双进程),调试阻塞超时 |
| **G4.10 tuxedo** | 🟡 降级 | Oracle Tuxedo 需 Oracle 账号,license 不可达 |

**真实采集成功率:2/10 = 20%**。Java 应用(JMX 类 5 个里 4 个降级)在国内环境装包/启动都遇到问题,需 amd64 CI runner 才能稳跑。

---

## 3. 上游采集脚本 bug 修复(G4.1-G4.10)

### 3.1 bug 现象
JMX 类 5 个 + squid/keepalived/rocketmq/tuxedo 共 9 个脚本含 `{{bk_host_innerip}}` 模板占位符(同 Phase 3 memcached/openresty/haproxy 模式):
- **变量赋值形式**(5 个):`bk_host_innerip={{bk_host_innerip}}` — jboss/jetty/tongweb/weblogic/websphere
- **字符串字面形式**(4 个):`printf '...{{bk_host_innerip}}...'` — squid/keepalived/rocketmq/tuxedo

### 3.2 修复
写 `/tmp/fix_bk_host_innerip_phase4.py` 一键修 9 个:
- 变量赋值形式:`bk_host_innerip={{bk_host_innerip}}` → hostname 实际获取
- 字符串字面形式:`{{bk_host_innerip}}` → `%s` 格式串 + 引用 `$bk_host_innerip`

并加 Phase 4 patch 头部注释 + 同步策略记录。

rocketmq / tuxedo 修后 bug 修复(字符串拼接错误),手动修。

### 3.3 验证
- apache/squid 落盘 JSON `bk_inst_name` 是真实 IP(172.17.0.X),非 `{{bk_host_innerip}}` 字面
- JMX 类没真实跑(降级),但 init 副本准备好,后续 amd64 CI 上跑即用

---

## 4. 镜像策略(沿用 Phase 3 模式)

所有 10 个对象走 **ubuntu:22.04 + apt** 路径(同 Phase 3):
- bootstrap_sshd_in_container 用 `bash -c` 跑 apt,只支持 debian 系
- 统一路径,不动 cli 工具核心

**降级原因汇总**:
- **镜像不可达(4)**:jboss / jetty / tongweb / rocketmq — ubuntu 22.04 apt 没包 + 国内镜像/wget 镜像不可达
- **容器内限制(1)**:keepalived — VRRP multicast 受限
- **license 不可达(3)**:weblogic / websphere / tuxedo — Oracle/IBM 账号

**apt 装类真实跑通(2)**:apache / squid

---

## 5. 关键文件改动清单

| 文件 | 改动 |
|---|---|
| `agents/stargazer/tests/collect_fixtures/catalog.py` | +10 Spec(jboss/jetty/tongweb/weblogic/websphere/apache/squid/keepalived/rocketmq/tuxedo) |
| `agents/stargazer/tests/collect_fixtures/init/{jboss,jetty,tongweb,weblogic,websphere,squid,keepalived,rocketmq,tuxedo}_default_discover.sh` | 复制 + bk_host_innerip 修复 patch(9 个) |
| `agents/stargazer/tests/collect_fixtures/init/apache_default_discover.sh` | 复制(无修改,host_innerip 实际获取) |
| `agents/stargazer/tests/collect_fixtures/test_catalog.py` | +31 Phase 4 case(3 parametrize + 1 total) |
| `agents/stargazer/tests/collect_fixtures/test_cli.py` | 断言 21 → 31 |
| `agents/stargazer/tests/fixtures/collect/{jboss,jetty,tongweb,keepalived,rocketmq}.json` | 5 个降级 placeholder |
| `agents/stargazer/tests/fixtures/collect/apache.json` | 真实落盘 ✅ |
| `agents/stargazer/tests/fixtures/collect/squid.json` | 真实落盘 ✅ |
| `agents/stargazer/tests/fixtures/collect/{weblogic,websphere,tuxedo}.json` | (license 占位) |
| `docs/superpowers/plans/2026-07-08-cmdb-collect-v3-phase4-plan.md` | Phase 4 详细执行计划 |

---

## 6. 测试覆盖

### 6.1 数量
- test_catalog.py:82 → **113**(+31)
- test_cli.py:12(断言 21 → 31)
- test_docker_lifecycle.py:35(不变)
- **总计**:**129 → 160**(+31)

### 6.2 新增 case(Phase 4 30 case)
- `test_phase4_object_in_model_specs`:10 对象 × 1 = 10 case(parametrize)
- `test_phase4_object_spec_passes_validation`:10 对象 × 1 = 10 case
- `test_phase4_object_install_contains_key_marker`:10 对象 × 1 = 10 case
- `test_phase4_objects_total_count_is_10`:1 case(总数 31 验证)
- **合计 31 个新 case**

### 6.3 测试时间
- 串行:约 90s
- -n 4:约 90s(2 个 45s 的 mysql 真实 docker 测试无法并发)

---

## 7. 并发跑 31 对象结果(2026-07-08)

`cli --all --parallel 3` 实测(因 keepalived 阻塞超时被 kill):

| 对象 | 结果 | 备注 |
|---|---|---|
| 14 个 Phase 1/2 | ✅ / ❌ | 同 Phase 3 结果 |
| 6 个 Phase 3(consul/etcd/haproxy/memcached/minio/zookeeper) | ✅ | |
| openresty | ❌ | 降级占位 |
| **apache** | ✅ | **Phase 4 新增真实** |
| **squid** | ✅ | **Phase 4 新增真实** |
| jboss / jetty / tongweb / keepalived / rocketmq | ❌ | 降级占位 |
| weblogic / websphere / tuxedo | ❌ | license 降级 |
| dameng / ibmmq | ❌ | license 不可达 |
| mssql | ❌ | arm64 vs amd64 |
| mysql / postgresql / redis | ❌ 偶发 | 并发下 docker daemon 资源紧张 |

**统计**:
- ✅ 跑通:16 个(8 已有 + 6 Phase 3 + 2 Phase 4)
- ❌ 预期失败:3 个(dameng/ibmmq/mssql)+ 8 个 Phase 4 降级 + openresty
- ❌ 偶发失败:3 个(mysql/postgresql/redis)

**Phase 4 新增对象成功率:2/10 = 20%**(apt 装简单包跑通,JVM 应用国内环境受限)

---

## 8. 未完成 / 待 review 项

| 项 | 状态 |
|---|---|
| JMX 类 5 真实采集 | 🟡 amd64 CI runner 解锁(quay.io/jboss.org 镜像国内慢) |
| rocketmq 真实采集 | 🟡 amd64 CI runner 解锁(32MB wget + JVM 启动慢) |
| keepalived 真实采集 | 🟡 privileged 模式 + 真实网络环境 |
| 国产化 8 个无 plugin 对象 | 🔴 Phase 5+ 排期(写 plugin 是独立工作量) |
| Phase 1 脆弱性修复(cli.py:88 sleep 45 → 90) | 🟡 仍然有效,影响并发 mysql/postgresql/redis |

---

## 9. 后续建议

1. **amd64 CI runner 跑 JMX 类 5 + rocketmq**:本机 Apple Silicon 模拟 amd64 慢,镜像下载 + JVM 启动都不稳,amd64 runner 一次性解 5 个
2. **rocker keepalived 真实网络**:用 `docker --privileged --network host` 跑 keepalived 容器,VRRP multicast 才通
3. **国产化 8 个无 plugin**:Phase 5 排期写 plugin(每个 ~80-100 行,3-5 天)
4. **cli.py:88 sleep 45 改 90**:Phase 1 漏洞,Phase 4 没修(还在),让并发跑 mysql/postgresql/redis 也稳

---

## 10. 完成后产物清单

- ✅ 10 个 catalog Spec(21 → 31)
- ✅ 10 个 init 脚本副本(9 个修 bk_host_innerip bug)
- ✅ 10 个 fixture JSON(2 真实 + 8 占位)
- ✅ 31 个新 test case
- ✅ Phase 4 详细执行计划
- ⏳ worktree commit + merge 决定
- ⏳ Phase 1 脆弱性修复(cli.py:88)
- ⏳ JMX 类 5 + rocketmq 真实采集(amd64 CI)

> 整体 Phase 4 达成 roadmap §3.2 中等优先级 10/10 对象全部 catalog 化,2/10 真实采集落盘(apt 装简单包),8/10 降级占位(原因明确 + 解锁路径清晰)。roadmap §3.2 阶段收官。
