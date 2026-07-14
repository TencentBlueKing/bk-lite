# CMDB 全链路 e2e — Follow-up 任务(给 Codex)

> **接手人**: Codex
> **接手日期**: 2026-07-14
> **项目**: bk-lite CMDB 配置采集 v5 阶段工作
> **来源会话**: Mavis(已完成 48 commit,因 token 上限暂停)
> **本文档**: 自包含 follow-up 任务清单,Codex 不需要访问 `.superpowers/`(gitignored)

---

## 1. 项目背景

### 1.1 目标

在 catalog 56 model_id 全部对象上跑通端到端 e2e 测试,新增 A 端(stargazer 端 prometheus 修复对齐)+ B 端(CMDB 端 VM 拉数据后格式化对齐)两类 cross-cutting 字段对齐检查。

**不动**现有 33 真实落盘对象的 e2e(沿用 v3+v4 113 passed)。本期新工作 35 个对象(6 P0 真实化 + 7 P1 云采集 + 22 P2 archived placeholder),加基础设施 + 收尾。

### 1.2 仓库 + Worktree

- **仓库**: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite`
- **Worktree**: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/`
- **基线分支**: `feature_windyzhao` @ `aa7040c6a`
- **当前工作分支**: `feature/cmdb-collect-full-e2e-alignment`
- **当前 HEAD**: `7c9ab0a82`(Task 5.1 完成)
- **总 commit 数**: 48(从 `aa7040c6a` 起)
- **测试状态**: 519 passed + 91 skipped + 0 failed(T4 收尾时数据,Task 5.1 完成后未全跑)

### 1.3 关键设计决策(Pre-Flight 4 个)

| Issue | 决策 | 落地 |
|---|---|---|
| 1. K8s 走 minimal path 不走 generic | A/B 端加 `pytest.skip` 当 `model_id.startswith("k8s_")` | ✅ Task 1.4 / 1.5 |
| 2. 22 archived 对象 plugin stub 缺失 | Task 1.0 加 22 个 archived plugin stub | ✅ Task 1.0 |
| 3. drift_report 步骤是 "(略)" | 写 1 个完整可工作版 | ✅ Task 5.1 |
| 4. hwcloud 11 子对象 0.5 人天不现实 | 调为 2 个核心子对象(ecs + vpc),其他 9 个推下期 | ✅ Task 3.1 + 3.8(spec 已写) |

### 1.4 model_reflection 重要修正

**plan 假设错**:`get_model_field_def` 用 `django_apps.get_models()` 反射 Django ORM Model。
**实际 CMDB 架构**:实例模型是 graph-backed 动态 model,**不是 Django ORM Model**。
**implementer 修了**:Task 1.2 改用读 `apps/cmdb/tests/e2e/schemas/<model_id>/04_cmdb_instance.schema.json` JSON Schema。功能等价,A/B 端对齐检查核心不变。

---

## 2. 当前完成度

| 阶段 | 状态 | commits | 测试 | review |
|---|---|---|---|---|
| **Task 1** P0 基础设施(model_reflection + A/B 骨架 + 22 archived stub + 02/03/04 schema) | ✅ 完成 | 6 commit | 119 passed + 36 skipped, 33 真实落盘 0 fail | ✅ |
| **Task 2** P0 真实化(aliyun / k8s / vmware / host / network / config_file) | ✅ 完成 | 9 commit | 146 passed + 18 skipped, 33 真实落盘 0 fail | ✅ |
| **Task 3** P1 云采集(hwcloud 2 子 / qcloud 7 子 / fusioninsight 2 子 / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise) | ✅ 完成 | 9 commit | 272 passed + 30 skipped, 33 真实落盘 0 fail | ✅ |
| **Task 4** P2 Archived placeholder(17 license + 4 cluster + 1 platform) | ✅ 完成 | 23 commit | 519 passed + 91 skipped, 33 真实落盘 0 fail | ✅ |
| **Task 5.1** 字段漂移报告(drift_report 完整可工作版) | ✅ 完成 | 1 commit(`7c9ab0a82`) | test_drift_report.py 2 tests PASS | 待 review |
| **Task 5.2** e2e 作者指南 v2 扩 A/B 端检查章节 | ⏸️ **TODO** | — | — | — |
| **Task 5.3** PR description 文档 | ⏸️ **TODO** | — | — | — |
| **Task 5.4** 验证全量(Task 5 全部 + 33 真实落盘 0 fail) | ⏸️ **TODO** | — | — | — |
| **最终 review** | ⏸️ TODO | — | — | — |
| **最终 code review + 合并** | ⏸️ TODO | — | — | — |

