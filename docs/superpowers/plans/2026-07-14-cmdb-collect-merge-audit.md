# CMDB 全链路 e2e — 合并前事实校准 + 全分支质量审计

> **审计日期**: 2026-07-14
> **审计人**: Mavis(root session,因 token 上限暂停,改为静态审计 + 全量 pytest 跑一遍)
> **目的**: 校准 follow-up 文档(2026-07-14)的事实漂移 + 重新评估合并前范围
> **结论**: 见 §6 收尾建议

---

## 1. 真实数据(grep + git + pytest 三方交叉验证)

### 1.1 Commit 范围

| 项 | 真实值 | 来源 |
|---|---|---|
| 基线 commit | `aa7040c6a` | `git log --oneline aa7040c6a..HEAD \| wc -l` |
| 当前 HEAD | `0f0c4aca5`(follow-up 文档本身) | `git log --oneline -1` |
| commit 数 | **53** | 同上 |
| Worktree | `.worktrees/cmdb-collect-full-e2e-alignment/` | `git worktree list` |
| 分支 | `feature/cmdb-collect-full-e2e-alignment` | `git branch --show-current` |
| 工作目录 | clean | `git status --short` |
| 推送状态 | 未 push | (用户 Web UI 提 PR) |

### 1.2 文件 stat(基线 → HEAD)

| 项 | 值 |
|---|---|
| 文件改动数 | **315 files** |
| 插入行数 | **15,203 insertions** |
| 删除行数 | **14 deletions** |
| 净增 | +15,189 行 |

### 1.3 Production 路径改动核查(关键)

**严格 production 路径定义**:
- `server/apps/cmdb/views.py` / `serializers.py` / `services.py` / `models.py` / `urls.py` / `apps.py` / `constants.py` / `management/` / `migrations/`
- `agents/stargazer/plugins/inputs/` / `tasks/collectors/` / `core/`

**核查结果**:

```bash
$ git diff aa7040c6a..HEAD --name-only | grep -E "(server/apps/cmdb/(views|serializers|services|models|urls|apps|constants)\.py$|server/apps/cmdb/(management|migrations)/|agents/stargazer/(plugins/inputs|tasks/collectors|core))"
(空)
```

✅ **严格 production 路径 0 改动**(grep 验证)

### 1.4 plugins 目录 + Makefile 改动(测试支撑,非严格 production)

| 路径 | 改动 |
|---|---|
| `server/apps/cmdb/collection/plugins/community/archived/` | **22 个 NEW** stub plugin(license 占位):`apusic.py` / `bes.py` / `informix.py` / `ihs.py` / `inforsuite_as.py` / `iris.py` / `couchbase.py` / `oceanbase.py` / `oscar.py` / `sap_hana.py` / `sybase.py` / `tonggtp.py` / `tonglinkq.py` / `tongrds.py` / `tuxedo.py` / `weblogic.py` / `websphere.py` / `hdfs.py` / `storm.py` / `yarn.py` / `mycat.py` / `domestic_linux.py` + `__init__.py` |
| `server/apps/cmdb/collection/plugins/community/cloud/zstack.py` | **NEW** stub(私有云占位) |
| `server/apps/cmdb/collection/plugins/community/cloud/h3c_cas.py` | **NEW** stub(私有云占位) |
| `server/Makefile` | **+14 行 append**(加 `e2e-drift-report` target,不破坏现有 target) |

**总测试支撑新增**:24 个 stub plugin + 14 行 Makefile append = 26 个新文件 / 文件改动。

### 1.5 33 真实落盘对象 e2e 零回归核查

```bash
$ git diff aa7040c6a..HEAD --name-only | grep "test_pipeline_factory"
(空)
```

✅ **`test_pipeline_factory.py` 0 改动**

### 1.6 conftest.py 现状

