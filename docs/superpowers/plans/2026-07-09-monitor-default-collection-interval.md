# Monitor Default Collection Interval 60s Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把监控子系统里所有「采集频率默认值 < 60s」的硬编码统一改为 60s,并加一个回归测试防止回退。

**Architecture:**
- Django 模型 `MonitorInstance.interval` 字段 `default` 从 10 改为 60,自动生成 AlterField migration(不动老数据)
- K8s 部署的 Telegraf ConfigMap 中两处 `[agent] interval` 从 `"10s"` 改为 `"60s"`(deployment + daemonset 各一处)
- 新增回归测试断言 `MonitorInstance.interval` 字段默认 == 60
- 不在范围:cadvisor 内部清理、SNMP 校验样本、安装轮询、sidecar 配置拉取、前端图表刷新等"语义不同的 10"

**Tech Stack:** Python 3.12, Django 4.2, pytest(uv 管理),K8s YAML ConfigMap

## Global Constraints

来自 spec `docs/superpowers/specs/2026-07-09-monitor-default-collection-interval-design.md` 与仓库 `CLAUDE.md`:

- 中文优先(回答、注释、commit 全部中文)
- TDD 流程:测试先行,红-绿-重构;不写凑数测试
- 改动只触及 spec 列出的 4 个文件 + 1 个自动生成的 migration,其它文件不动
- 旧数据库数据不动(只改 default,不动老行)
- 验证命令:`cd server && make test` 必须通过
- 本任务不涉及 web/ 改动,无需 `pnpm lint` / `pnpm type-check`
- commit Co-Authored-By 末尾固定 `Claude <noreply@anthropic.com>`

---

### Task 1: 添加回归测试(红)

**Files:**
- Create: `server/apps/monitor/tests/test_default_collection_interval.py`

**Interfaces:**
- Consumes: `apps.monitor.models.MonitorInstance`
- Produces: 测试函数 `test_monitor_instance_default_interval_is_60_seconds`(当前必然失败)

**Context:** 当前 `MonitorInstance.interval` 字段 `default=10`,业务规则要求默认 = 60。先写一个断言 = 60 的测试,它在当前代码下必然失败(红),用于驱动后续 model 改动。

- [ ] **Step 1: 创建测试文件**

写入 `server/apps/monitor/tests/test_default_collection_interval.py`:

```python
"""监控实例采集间隔默认值锁定为 60s 的回归测试。

业务规则:任何「采集频率/采集间隔」类默认值,不足 60s 一律改为 60s。
该测试防止后续误改回 10s。
"""
from apps.monitor.models import MonitorInstance


def test_monitor_instance_default_interval_is_60_seconds():
    field = MonitorInstance._meta.get_field("interval")
    assert field.default == 60, (
        f"MonitorInstance.interval 默认值应为 60s,实际为 {field.default}"
    )
```

- [ ] **Step 2: 运行测试,确认失败(红)**

Run: `cd server && uv run pytest apps/monitor/tests/test_default_collection_interval.py -v`
Expected: `FAILED apps/monitor/tests/test_default_collection_interval.py::test_monitor_instance_default_interval_is_60_seconds - AssertionError: MonitorInstance.interval 默认值应为 60s,实际为 10`

- [ ] **Step 3: 提交测试(红状态)**

```bash
git add server/apps/monitor/tests/test_default_collection_interval.py
git commit -m "test(monitor): 添加采集间隔默认值回归测试(红)

为默认采集间隔 = 60s 业务规则添加锁定测试。当前应失败,
因为 MonitorInstance.interval 字段 default 仍为 10。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 改 Django 模型字段默认值 + 生成 migration(绿)

**Files:**
- Modify: `server/apps/monitor/models/monitor_object.py:55`
- Create: `server/apps/monitor/migrations/0009_alter_monitorinstance_interval.py`(自动生成,序号视实际而定)

**Interfaces:**
- Consumes: Task 1 的回归测试
- Produces: `MonitorInstance.interval.default == 60`、AlterField migration 同步

- [ ] **Step 1: 修改模型字段默认值**

编辑 `server/apps/monitor/models/monitor_object.py:55`,把:

```python
    interval = models.IntegerField(default=10, verbose_name='监控实例采集间隔(s)')
```

改为:

```python
    interval = models.IntegerField(default=60, verbose_name='监控实例采集间隔(s)')
```

- [ ] **Step 2: 生成 Django migration**

Run: `cd server && uv run python manage.py makemigrations`
Expected: 输出形如:
```
Migrations for 'monitor':
  apps/monitor/migrations/0009_alter_monitorinstance_interval.py
    - Alter field interval on monitorinstance
```

如果 Django 提示"No changes detected",停下来检查:可能 `models/monitor_object.py` 编辑未保存,或 default 仍为 10。

- [ ] **Step 3: 检查 migration 文件内容**

Run: `cat server/apps/monitor/migrations/0009_alter_monitorinstance_interval.py`
Expected: 文件中存在 `migrations.AlterField(model_name='monitorinstance', name='interval', field=models.IntegerField(default=60, verbose_name='监控实例采集间隔(s)'))`,且 **default 必须是 60**(不是 10)。

- [ ] **Step 4: 跑回归测试,确认通过(绿)**

Run: `cd server && uv run pytest apps/monitor/tests/test_default_collection_interval.py -v`
Expected: `1 passed in <X>s`

- [ ] **Step 5: 跑全量 server 测试,确认未破坏其它测试**

Run: `cd server && make test`
Expected: 全部通过。特别确认 `test_monitor_object_service_extra.py::TestGenerateMonitorInstanceId::test_reuses_existing_and_updates_interval` 仍通过(它的 fixture 显式 `interval=10` 不依赖默认值)。

如果有新失败:可能是 migration 序号与已有分支冲突,或测试 fixture 依赖旧 default。停下来排查,不要继续 Task 3。

- [ ] **Step 6: 提交 model + migration**

```bash
git add server/apps/monitor/models/monitor_object.py server/apps/monitor/migrations/0009_alter_monitorinstance_interval.py
git commit -m "fix(monitor): 监控实例采集间隔默认值 10s → 60s