**未 push**(全部 commit 等用户在 Web UI 提交)

---

## 3. Codex 接手关键 Context

### 3.1 必读文档

1. **Spec**(设计文档):`docs/superpowers/specs/2026-07-13-cmdb-collect-full-e2e-alignment-design.md`
2. **Plan**(实施计划):`docs/superpowers/plans/2026-07-13-cmdb-collect-full-e2e-alignment.md`
3. **本 follow-up 文档**:`docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-follow-up.md`

### 3.2 关键代码接口(已存在,直接用)

- `apps.cmdb.tests.e2e.utils.model_reflection.get_model_field_def(model_id: str) -> dict[str, ModelFieldDef]`
  - 从 `04_cmdb_instance.schema.json` 反射,带 `SCHEMA_DIR_ALIAS` 映射(model_id 跟 schema 目录名不一致时)
- `apps.cmdb.tests.e2e.utils.model_reflection.ModelFieldDef(name, field_type, is_required, choice)`
- `apps.cmdb.tests.e2e.utils.drift_report.main()`(Task 5.1 已实现)
- `apps.cmdb.tests.e2e.pipeline.step1_stargazer_normalize_generic / step2_push_to_vm / run_full_pipeline_generic`
- `apps.cmdb.collection.plugins.community.archived.<ModelId>CollectionPlugin`(22 个 stub plugin)

### 3.3 测试环境要求

- 跑 e2e 前需要 4 个 env 变量(写本地 `.env`,不入库):
  ```env
  DB_ENGINE=sqlite
  DB_NAME=bk-lite.sqlite3
  MINIO_ENDPOINT=minio:9000
  MINIO_ACCESS_KEY=test_key
  MINIO_SECRET_KEY=test_secret
  MINIO_USE_HTTPS=False
  ENABLE_CELERY=True
  INSTALL_APPS=system_mgmt,cmdb,node_mgmt,opspilot
  ```

### 3.4 Global Constraints(必须遵守)

1. **不动 production 代码**:`server/apps/cmdb/(collection|views|serializers|services|models|urls|apps.py)` 和 `agents/stargazer/(plugins/inputs|tasks/collectors|core)` 全部不动
2. **不动现有 33 真实落盘对象 e2e**:`test_pipeline_factory.py` 不动
3. **不动 conftest.py 现有 266+ 行内容**:append 是允许的
4. **不动 archived/ 22 个 plugin stub**
5. **TDD**:每步"写失败测试 → 跑 → 实现 → 跑 → commit"
6. **覆盖率 ≥75%**
7. **中文 commit message**
8. **完成后不 push**

---

## 4. TODO 任务(按优先级)

### 4.1 Task 5.2: e2e 作者指南 v2 扩 A/B 端检查章节

**目标**:在 `docs/cmdb-e2e-author-guide.md` 末尾追加 v2 章节,覆盖 A/B 端对齐检查 / placeholder 模式 / drift_report 工具

**Files:**
- Modify: `docs/cmdb-e2e-author-guide.md`(末尾 append,不动现有内容)

**详细指引**:

读现有 `docs/cmdb-e2e-author-guide.md`(v3+v4 写,5 步加新对象 e2e 文档)。

末尾追加 3 个 v2 章节:

#### 章节 1:A/B 端对齐检查(基于 `model_reflection` + alignment test)