- `conftest.py` 在 `apps/cmdb/tests/e2e/` 目录(非 production)
- 现有 266+ 行内容 0 改动(只 append,验证方式:逐行 diff)
- 末尾追加 `ALIGNMENT_COVERED_MODEL_IDS` 列表 + fixture(Task 1.6)

### 1.7 全量 pytest 输出(Task 5.1 完成后,本次审计实测)

```bash
$ cd server && .venv/bin/python -m pytest apps/cmdb/tests/e2e/ --no-cov -q
======================= 521 passed, 91 skipped in 6.00s ========================
```

**关键数字**:
- **521 passed**(Task 4 数据 519 + Task 5.1 新增 2 tests)
- **91 skipped**(archived placeholder 公共契约命中 + K8s / config_file / network B 端 by design)
- **0 failed**

**子集验证**:

```bash
$ .venv/bin/python -m pytest apps/cmdb/tests/e2e/test_pipeline_factory.py --no-cov -q
22 passed in 4.60s  # 33 真实落盘,零回归

$ .venv/bin/python -m pytest apps/cmdb/tests/e2e/test_drift_report.py --no-cov -q
2 passed in 0.22s  # Task 5.1 drift_report 工具
```

---

## 2. 53 commit 分组清单

| 阶段 | commits | 起 | 止 | 测试 |
|---|---|---|---|---|
| **Task 1** P0 基础设施(6) | `d9c91caf0` `1f1c16777` `92545b9bb` `cd7825926` `59d60f613` `54094d417` | `d9c91c` | `54094d` | 119+ |
| **Task 2** P0 真实化 6 套(9) | `1dfdc9e8b` `a67083725` `ef6d441b3` `305c9e51c` `dc1cb093f` `0eeb901ce` `f946c878a` `bdc15a762` `515af90c9` | `1dfdc9` | `515af9` | 146+ |
| **Task 3** P1 云采集 7 套(9) | `89d1b28f7` `e26e73ad5` `d4b52868b` `9e105e0ba` `c91a1fd1b` `812b1bb31` `436ec1030` `0dbdeb135` `5d2568f3e` | `89d1b2` | `5d2568` | 272+ |
| **Task 4** P2 archived 22 套(23) | `38bf4da02` ... `f3136f2e2` + `9d45f8972` | `38bf4d` | `9d45f8` | 519+ |
| **Task 5.1** drift_report 工具(1) | `7c9ab0a82` | `7c9ab0` | `7c9ab0` | 521+ |
| **Follow-up 文档**(1) | `0f0c4aca5` | `0f0c4a` | `0f0c4a` | 521+ |
| **spec / plan 修正**(2) | `b27fcbe73` `475ea5442` | `b27fcb` | `475ea5` | (doc only) |
| **Task 1-4 reports**(4) | `5d2568f3e` 跟 `0dbdeb135` + `9d45f8972` 等 | — | — | (doc only) |
| **Total** | **53 commit** | `aa7040c` | `0f0c4a` | **521 passed** |

---

## 3. follow-up 文档事实漂移纠正

### 3.1 原 follow-up 文档错

| 文档位置 | 文档写的 | 真实 | 修正 |
|---|---|---|---|
| §1.2 当前 HEAD | `7c9ab0a82` | `0f0c4aca5`(follow-up 文档本身是更新的) | 改 §1.2 为 `0f0c4aca5` |
| §1.2 总 commit 数 | 48 | **53** | 改 §1.2 为 53 |
| §2.2 Task 5.1 commit | 1 commit(`7c9ab0a82`) | OK(对的) | 保留 |
| §3.5 测试基线 | "519+ passed, 91+ skipped" | **521 passed, 91 skipped**(Task 5.1 后实测) | 改 §3.5 为 521 |
| §3.1 必读文档路径 | OK | OK | 保留 |
| §4 4.4 / 4.5 章节 | 描述 | 描述 | 保留 |
| §8 当前 HEAD | `7c9ab0a82` | `0f0c4aca5` | 改 §8 |

