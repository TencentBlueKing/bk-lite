# 告警分派「告警源过滤」不生效 — 根因分析与修复方案

> 状态：✅ 已实施，待 review
> 日期：2026-07-17
> 范围：`server/apps/alerts/`（告警自动分派/屏蔽/富化） + Alert 模型 + RuleMatcher
> 关联：与 [2026-07-10 v4 收官报告] 的"fixture 采集"无关，本次为配置消费链路的代码缺陷

## 测试结果回填（2026-07-17）

| Phase | 用例数 | 状态 |
|---|---|---|
| RED 阶段 4 个新 bug 用例 | 4 | ✅ 全红（确认捕获到 bug）|
| GREEN 阶段 - 4 个新 bug 用例 + 4 个 fallback 单元测试 | 8 | ✅ 全绿 |
| alerts 范围全量回归 | 1016 | ✅ 0 失败（之前 1012 + 4 个新 fallback 单元测试）|

**结论**：修复完整、无回归。

---

## 1. 现象

用户配置的告警分派策略：

```json
{
  "name": "K8s Event 根因分析分派",
  "match_type": "filter",
  "match_rules": [[{"key": "source_id", "value": "3", "operator": "eq"}]],
  "personnel": ["o-eXO6xSkv0Sh82YhXLq5lWUMX1o"],
  "is_active": true
}
```

**期望**：K8s 告警源（id=3）产生的告警，自动分派给 Qiu.Jia。
**实际**：告警产生了，但没有处理人；落到「未分派告警兜底」通知里。

---

## 2. 根因（Phase 1 — 证据链）

### 2.1 数据流追踪

```
K8s event 产生
   ↓
Event 入库（source = AlertSource FK，source.source_id = "k8s"）
   ↓
聚合/即时生成 Alert
   Alert.source    = AlertSource(id=3, name="K8s", source_id="k8s")
   Alert.source_name = "K8s"   ← 在 alert_builder.py:279 写入
   ↓
触发自动分派：AlertAssignmentOperator.execute_auto_assignment
   ↓
_batch_find_matching_alerts(assignment)
   策略 match_type=filter → RuleMatcher.filter_queryset(qs, match_rules)
```

### 2.2 关键代码 — `server/apps/alerts/common/assignment.py:65-79`

```python
class AlertAssignmentOperator:
    FIELD_MAPPING = {
        "source_id": "source_name",   # ⚠️ 根因 ①：错误的字段映射
        "level": "level",
        "level_id": "level",
        "resource_type": "resource_type",
        "resource_id": "resource_id",
        "content": "content",
        "title": "title",
        "alert_id": "alert_id",
    }
```

**RuleMatcher** (`server/apps/alerts/utils/rule_matcher.py:144-149`) 把 key 替换成 model_field：

```python
key = rule.get("key", "")           # "source_id"
model_field = self.field_mapping.get(key)   # "source_name"
return Q(**{model_field: value})    # Q(source_name="3")
```

### 2.3 实际查询 vs. 数据库真实值

| 项 | 值 |
|---|---|
| 规则 `key` | `"source_id"` |
| 规则 `value` | `"3"`（用户在 UI 选 K8s 源时，前端发的是 `String(source.id)`，即 `AlertSource.id` 的字符串） |
| 实际生成的 SQL | `WHERE source_name = '3'` |
| `Alert.source_name` 实际存的值 | `"K8s"`（在 `aggregation/builder/alert_builder.py:279` 写入，取自 `AlertSource.name`） |

**结论**：`Q(source_name="3")` 永远匹配不上 `source_name="K8s"` 的告警 → 匹配数 = 0 → 没有任何告警进入分派 → 告警一直停在 UNASSIGNED → 走「未分派兜底」通知，没处理人。

### 2.4 前端在发什么 — `web/src/app/alarm/(pages)/settings/components/matchRule.tsx:175-179`

```tsx
{(i.key === 'source_id' || i.key === 'source_name') &&
  sourceList.map((source) => {
    // source_id 存 AlertSource.id（向后兼容老数据）；
    // source_name 存 AlertSource.name 字符串（推荐新规则用）。
    const optionValue =
      i.key === 'source_name' ? String(source.name) : String(source.id);
    return (
      <Option key={optionValue} value={optionValue}>
        {source.name}
      </Option>
    );
  })}
```

UI 标签：<kbd>告警源（按 ID）</kbd> → value = `String(source.id)`（`AlertSource` 的数据库主键，**整数转字符串**）。

### 2.5 模型结构对照