业务规则:采集频率默认 = 60s,10s 太短对采集端/后端压力大、噪声多。
- models/monitor_object.py MonitorInstance.interval default=60
- 自动生成 AlterField migration(不动老数据)
- 配合 Task 1 的回归测试锁定

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 改 K8s Telegraf ConfigMap 采集间隔(配置改动,无单元测试)

**Files:**
- Modify: `agents/webhookd/bk-lite-metric-collector.yaml`(2 处行)

**Interfaces:**
- Consumes: 无
- Produces: telegraf-deployment ConfigMap 与 telegraf-daemonset ConfigMap 的 `[agent] interval = "60s"`

**Context:** 这两处是 K8s 部署里 Telegraf 的采集间隔,只在 apply 该 yaml 重启 Pod 后生效;无可执行单元测试,通过 `git diff` 验证唯一改动是这两行。

- [ ] **Step 1: 修改 telegraf-deployment ConfigMap**

编辑 `agents/webhookd/bk-lite-metric-collector.yaml:315`,把:

```yaml
    [agent]
      interval = "10s"
```

改为:

```yaml
    [agent]
      interval = "60s"
```

- [ ] **Step 2: 修改 telegraf-daemonset ConfigMap**

编辑 `agents/webhookd/bk-lite-metric-collector.yaml:408`,把:

```yaml
    [agent]
      interval = "10s"
```

改为:

```yaml
    [agent]
      interval = "60s"
```

- [ ] **Step 3: 验证只有这两行被改**

Run: `git diff agents/webhookd/bk-lite-metric-collector.yaml`
Expected: 仅有 2 处 `interval = "10s"` → `interval = "60s"` 的 diff。**不能**包含:
- cadvisor `--housekeeping_interval=10s`(行 38)
- vmagent `scrape_interval: 60s`(行 350)
- telegraf `flush_interval` 等其它间隔

如果有其它 diff,停下来检查,只保留 2 处 `[agent] interval` 的改动。

- [ ] **Step 4: 提交 yaml**

```bash
git add agents/webhookd/bk-lite-metric-collector.yaml
git commit -m "fix(collector): K8s Telegraf [agent] interval 10s → 60s

业务规则:采集频率默认 = 60s。本 yaml 内:
- telegraf-deployment ConfigMap [agent] interval 改 60s
- telegraf-daemonset ConfigMap [agent] interval 改 60s
cadvisor housekeeping_interval 与 vmagent scrape_interval 不在范围。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 最终验证

**Files:** 无

**Interfaces:**
- Consumes: Task 1/2/3 全部产出
- Produces: 干净 working tree,所有测试通过

- [ ] **Step 1: 跑全量 server 测试**

Run: `cd server && make test`
Expected: 全部通过,无新失败。

- [ ] **Step 2: 检查改动面与 spec 一致**

Run: `git status --short`
Expected: 无未提交改动(或仅有 `__pycache__` 等已忽略文件)。

Run: `git log --oneline -3`
Expected: 看到 3 个新 commit(Task 1/2/3),按顺序排列。

Run: `git diff --stat HEAD~3 HEAD`
Expected: 改动只涉及以下文件:
- `server/apps/monitor/models/monitor_object.py`(+1/-1)
- `server/apps/monitor/migrations/0009_alter_monitorinstance_interval.py`(新文件)
- `server/apps/monitor/tests/test_default_collection_interval.py`(新文件)
- `agents/webhookd/bk-lite-metric-collector.yaml`(+2/-2)

如果出现其它文件,在最终回复里说明并停下。

---

## 自审

### 1. Spec 覆盖

- spec §目标 1(改 3 处默认值)→ Task 2(1 处) + Task 3(2 处) ✓
- spec §目标 2(老数据不动)→ Task 2 Step 2-3 的 AlterField 不改数据,只改 default ✓
- spec §目标 3(回归测试)→ Task 1 ✓
- spec §目标 4(项目记忆已记录)→ 不需要任务,实施前已完成
- spec §验收标准 1-6 → 散落在 Task 2-4 的验证步骤里 ✓
- spec §非目标(4 条)→ Task 3 Step 3 的 diff 校验、Task 4 Step 2 的改动面校验 ✓

### 2. Placeholder 扫描

全文无 "TBD" / "TODO" / "implement later" / "fill in details" / "add appropriate error handling" / "类似 Task N"。每个代码步骤都含完整代码块,无 "Write tests for the above" 之类的空洞描述。

### 3. 类型/接口一致性

- Task 1 定义的测试函数名 `test_monitor_instance_default_interval_is_60_seconds` 在 Task 2 Step 4 的运行命令中一致引用 ✓
- Task 2 的 model 改动 `default=60` 与 Task 2 Step 3 的 migration 校验 `default=60` 一致 ✓
- Task 3 的两处 yaml 改动都使用相同的 `interval = "60s"` 字符串 ✓
- 没有任务引用任何未定义的方法/类/字段 ✓