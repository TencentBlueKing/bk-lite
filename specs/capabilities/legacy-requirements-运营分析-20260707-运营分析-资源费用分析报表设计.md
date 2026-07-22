# 云资源成本运营分析报表 — 设计规格

> Migrated from `spec/requirements/运营分析/20260707.运营分析-资源费用分析报表设计.md` as legacy capability evidence.

> 状态: 已通过 brainstorming 流程与用户确认,等待最终评审
> 日期: 2026-07-06
> 适用模块: `bk-lite/server/apps/cmdb/` + `bk-lite/server/apps/operation_analysis/`
> 前端: `bk-lite/web/src/app/ops-analysis/`

## 1. 背景与目标

### 1.1 背景

bk-lite 已具备完整的「CMDB 自定义上报」能力(企业版,代码位于 `server/apps/cmdb/enterprise/` 与 `server/apps/cmdb/custom_reporting/`)。运维侧有两个 cmdb 模型:

- `cloud_resource`:云资源主体实例,字段含 `instance_id / instance_name / instance_type / department / user / daily_unit_price / region / status` 等。`department` 为**手工录入的扁平字符串字段**,无上下级层级。
- `cloud_bill`:云资源账单实例,字段含 `bill_id / bill_date / daily_cost / cost_type / currency`,通过关系字段 `resource_inst` 关联到 `cloud_resource.inst_id`。**每一条记录 = 一个云资源某一天的费用**。

数据录入与上报流程由用户与 ITSM 平台手工完成,本设计不涉及采集、上报、关系维护。

### 1.2 目标

在 `operation_analysis` 模块下,基于「Report 画布」提供**云资源成本分析报表**,支持:

1. 按用户、部门、时间范围筛选
2. 在筛选条件下聚合展示总费用、实例数、日均费用、同环比
3. 按资源类型 / 部门 / 用户维度展示费用分布
4. 展示每个云资源实例在时间范围内的总费用明细(支持分页排序)

### 1.3 范围

**In Scope**:
- 3 个 scene_widget 后端接口(汇总、分布、明细)
- 共享筛选条件序列化器与 ORM 服务层
- 一个预置的 Report 画布模板(可在画布中调整)
- 多租户隔离、性能降级、错误处理、测试

**Out of Scope**:
- cmdb 模型本身的设计与录入
- 数据的采集、上报、关系维护
- 多币种实时汇率换算
- 预算 / 告警 / 预测

## 2. 架构概览

```
┌────────────────────────────────────────────────────────────────────┐
│ Frontend (Web)                                                      │
│   Report 画布(canvas)                                                │
│   ├── KPI 卡  widget(type=cost_summary)                            │
│   ├── 分布图  widget(type=cost_distribution)                        │
│   └── 明细表  widget(type=cost_instance_list)                       │
└────────────────────┬───────────────────────────────────────────────┘
                     │  POST /api/operation_analysis/scene_widget/<name>
                     ▼
┌────────────────────────────────────────────────────────────────────┐
│ Backend                                                              │
│   apps.operation_analysis.views.scene_widget_view                   │
│     ├── cloud_resource_cost_summary                                 │
│     ├── cloud_resource_cost_distribution                            │
│     └── cloud_resource_cost_instance_list                           │
│                          │                                          │
│                          ▼                                          │
│   apps.operation_analysis.services.cloud_cost.service               │
│     - 共用 filter 序列化 + ORM 拼装                                  │
│     - 复用 cmdb 实例服务层(读 cloud_resource / cloud_bill)           │
│                          │                                          │
│                          ▼                                          │
│   cmdb 自定义上报 + (可选) cost_daily_rollup 预聚合表                │
└────────────────────────────────────────────────────────────────────┘
```

**关键决策**:
- 数据全部走 cmdb 模型实例表(`cloud_resource`、`cloud_bill`),由 cmdb 自定义上报治理。
- 报表 widget 通过 cmdb 实例服务层读取,**不在 cmdb 之外维护业务表**。
- 若 cmdb 实例表的 JSON 字段无原生索引导致查询过慢,引入一张**预聚合 rollup 表**作为降级路径。