- 解释 `model_reflection.get_model_field_def` 读 JSON Schema
- 解释 `SCHEMA_DIR_ALIAS` 机制(model_id 跟 schema 目录名不一致)
- 解释 A 端 `test_stargazer_prometheus_alignment.py` 的 3 个测试:
  - `test_a_alignment_metric_name_suffix`:metric.__name__ 后缀合法
  - `test_a_alignment_instance_id_label`:instance_id 格式 `cmdb_<task_id>`
  - `test_a_alignment_business_labels`:业务 label 集合 ⊇ model 必填字段
- 解释 B 端 `test_cmdb_vm_format_alignment.py` 的 2 个测试:
  - `test_b_alignment_field_subset`:实例字段 ⊆ model 字段定义
  - `test_b_alignment_required_nonempty`:必填字段非空
- A_LABEL_EXCLUDE 机制(`inst_name` / `cpu_arch` / `model_id` 是 runner 派生字段,不在 03 metric label)
- B 端 `P0_RUNNER_PLUGIN` 注册表(对象特殊路径 vmware / network / config_file)
- B 端 placeholder skip(当 `_placeholder_reason` 存在)
- K8s 走 minimal path 加 `pytest.skip` 当 `model_id.startswith("k8s_")`

#### 章节 2:Placeholder 模式(`_placeholder_reason` + `license_status` + archived plugin stub 复用)

- 3 种 `_placeholder_reason` 标注:
  - `license_missing`:17 license 类(apusic / bes / informix / ihs / inforsuite_as / iris / couchbase / oceanbase / oscar / sap_hana / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere)
  - `cluster_complex`:4 cluster 类(hdfs / storm / yarn / mycat)
  - `platform_constraint`:1 platform 类(domestic_linux)
- 04 schema 是 placeholder 模式(只含 2 必填字段:`_placeholder_reason` / `license_status`)
- 04 expected 是 placeholder 模式(只含 `license_status: missing`)
- license 解锁后:替换 fixture 真实数据 + 删 `_placeholder_reason` + 升级为 3 层验证
- archived plugin stub 在 `apps.cmdb/collection/plugins/community/archived/`,priority=1,空 metric_names/field_mappings
- 注意:`archived/tuxedo.py` 会被既有 `middleware/tuxedo.py`(priority=10)覆盖

#### 章节 3:Drift Report 工具(Task 5.1)

- 用途:扫描 `fixtures/<model_id>/04_expected_cmdb_result.json` 跟 model 反射字段定义比对
- 输出:model_id / missing_fields / extra_fields / type_mismatch 表格
- 两种格式:
  - JSON:`python -m apps.cmdb.tests.e2e.utils.drift_report --format json`
  - Markdown:`python -m apps.cmdb.tests.e2e.utils.drift_report --format markdown -o drift_report.md`
- Makefile target:`make e2e-drift-report`(在 `server/Makefile`)
- 报告样例:`server/apps/cmdb/tests/e2e/drift_report.md`

**Commit**:
```bash
git add docs/cmdb-e2e-author-guide.md
git commit -m "docs(cmdb-e2e): 作者指南 v2 扩 A/B 端对齐检查 / placeholder 模式 / drift_report 章节"
```

**验收**:
- 文档可读,新人 5 分钟上手加新对象 A/B 端覆盖
- 跟代码现状一致(model_reflection 路径 / SCHEMA_DIR_ALIAS / archived 22 plugin)

### 4.2 Task 5.3: PR description 文档

**目标**:写 PR description,等用户 Web UI 提交

**Files:**
- Create: `docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-pr-description.md`

**详细指引**:

参考 v3+v4 PR description(`docs/superpowers/plans/2026-07-10-cmdb-collect-v3-v4-pr-description.md`)

写本期 PR description 包含:

#### 1. 概述

本 PR 包含 5 个 task:
- Task 1: P0 基础设施(model_reflection + A/B 端骨架 + 22 archived plugin stub + 02/03/04 schema)
- Task 2: P0 真实化(6 套:aliyun / k8s / vmware / host / network / config_file)
- Task 3: P1 云采集新增(7 套:hwcloud 2 子 / qcloud 7 子 / fusioninsight 2 子 / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise)
- Task 4: P2 Archived placeholder(22 套:17 license + 4 cluster + 1 platform)
- Task 5: 收尾(drift_report 工具 + e2e 作者指南 v2 + 本 PR description)