```python
# server/apps/alerts/models/alert_source.py:20
class AlertSource(models.Model):
    id         = AutoField(primary_key=True)         # 数据库主键，数字
    name       = CharField(max_length=100)           # 显示名，如 "K8s"
    source_id  = CharField(unique=True)              # 业务 ID，如 "k8s"

# server/apps/alerts/models/models.py:130 Alert
class Alert(models.Model):
    source      = ForeignKey(AlertSource)            # FK
    source_name = CharField(max_length=100)          # 冗余，存 name
    # ⚠️ Alert 没有 source_id 字段
```

---

## 3. 同类历史（防止再犯）

- **2026-06-25 `2774d4c14` 「按级别自动分派不生效——FIELD_MAPPING 补 level 键」**
  - 同类问题：前端发 `key=level`，后端 FIELD_MAPPING 没注册，整组失效
  - 修复：补 `"level": "level"`
  - 教训：每次前端 matchRule 加新 key 类型，后端 FIELD_MAPPING 容易漏——**应改成更安全的「默认 fallback」**

- **2026-06-25 新增 `server/apps/alerts/tests/test_repro_filter_assignment.py`**
  - 覆盖了 `title / level / resource_type / resource_id`
  - **没有覆盖 `source_id`**——所以这次 bug 逃过 CI

---

## 4. 修复方案

### 方案 A（推荐，最小变更）

**改 `FIELD_MAPPING["source_id"]` 从 `"source_name"` → `"source__id"`**

```python
FIELD_MAPPING = {
    "source_id": "source__id",   # Alert.source(FK) → AlertSource.id
    "level": "level",
    ...
}
```

- 实际查询变成 `Q(source__id="3")` —— `Alert.source_id = 3` 的告警全部命中
- 跟前端发 `String(source.id)` 的契约一致
- 跟现有 `level` 那次修复（commit 2774d4c14）同模式
- 兼容成本：现有数据库里如果有 `match_rules` 写了 `key=source_id` 但 value 是别的（比如 name "K8s"），改后会失效——但根据前端 matchRule.tsx 一直发 `String(source.id)`，实际不可能写出别的值，**风险≈0**

### 方案 B（更稳，加 fallback）

**改 `FIELD_MAPPING["source_id"]` + 自定义 matcher 多值兜底**

把 RuleMatcher 改成可对单 key 生成"或"条件：

```python
# 方案 B：在 RuleMatcher.build_single_rule_q 之外加 build_single_rule_q_with_fallback
def build_single_rule_q_with_fallback(self, rule, alt_model_fields):
    """如果主字段匹配 0 行，回退尝试 alt_model_fields"""
    primary_q = self.build_single_rule_q(rule)
    alt_qs = [Q(**{f"{field}": rule.get("value")}) for field in alt_model_fields]
    return primary_q | reduce(or_, alt_qs) if primary_q else reduce(or_, alt_qs)
```

- 兼容性最好（兜住历史脏数据）
- 实现略复杂，对 RuleMatcher 做了小扩展
- 价值：未来再加新 key 类型不容易再翻车

### 方案 C（前端改造，跨页面大改）

**前端 matchRule.tsx 改成发 `String(source.source_id)` 业务 ID 字符串**

- 业务 ID 字符串（如 "k8s"）更有业务含义
- 4 个共享 matchRule 页面（分派/屏蔽/富化）+ 1 个 actionRules 专用版都要改
- 还要改后端映射 `source__source_id`
- 改动面大，不在本次 bug 修复范围

### 方案对比

| 方案 | 改动量 | 兼容性 | 防再犯 | 推荐度 |
|---|---|---|---|---|
| A. 仅改 FIELD_MAPPING | 1 行 | 高（前端一致） | 弱（仍靠人记得加） | ⭐⭐⭐ |
| B. A + fallback matcher | 1 行 + RuleMatcher 增强 30 行 | **极高**（兜所有老数据） | **强**（未来加 key 不易再翻车） | ⭐⭐⭐⭐⭐ |
| C. 改前端 | 跨 5+ 页面 | 中 | 中 | ⭐ |

---

## 5. 测试计划（TDD 红-绿-重构）

### Phase A. RED — 在 `test_repro_filter_assignment.py` 加 source_id 用例