## 3. 组件设计

### 3.1 共享筛选契约(Filter)

三个 widget 接受同一组筛选参数,保证画布切换筛选条件时三个 widget 同步刷新。

```python
# apps/operation_analysis/serializers/cloud_cost_serializers.py
from rest_framework import serializers

class CloudResourceCostFilterSerializer(serializers.Serializer):
    user = serializers.CharField(required=False, allow_blank=True, help_text="主责任人(精确匹配)")
    department = serializers.CharField(required=False, allow_blank=True, help_text="部门(扁平精确匹配,无递归)")
    bill_date_range = serializers.ListField(
        child=serializers.DateField(),
        min_length=2,
        max_length=2,
        help_text="[start_date, end_date],闭区间,bill_date 在此范围内",
    )
    group_by = serializers.ChoiceField(
        choices=["instance_type", "department", "user"],
        required=False,
        help_text="仅 cost_distribution 使用",
    )
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    sort_by = serializers.ChoiceField(
        choices=["instance_name", "total_cost", "department", "user"],
        required=False,
        default="total_cost",
    )
    order = serializers.ChoiceField(choices=["asc", "desc"], required=False, default="desc")
```

### 3.2 Widget 1: KPI 汇总卡

**端点**:`POST /api/operation_analysis/scene_widget/cloud_resource_cost_summary`

**入参**:
```json
{
  "user": "alice",
  "department": "ops",
  "bill_date_range": ["2026-06-01", "2026-06-30"]
}
```

**返回**:
```json
{
  "total_cost": "12345.67",
  "instance_count": 142,
  "avg_daily_cost": "411.52",
  "mom_change_pct": "+12.5",
  "currency": "CNY"
}
```

**计算逻辑**:
- `total_cost = SUM(cloud_bill.daily_cost)` WHERE `bill_date ∈ range` AND 通过 `resource_inst` 关联的 `cloud_resource` 满足 `user=? AND department=?`
- `instance_count = COUNT(DISTINCT cloud_resource.inst_id)` WHERE 在该筛选下至少存在一条 cloud_bill
- `avg_daily_cost = total_cost / days_in_range`(days_in_range 含起止)
- `mom_change_pct`:把 `[start, end]` 向前平移 `(end - start + 1)` 天得到 `[prev_start, prev_end]`,计算 `prev_total`,返回 `((total - prev_total) / prev_total * 100)` 保留 1 位小数 + 符号

**Service 签名**:
```python
class CloudCostService:
    def summary(self, *, group_id: int, user: str | None, department: str | None,
                date_range: tuple[date, date]) -> dict: ...
```

### 3.3 Widget 2: 分布图

**端点**:`POST /api/operation_analysis/scene_widget/cloud_resource_cost_distribution`

**入参**:
```json
{
  "department": "ops",
  "bill_date_range": ["2026-06-01", "2026-06-30"],
  "group_by": "instance_type"
}
```

**返回**:
```json
{
  "group_by": "instance_type",
  "groups": [
    {"key": "compute", "total_cost": "8000.00", "instance_count": 80, "pct": "64.81"},
    {"key": "storage", "total_cost": "4345.67", "instance_count": 62, "pct": "35.19"}
  ]
}
```

**计算逻辑**:
- 在 summary 的筛选基础上,按 `group_by` 字段(`cloud_resource.instance_type | department | user`)GROUP BY
- 每个分组:`total_cost = SUM(daily_cost)`、`instance_count = COUNT(DISTINCT cloud_resource.inst_id)`
- `pct = total_cost / 总 total_cost × 100`,保留 2 位小数
- 返回按 `total_cost DESC` 排序

### 3.4 Widget 3: 实例明细表

**端点**:`POST /api/operation_analysis/scene_widget/cloud_resource_cost_instance_list`

**入参**:
```json
{
  "department": "ops",
  "bill_date_range": ["2026-06-01", "2026-06-30"],
  "page": 1,
  "page_size": 20,
  "sort_by": "total_cost",
  "order": "desc"
}
```