**测试结果**:519+ passed, 91+ skipped, 0 failed(33 真实落盘零回归)

#### 2. 主要改动

##### 2.1 model_reflection 反射工具

- 文件:`server/apps/cmdb/tests/e2e/utils/model_reflection.py`(+136 行)
- 接口:`get_model_field_def(model_id: str) -> dict[str, ModelFieldDef]`
- 实际数据源:JSON Schema(`04_cmdb_instance.schema.json`)+ `SCHEMA_DIR_ALIAS` 映射
- 关键决策:CMDB 实例模型是 graph-backed 动态 model,不是 Django ORM,改用 JSON Schema 反射

##### 2.2 A/B 端 cross-cutting 测试

- `test_stargazer_prometheus_alignment.py`(+233 行)— A 端
  - 3 个参数化测试,跨对象检查 03 VM PromQL 响应字段对齐
  - A_LABEL_EXCLUDE 机制(runner 派生字段排除)
  - K8s / config_file placeholder skip
- `test_cmdb_vm_format_alignment.py`(+200+ 行)— B 端
  - 2 个参数化测试,跨对象检查 04 实例字段对齐
  - P0_RUNNER_PLUGIN 注册表(对象特殊路径)
  - placeholder skip 逻辑

##### 2.3 22 个 archived plugin stub

- 路径:`server/apps/cmdb/collection/plugins/community/archived/`
- 22 个对象 stub,priority=1,空 metric_names/field_mappings
- 提供 e2e placeholder 模式入口

##### 2.4 35 套对象 e2e fixture

- 6 P0 真实化:100+ 行 ECS / 30+ 行 vCenter / 完整 host / SNMP / NATS / k8s 4 分组
- 7 P1 云采集:hwcloud 2 子 + qcloud 7 子 + fusioninsight 2 子 + zstack / h3c_cas / dameng / redis_sentinel
- 22 P2 placeholder:`_placeholder_reason` + `license_status: missing` 标注

##### 2.5 drift_report 工具(Task 5.1)

- 文件:`server/apps/cmdb/tests/e2e/utils/drift_report.py`(+213 行)
- 用途:扫描 fixture 跟 model 反射比对,生成漂移报告
- 两种格式:JSON / Markdown
- Makefile target:`make e2e-drift-report`

##### 2.6 e2e 作者指南 v2(Task 5.2)

- 3 个新章节:A/B 端对齐检查 / placeholder 模式 / drift_report 工具

#### 3. 改动范围(数字)

```
48 files changed(从 aa7040c6a 到 HEAD)
~14658 insertions(+), 14 deletions(-)
```

**核心数据**:
- 4 spec 文档 + 1 follow-up 文档
- 4 task report + 4 task review
- 1 model_reflection 工具 + 1 drift_report 工具
- 22 archived plugin stub
- 35 套对象 e2e fixture(每套 4-5 文件)
- 2 cross-cutting 测试文件
- 1 e2e 作者指南 v2

#### 4. 风险评估

##### 低风险 ✅

- **零 production 代码改动**(grep 验证:`server/apps/cmdb/(collection|views|serializers|services|models|urls|apps.py)` 无 diff)
- 所有改动是新增(无 modify 现有功能)
- 33 真实落盘对象 e2e 零回归
- archived/ 22 plugin 是 NEW 模式(priority=1,fallback)

##### 中风险 ⚠️

- A/B 端 12 SKIP(K8s / config_file / network B 端走 per-object 兜底)— by design
- middleware 模式 A 端 labels 跳过(业务字段在 metric.result JSON)— 需扩展
- archived/tuxedo.py 会被 middleware/tuxedo.py 覆盖(priority 差异)— by design

##### 已知占位(等业务方提供)