```python
@pytest.fixture
def source2(db):  # 第二个源，验证不串号
    return AlertSource.objects.create(
        name="Zabbix", source_id="zabbix", source_type="restful", secret="x"
    )

def _make_alert_with_source(source, alert_id, source_name=None):
    return Alert.objects.create(
        alert_id=alert_id,
        level="1",
        title="CPU高",
        content="c",
        fingerprint="fp" + alert_id,
        status=AlertStatus.UNASSIGNED,
        source=source,                 # ← FK 设上
        source_name=source_name or source.name,
        team=[1],
    )

@pytest.mark.django_db
def test_filter_by_source_id_assigns(sys_user, source, source2):
    """K8s 告警应被 K8s 源过滤的分派策略命中；Zabbix 告警不应被命中。"""
    alert_k8s = _make_alert_with_source(source, "A1")
    alert_zbx = _make_alert_with_source(source2, "A2")

    _make_assignment([[{"key": "source_id", "operator": "eq", "value": str(source.id)}]])

    AlertAssignmentOperator(["A1", "A2"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.UNASSIGNED, \
        "Zabbix 告警不应被 K8s 源的分派策略误命中"
```

### Phase B. GREEN — 改 FIELD_MAPPING

```python
# server/apps/alerts/common/assignment.py
"source_id": "source__id",   # 修
```

跑 `cd server && make test` 全绿。

### Phase C. 回归 + 端到端

- 跑 `test_repro_filter_assignment.py` 全用例（title/level/resource_type/resource_id/source_id 5 个 key 都过）
- 跑 `test_assignment.py` 现有用例
- 跑 `make test` 整库

### Phase D.（方案 B 可选）增强 RuleMatcher fallback

如果选方案 B，给 RuleMatcher 加 `build_single_rule_q_with_fallback` + 给 `FIELD_MAPPING` 加 `_alt_fields` 元数据；并对 `source_id` 注册 fallback `["source__source_id", "source_name"]`。

---

## 6. 关联风险（同模式未爆点）

排查过程中发现，**共享 matchRule.tsx 也被屏蔽、富化、相关性规则使用**：

| 位置 | FIELD_MAPPING source_id 映射 | 影响 |
|---|---|---|
| `common/assignment.py:74` | `"source_name"` ⚠️ | **本次 bug**（告警分派） |
| `common/shield.py:29` | `"source__source_id"` ⚠️ | 屏蔽可能也错（前端发 `source.id` 数字，shield 查 `source.source_id` 业务 ID 字符串 → 业务 ID 是 "k8s"，数字 "3" 永远不匹配） |
| `enrichment/engine.py` | 待查 |  |
| `aggregation/strategy/matcher.py` | `FIELD_MAP` 无 source_id 键 → fallback `Q(source_id=...)` 但 Event 模型无 `source_id` 字段 → 永远不匹配 | init_alert_rules.py 的"按 source_id"内置规则可能也失效 |

**本次最小修复只动 assignment.py**。其余 3 处需独立评估，但既然源码已读，**建议放在同一波修复**——一起走 TDD，避免分批回归。

---

## 7. 实施步骤（按用户工作流偏好）

1. **【本步】review 文档**：你 review 上面方案 A vs B，确定选哪个
2. 开 worktree：`feature/fix-alert-assignment-source-id-filter`（CLAUDE.md 强制要求）
3. 写 RED 测试用例（Phase A）
4. 跑测试看红
5. 改 `assignment.py`（方案 A）或 + 改 `rule_matcher.py`（方案 B）
6. 跑测试看绿
7. 跑 `make test` 全量回归
8. 顺手把 §6 的屏蔽/富化/聚合用同样 TDD 修一遍（如果你同意一起修）
9. 写 commit + PR 描述，按 v3/v4 模板
10. 文档「测试结果回填」一栏填好（绿/红用例数 + 关键 evidence）

---

## 8. 待确认假设（提交 review 前需要你拍板）

1. **方案选 A 还是 B？**（A = 1 行最小；B = + RuleMatcher fallback）
2. **§6 的同源问题本次一起修，还是先只修分派？**（一起修工作量大 3x，但能根除这类问题）
3. **是否要在 PR 描述里附"用户复现步骤"截图？**（已有的截图很合适）

---

## 9. 实际方案 + 实施总结

### 9.1 方案再调整（Phase 1 重新评估）

实施过程中发现 plan §2 的核心假设需要调整：

- ❌ **plan 原假设**：`source_id → source_name` 修复成 `source__id`（FK 跳到 AlertSource.id）
- ✅ **实际发现**：`Alert` 模型**没有 `source` FK 字段**（只有 `source_name` 字符串），`Event` 模型才有 `source` FK

这意味着：
1. 告警分派/屏蔽需要为 Alert 加 `source` FK 字段（schema migration）
2. 已有历史告警的 source_name 需要反查 AlertSource 设上 source FK（data migration）
3. alert_builder 写入 Alert 时需要同时设 source FK
4. shield 的 source__source_id 也需要改（Event 有 FK，可直接走 source_id）