**返回**:
```json
{
  "total": 142,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "inst_id": "i-abc123",
      "instance_name": "web-prod-01",
      "instance_type": "compute",
      "department": "ops",
      "user": "alice",
      "region": "cn-north-1",
      "total_cost": "1234.56",
      "cost_pct": "10.00"
    }
  ]
}
```

**计算逻辑**:
- 按 `cloud_resource.inst_id` GROUP BY,聚合 `SUM(daily_cost)` 作为 `total_cost`
- `cost_pct` = 该实例 total_cost / 整体 total_cost × 100(整体 total_cost 复用 summary 的结果,或此处再算一次保证自洽)
- 排序字段映射: `total_cost` → `SUM(daily_cost)`, `instance_name` → `cloud_resource.instance_name`, `department` → `cloud_resource.department`
- 分页:`OFFSET = (page - 1) * page_size`,`LIMIT = page_size`

### 3.5 Report 画布预置模板

```python
# apps/operation_analysis/management/commands/seed_cloud_cost_report.py
REPORT_TEMPLATE = {
    "name": "云资源成本分析",
    "build_in_key": "cloud_resource_cost_overview",
    "directory": None,  # 预置报表挂在根目录,用户可自行拖到子目录;避免首次安装目录缺失
    "view_sets": [
        {
            "id": "w_summary",
            "type": "cost_summary",
            "title": "总览",
            "endpoint": "cloud_resource_cost_summary",
            "position": {"x": 0, "y": 0, "w": 12, "h": 2},
        },
        {
            "id": "w_distribution",
            "type": "cost_distribution",
            "title": "费用分布",
            "endpoint": "cloud_resource_cost_distribution",
            "default_group_by": "instance_type",
            "position": {"x": 0, "y": 2, "w": 6, "h": 4},
        },
        {
            "id": "w_instance_list",
            "type": "cost_instance_list",
            "title": "实例明细",
            "endpoint": "cloud_resource_cost_instance_list",
            "page_size": 20,
            "position": {"x": 6, "y": 2, "w": 6, "h": 4},
        },
    ],
    "filters": [
        {"key": "department", "label": "部门", "type": "select", "source": "from-cloud-resource"},
        {"key": "user", "label": "主责任人", "type": "select", "source": "from-cloud-resource"},
        {"key": "bill_date_range", "label": "账单日期范围", "type": "daterange", "default": "last_30_days"},
    ],
}
```

- `is_build_in=True` + `build_in_key` 唯一约束,避免重复种子
- 用户可以在画布里增删 widget / 调整布局 / 改默认筛选,无需后端改动
- 前端需要支持 widget 类型 `cost_summary / cost_distribution / cost_instance_list` 的渲染组件

## 4. 多租户与权限

- **多租户隔离**:所有 ORM 查询强制带 `group_id=request.user.group_id`,沿用 cmdb 实例服务层的隔离策略
- **权限点**:
  - cmdb 实例查看权限(`view-View` 或对应实例权限)
  - operation_analysis 的 `directory.report` 权限(查看 Report 画布)
- **不做**字段级权限(部门/用户筛选对所有能进报表的人开放)

## 5. 性能与索引

### 5.1 索引需求

| 索引 | 用途 | 备注 |
|------|------|------|
| `(group_id, model_id, inst_id)` 唯一 | cmdb 实例表基础查询 | cmdb 已有 |
| `(model_id, bill_date)` | 账单按时间过滤 | 需 cmdb 自定义上报支持字段索引 |
| `(model_id, resource_inst)` | 账单按资源 join | 同上 |

### 5.2 降级方案:预聚合 rollup 表

**触发条件**:任一 widget 查询耗时 > 3s 或日账单行数 > 阈值(暂定 500 万)。