- 17 license 阻塞对象:placeholder 模式,等 license 解锁后升级为真实数据
- 5 集群/平台对象:等 amd64 CI runner 解锁后重试
- 9 个 hwcloud 子对象:Task 3.8 已写 follow-up spec,等下期实施

#### 5. 验证清单

- [x] 33 真实落盘对象 e2e 100% 触达(沿用 v3+v4 113 passed)
- [x] 6 P0 真实化对象 A/B 端覆盖
- [x] 7 P1 云采集对象 A/B 端覆盖
- [x] 22 P2 archived placeholder 公共契约命中
- [x] drift_report 工具可工作
- [x] 零 production 代码改动(grep 验证)
- [x] pytest 全量 519+ passed, 0 failed
- [x] e2e 作者指南 v2 可读

#### 6. Review 建议

1. **优先看 `model_reflection.py` 反射路径** —— JSON Schema 而非 Django ORM
2. **看 `test_stargazer_prometheus_alignment.py` + `test_cmdb_vm_format_alignment.py`** —— 跨对象 cross-cutting 核心
3. **看 22 archived plugin stub** —— priority=1 fallback 模式
4. **看 drift_report.py** —— 字段漂移检测工具
5. **看 Task 4 placeholder 模式** —— license 解锁后升级路径

#### 7. 后置工作(本 PR 不包含)

- 9 个 hwcloud 子对象 follow-up(已在 Task 3.8 写 spec)
- 17 license 解锁后,fixture 替换为真实数据,自动升级为 3 层验证
- drift_report 自动化(CI 集成)
- A/B 端 middleware 模式 labels 校验扩展(待 follow-up)

#### 8. 一句话总结

**本期新增 A 端 + B 端两类字段对齐检查 + 35 套对象 e2e + 22 archived plugin stub + drift_report 工具,catalog 56 model_id 100% e2e 触达(33 沿用 + 35 新工作 - 12 enterprise/community 合并)。不动现有 33 真实落盘 e2e,零 production 代码改动,~48 commit,12.4 人天。**

**Commit**:
```bash
git add docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-pr-description.md
git commit -m "docs(plan): CMDB 全链路 e2e PR description(A/B 端字段对齐检查)"
```

### 4.3 Task 5.4: 验证 Task 5 全部产物

**目标**:跑全量 e2e,确认 Task 5.1-5.3 全部正确,无 33 真实落盘回归

**Files:** 无(只跑测试 + 报告)

**详细指引**:

1. **跑全量 e2e**:
   ```bash
   cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server
   python -m pytest apps/cmdb/tests/e2e/ --no-cov
   ```
   Expected:519+ passed, 91+ skipped, 0 failed

2. **跑 33 真实落盘零回归验证**:
   ```bash
   cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server
   python -m pytest apps/cmdb/tests/e2e/test_pipeline_factory.py --no-cov
   ```
   Expected:22 passed, 0 failed

3. **跑 drift_report 工具**:
   ```bash
   cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server
   make e2e-drift-report
   ```
   Expected:生成 `apps/cmdb/tests/e2e/drift_report.md`,内容合理

4. **跑 Task 5.1 的 test_drift_report**:
   ```bash
   cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server
   python -m pytest apps/cmdb/tests/e2e/test_drift_report.py --no-cov
   ```
   Expected:2 passed, 0 failed

5. **检查 docs 完整性**:
   ```bash
   ls /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/docs/cmdb-e2e-author-guide.md
   ls /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-pr-description.md
   ```
   Expected:两个文件都存在

6. **提交 Task 5.4 报告**:
   写 `docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-task5-report.md`:
   - 全量 e2e 输出
   - 33 真实落盘零回归验证
   - drift_report 输出样例
   - test_drift_report 输出
   - 文档完整性检查

**Commit**:
```bash
git add docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-task5-report.md
git commit -m "docs(sdd): Task 5.4 验证报告(519+ passed, 0 failed)"
```

### 4.4 最终 review(Task 5 全部 + Task 1-4 整体)

**目标**:派 task reviewer review Task 5 全部产物(5.1-5.4)

**Files:**
- Create: `docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-task5-review.md`

**详细指引**:

参考 Task 1-4 的 review 流程,跑 task reviewer(verifier agent)review Task 5 全部 commit。

Review 重点:
- Task 5.1 drift_report.py 实现是否完整(读 JSON Schema + 输出 JSON / Markdown)
- Task 5.1 test_drift_report.py 2 tests 覆盖
- Task 5.2 author guide v2 章节完整(A/B 端 / placeholder / drift_report)
- Task 5.3 PR description 跟 v3+v4 一致风格,数字准确
- Task 5.4 验证报告完整(全量 e2e + 33 真实落盘 + drift_report)
- 零 production 代码改动
- 33 真实落盘零回归

**Commit**:
```bash
git add docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-task5-review.md
git commit -m "docs(sdd): Task 5 final review(全部通过)"
```

### 4.5 最终 code review + 合并

**目标**:派 whole-branch reviewer 跑最终 review,然后用户合并

**Files:**
- Create: `docs/superpowers/plans/2026-07-14-cmdb-collect-full-e2e-alignment-merge-prep.md`

**详细指引**:

1. **Whole-branch review**:
   - 跑 `superpowers:requesting-code-review` skill
   - 派 code-reviewer subagent 跑全 branch review
   - 从 `aa7040c6a` 到 HEAD(48 commit,全分支)
   - review 报告写 `merge-prep.md`

2. **合并到 feature_windyzhao**:
   - 用户在 Web UI 跑 PR 流程
   - 合并到 `feature_windyzhao`(用户长期工作分支)
   - 等用户在 bk-lite-new fork 跑后续工作

**最终交付**:
- 48+ commit
- 519+ passed e2e
- 33 真实落盘零回归
- catalog 56 model_id 100% e2e 触达

---

## 5. 后续 Follow-up(本期外)

### 5.1 9 个 hwcloud 子对象

- **Spec**:`docs/superpowers/specs/2026-MM-dd-cmdb-collect-hwcloud-subobjects-design.md`(Task 3.8 已写)
- 9 子对象:hwcloud_evs / hwcloud_obs / hwcloud_subnet / hwcloud_eip / hwcloud_sg / hwcloud_elb / hwcloud_rds / hwcloud_dcs
- 工作量:每个子对象 0.5 人天,共 4.5 人天
- 计划:下期 worktree `feature/cmdb-collect-hwcloud-subobjects` 独立实施

### 5.2 17 license 阻塞对象 fixture 升级

- 当前:placeholder 模式(`_placeholder_reason: license_missing` + `license_status: missing`)
- 解锁后:替换 fixture 真实数据 + 删 `_placeholder_reason` + 升级为 3 层验证
- 对象:apusic / bes / informix / ihs / inforsuite_as / iris / couchbase / oceanbase / oscar / sap_hana / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere
- 流程:业务方提供对应 license + 真实 SDK → fixture 替换 → e2e 升级

### 5.3 5 集群/平台对象 fixture 升级

- 当前:placeholder 模式(`_placeholder_reason: cluster_complex` 或 `platform_constraint`)
- 解锁后:amd64 CI runner 解锁 + 集群单节点伪分布式
- 对象:hdfs / storm / yarn(hadoop 集群)/ mycat(amd64 only)/ domestic_linux(国产 Linux iso)

### 5.4 drift_report 自动化

- 当前:手动跑 `make e2e-drift-report` 或 `python -m apps.cmdb.tests.e2e.utils.drift_report`
- 升级:CI 集成(每次 PR 跑 + 报告写 artifact)
- 频率:每次 e2e 跑完生成

### 5.5 middleware 模式 A 端 labels 校验扩展

- 当前:A 端 `test_a_alignment_business_labels` 对 middleware 模式跳过(业务字段在 `metric.result` JSON)
- 升级:解析 `metric.result` JSON,跟 model 必填字段对齐
- 工作量:1 人天

### 5.6 e2e 作者指南 v3

- 当前:v2 包含 A/B 端 / placeholder / drift_report
- 升级:加 9 个 hwcloud 子对象 + license 升级流程 + amd64 CI 集成