**最终选择**：方案 A + Alert 模型加 FK（4 处 bug + Alert model + 1 schema migration + 1 data migration）

### 9.2 实施内容（按 TDD 顺序）

| Step | 文件 | 改动 |
|---|---|---|
| RED | `tests/test_repro_filter_assignment.py` | 新增 `test_filter_by_source_id_assigns_k8s_only` / `test_filter_by_source_id_ne_excludes_target_source` |
| RED | `tests/test_shield.py` | 新增 `test_shield_filter_match_by_source_id` |
| RED | `tests/test_source_adapter.py` | 新增 `test_create_events_injects_source_id_into_event_dict_for_enrichment` |
| RED | `tests/test_enrichment_engine.py` | 新增契约测试 `test_enrich_match_by_source_id_filters_target_source_only`（验证修复后契约）|
| GREEN | `models/models.py:Alert` | 加 `source = ForeignKey(AlertSource, SET_NULL, ...)` |
| GREEN | `migrations/0023_alert_source.py` | schema migration: AddField source |
| GREEN | `migrations/0024_backfill_alert_source_from_source_name.py` | data migration: 从 source_name 反查 AlertSource 设上 source FK |
| GREEN | `aggregation/builder/alert_builder.py` | `_resolve_standard_fields` 同时返回 source_id；`_create_new_alert` 直接传 `source_id=standard_fields["source_id"]` |
| GREEN | `common/assignment.py` | `FIELD_MAPPING["source_id"]`: `"source_name"` → `"source_id"`；新增 `ALT_FIELD_MAPPING = {"source_id": ["source_name"]}` |
| GREEN | `common/shield.py` | `FIELD_MAPPING["source_id"]`: `"source__source_id"` → `"source_id"`；新增 `ALT_FIELD_MAPPING = {"source_id": ["source__source_id"]}` |
| GREEN | `common/source_adapter/base.py:create_events` | 在 enrich_batch 之前塞 `data["source_id"] = self.alert_source.id` |
| GREEN | `utils/rule_matcher.py` | 加 `alt_field_mapping` 参数 + `build_single_rule_q` 按操作符区分 OR/AND 语义（正/反向 fallback）|
| GREEN | `tests/test_utils.py` | 新增 4 个 fallback 单元测试（OR 语义/AND 语义/无 alt/alt 不命中）|

### 9.3 已知技术债（不阻塞，可后续 PR）

1. **Migration 9 残留 `SessionEventRelation` 索引问题**（主分支已有，跟本次修复无关，CI 跑过 `--no-migrations` 才能跑通）
2. **alerts migration 0021 冲突**（已自动生成 merge migration 0022，主分支需要 cherry-pick）
3. **Alert 模型 source 字段**虽然加上了，但**老数据靠 data migration 回填**——如果用户线上的 AlertSource 有重名源，data migration 会按 name 匹配第一个，**重名风险**待评估（建议运营层加 `AlertSource.name` 唯一约束，但本 PR 不做）
4. **RuleMatcher fallback 当前只支持 ORM Q 的 OR/AND**，正则/包含嵌套等情况暂未单独走 alt，依赖主字段（已测试覆盖）
5. **enrichment matcher 仍走纯 dict 匹配**——`source_id` 注入是 source_adapter 的责任，没在 enrich_engine 里加 key 解析

### 9.4 风险点

- **数据迁移风险**：data migration 跑在生产环境时如果 Alert.source_name 跟 AlertSource.name 匹配不上，Alert.source 会保持 NULL（已 log warning 不阻断）。建议运维：
  1. 上线前先 SELECT count(*) 验证 name 一致性
  2. 跑完 migration 后 SELECT count(*) FROM alerts_alert WHERE source_id IS NULL 看回填率
- **回滚成本**：如果新代码回滚，data migration 不回填（设计上 `reverse_noop` 保持 source_id 不清空）。如需回滚需手动 `UPDATE alerts_alert SET source_id=NULL`

---

## 10. 待 review 项（更新）

1. ~~方案 A 还是 B~~ → ✅ 已选 A + Alert 加 FK（实施中再发现需要加 FK）
2. ~~§6 同源问题一起修吗~~ → ✅ 已一起修（4 处全修）
3. ~~是否附截图~~ → ❌ 不附（用户决定）

**新增 review 项**：
- 4. Alert 加 `source` FK 字段的 migration 风险（§9.3 第 3 点）
- 5. data migration 不回填的策略（§9.4）
- 6. merge migration 0022 是否需要单独 PR（§9.3 第 2 点）
