# 监控系统采集频率默认值统一为 60 秒 — 设计说明

## 背景

BK-Lite 监控子系统当前存在多处「采集频率默认值 = 10 秒」的硬编码：

- Django 模型 `MonitorInstance.interval` 字段 `default=10`
- K8s 部署的 Telegraf ConfigMap 中 `[agent] interval = "10s"`（Deployment 与 DaemonSet 各一处）

10 秒对采集端/后端压力大、噪声多；60 秒是平衡实时性和成本的合理默认。

## 已确认事实

1. `server/apps/monitor/models/monitor_object.py:55` 当前 `interval = models.IntegerField(default=10, verbose_name='监控实例采集间隔(s)')`。
2. `agents/webhookd/bk-lite-metric-collector.yaml:315`（telegraf-deployment ConfigMap）与 `:408`（telegraf-daemonset ConfigMap）均使用 `interval = "10s"`。
3. 同 yaml 中 cadvisor 的 `--housekeeping_interval=10s`（`:38`）属于 cadvisor 内部清理频率，**不是**数据采集频率；vmagent 的 `scrape_interval: 60s`（`:350`）已经是 60s，无需再动。
4. `server/apps/monitor/services/custom_snmp_plugin.py:187` 的 `"interval": 10` 仅用于 `_build_validation_context` 校验样本，运行时从 config 读取，不算采集频率默认值。
5. `server/scripts/run_monitor_manifest.sh:442` 的 `INSTALL_AGENT_POLL_INTERVAL_SECONDS="10"` 是安装任务轮询间隔，不是数据采集。
6. `agents/fusion-collector/.../sidecar.yml:5` 的 `update_interval: 10` 是 sidecar 拉配置间隔，不是数据采集。
7. `web/src/app/monitor/dashboards/shared/utils/constants.ts:14` 的 `DEFAULT_REFRESH_FREQUENCY_LIST` 是前端图表刷新选项，不是数据采集。

## 问题定义

监控系统内「采集频率 / 采集间隔」类默认值不统一，且明显偏激进（10s）。需要把这类默认值统一到 60s，避免新建实例/新部署默认跑出高频采集。

## 目标

1. 把已识别的 3 处「采集频率默认值 < 60s」全部改成 60s。
2. 不动已有数据（数据库里 `interval=10` 的老实例保持不变）。
3. 加一个轻量回归测试，锁定 `MonitorInstance.interval` 字段默认必须 = 60，防止后续误改回 10s。
4. 将“监控采集频率默认值统一为 60 秒”作为本设计和回归测试共同守护的规则。

## 非目标

1. 不迁移老数据（`interval < 60` 的已存在实例保留原值）。
2. 不改 cadvisor `--housekeeping_interval=10s`（属 cadvisor 内部清理，不在用户感知的「采集频率」范围）。
3. 不改 SNMP 插件校验样本里的 `"interval": 10`（非用户面对的默认值）。
4. 不改安装轮询 / 配置拉取 / 前端图表刷新等其它类型的「10」数字（语义不同）。
5. 不重写 telegraf 配置模板或提取常量（本次最小改动）。

## 方案选项

### 方案 A：只改 3 处硬编码默认值（最小改动）

只动 3 行硬编码：

- `models/monitor_object.py:55` `default=10` → `default=60`
- `bk-lite-metric-collector.yaml:315` `interval = "10s"` → `"60s"`
- `bk-lite-metric-collector.yaml:408` `interval = "10s"` → `"60s"`

Django 会要求生成一个 AlterField migration（仅记录 default 变化，不动老数据）。

**优点**：改动面最小，精确对应业务诉求。
**缺点**：没有回归保护，未来有可能被改回 10s。

### 方案 B：方案 A + 回归测试（推荐）

在方案 A 基础上，新增 `server/apps/monitor/tests/test_default_collection_interval.py`，断言 `MonitorInstance._meta.get_field("interval").default == 60`。

**优点**：

- 防止未来误改回 10s。
- 符合 `CLAUDE.md` 中「新功能/bugfix 必须先写测试」的 TDD 红线。
- 测试不依赖数据库，纯读模型元数据，跑得快。