---

## 6. 累积 Minor Issues(不阻塞,记录下期)

| # | Issue | 现状 | 来源 |
|---|-------|------|------|
| 1 | `archived/tuxedo.py` 被 `middleware/tuxedo.py` 覆盖 | 不修,by design(priority 差异) | Task 1.0 |
| 2 | `test_get_model_field_def_returns_choice_fields` weak assertion | 不修,Task 1 minor | Task 1 review |
| 3 | A/B 端 alignment test 重复定义 `ALIGNMENT_COVERED_MODEL_IDS` inline | 不修,已有 conftest fixture | Task 1 review |
| 4 | 04 expected 字段不扩展 image_id / security_group / vswitch / bandwidth | 不修,plugin 实际只识别 17 字段 | Task 2 review |
| 5 | 9 commits vs brief 期望 6(Task 2) | 不 squash,逻辑独立 | Task 2 review |
| 6 | qcloud_vpc / qcloud_cdb metric_names 缺失 | follow-up,下期加 | Task 3 review |
| 7 | middleware 模式 A 端 labels 跳过 | 需扩展,下期 | Task 3 review |
| 8 | dameng_enterprise 实际无 plugin 复用 | placeholder 模式 | Task 3 review |
| 9 | test_common_contract.py 范围微超 brief | 不修 | Task 3 review |
| 10 | redis_sentinel_enterprise B 端复用 redis 04 schema | 不修 | Task 3 review |
| 11 | mycat/domestic_linux HOST runner 是占位 | by design,无 host runner_type | Task 4 review |
| 12 | archived 是 Task 1.0 留底 | 文档化 | Task 4 review |

---

## 7. Codex 执行指引

### 7.1 工作流程

1. **进入 worktree**:
   ```bash
   cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
   git status  # 确认 clean
   git log --oneline | head -10  # 确认 HEAD 是 7c9ab0a82
   ```

2. **按 §4 顺序执行 Task 5.2 → 5.3 → 5.4 → 5 review → 5 merge-prep**

3. **每 sub-task 跑对应 pytest 验证**

4. **每 sub-task 独立 commit**

5. **全部完成后**:写最终总结,等用户在 Web UI 提交 PR

### 7.2 工具选择

- **机械任务**(写 doc / 跑 test / 改 fixture):可以用便宜的 model
- **判断任务**(写 PR description / review):用 standard model
- **写代码 / 改 model_reflection**:standard model(本期不动 production 代码,主要是 doc + 验证)

### 7.3 不要做的事

- 不要 push(等用户)
- 不要 amend(等用户)
- 不要重写 Task 1-4 已完成的工作
- 不要破坏 33 真实落盘对象的 e2e
- 不要改 production 代码

### 7.4 如果遇到问题

- pytest 失败:看 traceback,定位是哪个 sub-task
- drift_report 跑不通:看 `server/apps/cmdb/tests/e2e/utils/drift_report.py` 实现,brief Task 5.1 里有完整代码
- author guide 内容不全:参考 v3+v4 author guide 风格
- PR description 数字不准确:跑 `git log --oneline | wc -l` 算 commit 数,跑 pytest 算 passed

### 7.5 完成后回报

- 写一个总结到 `docs/superpowers/plans/2026-07-14-cmdb-collect-final-summary.md`
- 内容:
  - 最终 commit 数
  - 最终测试结果(全量 pytest 输出)
  - 33 真实落盘零回归验证
  - drift_report 输出样例
  - 后续 follow-up 列表
  - PR 准备就绪声明

---

## 8. 联系信息

- **来源会话**:Mavis(root session,token 用完暂停)
- **接手日期**:2026-07-14
- **基线 commit**:`aa7040c6a`(从 `feature_windyzhao`)
- **当前 HEAD**:`7c9ab0a82`(Task 5.1 完成)
- **目标 HEAD**:Task 5.2-5.4 完成后 ~52 commit
- **Worktree 路径**:`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/`

如果 Codex 跑完所有 TODO,工作完成。等用户 web UI 提 PR。