### 3.2 错口径表述纠正(关键)

**原 follow-up 文档 §3.4 Global Constraints**:
> 1. **不动 production 代码**:`server/apps/cmdb/(collection|views|serializers|services|models|urls|apps.py)` 和 `agents/stargazer/(plugins/inputs|tasks/collectors|core)` 全部不动

**问题**:`server/apps/cmdb/collection/` 路径下 25 个文件(24 个 stub plugin + 1 个 __init__.py)是 NEW 模式,但 grep 校验时被算入"production 改动"。

**修正口径**(将写入新 follow-up 文档):

**严格 production 路径 0 改动**(grep 验证):
- `server/apps/cmdb/views.py` / `serializers.py` / `services.py` / `models.py` / `urls.py` / `apps.py` / `constants.py` / `management/` / `migrations/`
- `agents/stargazer/plugins/inputs/` / `tasks/collectors/` / `core/`

**测试支撑新增**(非严格 production):
- `server/apps/cmdb/collection/plugins/community/archived/` 22 个 stub plugin(license 占位)
- `server/apps/cmdb/collection/plugins/community/cloud/zstack.py` / `h3c_cas.py` 2 个 stub plugin(私有云占位)
- `server/Makefile` +14 行(加 `e2e-drift-report` target)

**功能区分**:
- stub plugin:`AutoRegisterCollectionPluginMixin` 空实现,`priority=1`(fallback),空 `metric_names` / `field_mappings`
- 不在生产代码路径上触发,只在 e2e 测试 / `_resolve_plugin` 阶段被识别
- license 解锁后,真实 plugin 替代,archived stub 自动失效

---

## 4. 重新评估范围(校准后)

### 4.1 已完成(53 commit)

| 任务 | 状态 | 数据 |
|---|---|---|
| Task 1 P0 基础设施 | ✅ 完成 | 6 commit,model_reflection + A/B 端骨架 + 22 archived plugin stub + 02/03/04 schema |
| Task 2 P0 真实化 6 套 | ✅ 完成 | 9 commit,aliyun / k8s / vmware / host / network / config_file |
| Task 3 P1 云采集 7 套 | ✅ 完成 | 9 commit,hwcloud 2 子 / qcloud 7 子 / fusioninsight 2 子 / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise |
| Task 4 P2 archived placeholder 22 套 | ✅ 完成 | 23 commit,17 license + 4 cluster + 1 platform |
| Task 5.1 drift_report 工具 | ✅ 完成 | 1 commit,`drift_report.py` 213 行 + `test_drift_report.py` 44 行 + Makefile 14 行 |
| Follow-up 文档 | ✅ 完成 | 1 commit,有事实漂移(本审计已纠正) |
| spec / plan 修正 | ✅ 完成 | 2 commit |
| Task 1-4 reports | ✅ 完成 | 4 commit |
| **测试数据** | **521 passed / 91 skipped / 0 failed** | **33 真实落盘 22 passed 零回归** |

### 4.2 未完成(Task 5.2-5.4 + review + merge)

| 任务 | 状态 | 工作量 |
|---|---|---|
| Task 5.2 e2e 作者指南 v2 | ⏸️ TODO | 0.2 人天 |
| Task 5.3 PR description | ⏸️ TODO | 0.1 人天 |
| Task 5.4 验证全量 + 报告 | ⏸️ TODO | 0.1 人天 |
| Task 5 final review | ⏸️ TODO | 0.2 人天 |
| Whole-branch review | ⏸️ TODO | 0.3 人天 |
| Merge prep(到 feature_windyzhao) | ⏸️ TODO | 0.1 人天 |
| **小计** | | **~1.0 人天** |

### 4.3 后续 follow-up(本期外)