**Rollup 表 schema**:
```python
class CloudResourceCostDailyRollup(models.Model):
    rollup_date = models.DateField()
    inst_id = models.CharField(max_length=128)
    instance_name = models.CharField(max_length=256)
    instance_type = models.CharField(max_length=64)
    department = models.CharField(max_length=128)
    user = models.CharField(max_length=128)
    region = models.CharField(max_length=64)
    daily_cost = models.DecimalField(max_digits=18, decimal_places=4)
    cost_type = models.CharField(max_length=64)
    group_id = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cloud_resource_cost_daily_rollup"
        unique_together = [("rollup_date", "inst_id", "cost_type", "group_id")]
        indexes = [
            models.Index(fields=["group_id", "rollup_date"]),
            models.Index(fields=["group_id", "department", "rollup_date"]),
            models.Index(fields=["group_id", "user", "rollup_date"]),
            models.Index(fields=["group_id", "instance_type", "rollup_date"]),
        ]
```

**刷新策略**:
- Celery beat 任务,每日凌晨 02:00 跑一次增量刷新(刷新 `rollup_date >= yesterday`)
- 失败重试 3 次,失败告警到运维
- 全量重建命令可选触发(运维介入)

**Service 层路由**:
```python
def get_query_source():
    if CloudBill.objects.filter(...).count() > ROLLUP_TRIGGER_THRESHOLD:
        return CloudResourceCostDailyRollup.objects
    return CloudBill.objects  # 走 cmdb 实例服务
```

### 5.3 数据延迟

- 报表数据**允许最终一致**(T+1)
- rollup 表每日凌晨刷新,白天写入的账单在次日才出现在报表里(在 UI 上需要标注数据更新时间)

## 6. 错误处理

| 场景 | 行为 |
|------|------|
| 账单无对应云资源(关联丢失) | 报表中**排除**该账单,日志 WARN,`instance_count` 不计入 |
| 时间范围为空 / 非法(start > end) | 400,前端禁用查询按钮 |
| 同一 inst_id + bill_date 重复账单 | 由 cmdb identity (`bill_id = {inst_id}-{bill_date}`) 去重,主键冲突直接 upsert |
| 大数据量查询超时(> 10s) | 切到预聚合 rollup 表;若 rollup 表**当日尚未生成**(凌晨任务失败或首次启动),返回 503 + 提示「数据准备中,请稍后再试」 |
| 货币不一致 | 汇总卡的 `currency` 字段 = 筛选范围内账单中**出现频次最高**的币种(平票取字母序最小);明细表按原币种分组,**不做实时汇率换算**(MVP) |
| group_id 缺失 / 无权限 | 401 / 403,前端跳转登录或无权限页 |
| 内部异常 | 500 + 统一错误体,日志 ERROR 含 `request_id`,前端展示「系统繁忙」 |

## 7. 测试策略

对齐仓库红线 `server/docs/testing-guide.md` 与 `docs/governance/quality.md`:TDD 红-绿-重构,覆盖率 ≥ 75%。

### 7.1 单元测试

每个 widget 一个测试文件,覆盖:

**`test_cloud_cost_summary.py`**:
- 空数据(无账单 / 筛选无匹配)→ total_cost=0, instance_count=0, mom_change_pct=null
- 单条账单 → 数值正确
- 多条账单跨月 → SUM 正确,边界日期包含
- 同环比:本月 vs 上月 → 百分比正确,符号正确
- 上月无数据 → mom_change_pct=null,不抛 ZeroDivision
- 关联丢失账单 → 不计入

**`test_cloud_cost_distribution.py`**:
- group_by 三种字段各一个 case
- 空分组 → groups=[]
- 占比总和 = 100%
- 单实例多账单 → instance_count 仍 = 1(DISTINCT)
- 排序 DESC 正确

**`test_cloud_cost_instance_list.py`**:
- 默认排序 total_cost DESC
- 按 instance_name / department 排序
- 分页(page=2, page_size=10) → OFFSET 正确
- page_size > 100 → 400
- cost_pct 与 summary 的 total_cost 自洽

### 7.2 集成测试

- **三 widget 一致性**:同一组筛选条件,`summary.total_cost` = `distribution.groups[].total_cost` 之和 = `instance_list.items[].total_cost` 之和(允许 ±0.01 浮点误差)
- **多租户隔离**:租户 A 的用户在 widget 里看不到租户 B 的实例与账单
- **关联丢失**:删除一个 cloud_resource 后,其 cloud_bill 不出现在任何 widget
- **rollup 路由切换**:模拟账单量 > 阈值,验证 service 切到 rollup 查询路径
- **画布预置模板**:`seed_cloud_cost_report` 幂等可重跑,`build_in_key` 唯一约束生效