**缺点**：多 ~10 行代码、1 个文件。

### 方案 C：方案 A + 提取常量

把 60 抽到 `server/apps/monitor/constants/...` 模块做 `DEFAULT_COLLECTION_INTERVAL_SECONDS = 60`，模型引用该常量。

**优点**：Python 侧单一真相源。

**缺点**：

- yaml 是配置文件无法 import Python 常量，意义有限。
- 改动面变大，超出「最小改动」意图。

## 推荐方案

采用方案 B。方案 A 在「最小改动」上更激进，但失去回归保护；方案 C 改动面过大。方案 B 在两者间取得平衡，且符合项目 TDD 红线。

## 设计细节

### 改动 1：Django 模型字段默认值

`server/apps/monitor/models/monitor_object.py:55`:

```python
interval = models.IntegerField(default=60, verbose_name='监控实例采集间隔(s)')
```

影响：

- 新建 `MonitorInstance` 时如果不传 `interval`，ORM 走 `default=60`，新实例采集间隔 60s。
- 老实例的 `interval=10` 完全不动（数据库值优先于模型 default）。

### 改动 2/3：K8s Telegraf `[agent] interval`

`agents/webhookd/bk-lite-metric-collector.yaml` 两次改动：

- `:315`（telegraf-deployment ConfigMap）`interval = "10s"` → `interval = "60s"`
- `:408`（telegraf-daemonset ConfigMap）`interval = "10s"` → `interval = "60s"`

影响：仅在 K8s 重新 apply 该 yaml 并重启 Telegraf Pod 时生效；正在运行的集群需要手动 apply 一次新 yaml。

### 改动 4：数据库迁移

`make makemigrations monitor` 自动产出形如 `0XXX_alter_monitorinstance_interval.py` 的 schema migration（AlterField），不改任何已有行。提交进 git，部署时 `make migrate` 自动应用。

### 改动 5：回归测试

新增 `server/apps/monitor/tests/test_default_collection_interval.py`：

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

### 错误边界

- Django migration 生成失败：保留 10s default 直到 migration 修复，但本地/测试环境默认会跑测试覆盖。
- Telegraf yaml apply 失败：监控采集继续以 10s 旧值运行，无数据丢失风险，仅是「采集频率未及时收敛到 60s」。

## 验收标准

1. `cd server && make makemigrations` 产出 1 个 AlterField migration 文件，diff 中 `default=10` → `default=60`。
2. `cd server && make test` 通过；其中新增的 `test_default_collection_interval.py::test_monitor_instance_default_interval_is_60_seconds` 通过。
3. `git grep -n 'default=10'` 在 `apps/monitor/models/` 下不再命中 `interval` 字段。
4. `git grep -n 'interval = "10s"'` 在 `agents/webhookd/bk-lite-metric-collector.yaml` 不再命中。
5. `agents/webhookd/bk-lite-metric-collector.yaml` 中 cadvisor `--housekeeping_interval=10s`、`vmagent scrape_interval: 60s` 等其它 10/60 数值保持不变（验证未误改）。
6. 现有测试 `test_monitor_object_service_extra.py::TestGenerateMonitorInstanceId::test_reuses_existing_and_updates_interval` 仍通过（fixture 显式 `interval=10` 不动，测试自身不依赖默认值）。

## 验证步骤

实施完成后：

1. `cd server && make makemigrations` —— 生成 migration
2. `cd server && make test` —— 跑回归测试 + 不破坏现有测试
3. `git status` —— 检查无意外文件改动
4. `git diff --stat` —— 检查改动只涉及 4 个文件:
   - `server/apps/monitor/models/monitor_object.py`(1 处 default 改值)
   - `agents/webhookd/bk-lite-metric-collector.yaml`(同文件 2 处 interval 改值)
   - 自动生成的 migration 文件(1 个新文件)
   - 新增的 `server/apps/monitor/tests/test_default_collection_interval.py`(1 个新文件)

本任务不涉及 web/ 改动，无需 `pnpm lint` / `pnpm type-check`。