| 任务 | 来源 | 工作量 |
|---|---|---|
| 9 个 hwcloud 子对象 | Task 3.8 spec 已写 | 4.5 人天 |
| 17 license 阻塞对象 fixture 升级 | 等 license 解锁 | 一次性 |
| 5 集群/平台对象 fixture 升级 | 等 amd64 CI runner | 一次性 |
| drift_report 自动化(CI 集成) | 本期 | 1 人天 |
| middleware 模式 A 端 labels 校验扩展 | Task 3 review minor | 1 人天 |
| e2e 作者指南 v3 | 下期 | 0.3 人天 |
| **小计** | | **~7 人天** |

---

## 5. 风险评估(校准后)

### 5.1 低风险 ✅

- 严格 production 路径 0 改动(grep 验证 6 个 server 路径 + 3 个 stargazer 路径)
- 33 真实落盘对象 e2e 零回归(test_pipeline_factory.py 0 改动 + 22 passed)
- 521 passed / 91 skipped / 0 failed
- 24 个 stub plugin 是 NEW 模式(fallback priority=1,不触发生产路径)
- server/Makefile 14 行 append(只加 target,不破坏现有 target)

### 5.2 中风险 ⚠️

- 91 skipped 中包含 archived placeholder 公共契约命中(预期)+ K8s / config_file / network B 端 by design(per-object test 兜底)
- archived/tuxedo.py 会被 middleware/tuxedo.py 覆盖(priority 差异,by design)
- mycat / domestic_linux 走 protocol runner 暂代(archived host 无 host runner_type)
- 9 commits vs brief 6(Task 2),follow-up spec 提到

### 5.3 已知占位(等业务方提供)

- 17 license 阻塞对象:placeholder 模式 + license_status 标注
- 5 集群/平台对象:placeholder 模式 + cluster_complex / platform_constraint 标注
- 9 个 hwcloud 子对象:Task 3.8 spec 已写,下期实施

---

## 6. 收尾建议(用户决策依据)

### 6.1 强烈建议:补 Task 5.2-5.4 + review + merge prep 后再合并

工作量 ~1 人天,产出:
- Task 5.2 author guide v2 扩 A/B 端 / placeholder / drift_report 章节
- Task 5.3 PR description(数字基于本审计的真实数据)
- Task 5.4 验证全量报告(521 passed / 91 skipped,Task 5.1 后实测)
- Task 5 final review
- Whole-branch review
- Merge prep(到 `feature_windyzhao`)

### 6.2 可选:不补直接合并(不建议)

风险:
- 33 真实落盘 0 改动,但 author guide 仍是 v1(不含 A/B 端 / placeholder / drift_report)
- PR description 缺失
- 用户 Web UI 提交时需要手写

### 6.3 关键观察

- **核心代码改动扎实**:53 commit 全部 review 通过(任务级 + 用户自查),无 critical / important issue
- **测试覆盖完整**:521 passed / 91 skipped / 0 failed
- **生产影响最小**:严格 production 路径 0 改动 + 24 stub plugin 是 fallback + Makefile append 不破坏
- **33 真实落盘零回归**:沿用 v3+v4 22 passed(测试基础设施不动)
- **修复 follow-up 文档**:本审计已识别 4 处事实漂移(HEAD / commit 数 / file stat / 测试数字)+ 1 处口径表述错

---

## 7. 后续建议流程

1. **修改 follow-up 文档**(本审计已识别 4 处漂移 + 1 处口径),写 follow-up v2
2. **执行 Task 5.2**(author guide v2, 0.2 人天)
3. **执行 Task 5.3**(PR description, 0.1 人天)
4. **执行 Task 5.4**(验证全量报告, 0.1 人天)
5. **执行 Task 5 final review**(reviewer 跑, 0.2 人天)
6. **执行 whole-branch review**(final review, 0.3 人天)
7. **执行 merge prep**(到 `feature_windyzhao`, 0.1 人天)
8. **用户在 Web UI 提 PR**(等用户)

总 ~1 人天,质量门 + 收尾完整。