### 7.3 测试夹具

- `tests/factories/cloud_resource.py` / `cloud_bill.py`:基于 `factory_boy` 或手写工厂,每个 case 自包含
- 不依赖真实数据,数据库用 SQLite 内存模式
- cmdb 自定义上报用 community fallback model(已在测试环境跑通)

### 7.4 门禁

- `cd server && make test`(项目规定)
- 新增覆盖率报告;低于 75% 不允许合并

## 8. 文件落点

| 角色 | 路径 |
|------|------|
| Widget 后端视图 | `server/apps/operation_analysis/views/cloud_cost_view.py` |
| Widget 序列化 | `server/apps/operation_analysis/serializers/cloud_cost_serializers.py` |
| Widget 服务 | `server/apps/operation_analysis/services/cloud_cost/service.py` |
| ORM 查询封装 | `server/apps/operation_analysis/services/cloud_cost/orm.py` |
| Rollup 模型(降级) | `server/apps/operation_analysis/models/cloud_cost_rollup.py` |
| Rollup 刷新任务 | `server/apps/operation_analysis/tasks/cloud_cost_rollup.py` |
| 预置 Report 模板 | `server/apps/operation_analysis/management/commands/seed_cloud_cost_report.py` |
| 单元 / 集成测试 | `server/apps/operation_analysis/tests/cloud_cost/` |
| 前端 widget 组件 | `web/src/app/ops-analysis/components/cloud-cost/`(`SummaryCards.tsx` / `DistributionChart.tsx` / `InstanceTable.tsx` / `FilterBar.tsx`) |
| 前端 API 客户端 | `web/src/app/ops-analysis/api/cloud-cost.ts` |
| 前端 Report 画布注册 | `web/src/app/ops-analysis/constants/widget-types.ts` 追加 `cost_summary` / `cost_distribution` / `cost_instance_list` 三个类型定义 + 渲染器映射 |
| URL 注册 | `server/apps/operation_analysis/urls.py`(追加三个端点) |

## 9. 风险与未来工作

| 风险 | 缓解 |
|------|------|
| cmdb 自定义上报不支持字段级索引 | 首期上线后观察查询耗时;超阈值即启用 rollup 降级 |
| 多币种不做汇率换算,汇总数字与实际有偏差 | UI 上明示币种,文档说明;后续可加汇率源 |
| 报表数据 T+1 延迟不符合部分用户预期 | UI 标注「数据更新至 YYYY-MM-DD」,提供「刷新」按钮手动触发(走增量同步) |
| Report 画布预置模板被用户改坏 | 模板通过 `build_in_key` 锁定,误删后可重新 seed |

**未来扩展**:
- 趋势折线(按天聚合)
- 预算 / 阈值告警
- 多币种汇率换算
- 按资源标签(tags)分组
- 与告警模块联动(费用异常告警)

## 10. 评审记录

- 2026-07-06 brainstorming 阶段,用户确认以下决策:
  - 报表形态:Report 画布 + 三个 widget(KPI 汇总 / 分布 / 明细)
  - 账单语义:账单记录直接存当日金额(`bill.daily_cost`),主模型 `daily_unit_price` 为参考价,不参与聚合
  - 组织层级:无,主模型只有部门(扁平手工录入字段)
  - 时间筛选:bill_date 范围,中等规模(10万~几百万行),1-3 秒响应可接受
  - 数据架构:方案 A 全 cmdb 模式(主模型 + 账单子模型都走 cmdb 自定义上报)
  - 预聚合 rollup 表作为降级方案接受
  - 测试策略 TDD + 75% 覆盖率 + 三 widget 一致性测试接受

## 11. 下一步

- 用户评审本文档 → 通过后调用 `superpowers:writing-plans` 拆分实施计划 → 进入实现阶段。
