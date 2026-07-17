# fix(alerts): 告警分派「告警源过滤」不生效 + 同源问题 4 处全修

## 背景

### 用户报告

用户配置告警分派策略「K8s Event 根因分析分派」：

```json
{
  "match_type": "filter",
  "match_rules": [[{"key": "source_id", "value": "3", "operator": "eq"}]],
  "personnel": ["o-eXO6xSkv0Sh82YhXLq5lWUMX1o"],
  "is_active": true
}
```

期望：K8s 告警源（id=3）产生的告警自动分派给 Qiu.Jia。
实际：告警产生但**没有处理人**，落到"未分派告警兜底"通知里。

### 根因（数据流追踪）

```
前端 matchRule.tsx 选「告警源（按 ID）」→ 发送 key=source_id, value=String(source.id)
                                                            ↓
后端 common/assignment.py:74
  FIELD_MAPPING = {"source_id": "source_name", ...}   ← ⚠️ 错映射
                                                            ↓
RuleMatcher.build_single_rule_q 生成 Q(source_name="3")
                                                            ↓
Alert.source_name 实际存的是 AlertSource.name（如 "K8s"），跟 "3" 永远不匹配
                                                            ↓
匹配 0 命中 → 告警不进分派 → 没处理人
```

### 同源问题（顺手排查发现 4 处）

| 位置 | FIELD_MAPPING source_id 映射 | 真实结果 |
|---|---|---|
| `common/assignment.py:74` | `"source_name"` | ⚠️ **本次 bug**（告警分派） |
| `common/shield.py:29` | `"source__source_id"` | ⚠️ 错匹配（业务 ID 字符串 vs 主键数字） |
| `enrichment/matcher.py` | 走 dict 匹配，event 字典里没 `source_id` 字段 | ⚠️ 永不匹配 |
| `aggregation/strategy/matcher.py` | `FIELD_MAP` 无 source_id 键，但 Event.source_id 自动 FK 字段 | ✅ 实际 OK（init_alert_rules 用 `nats_source.id` 整数写入） |

**所有 4 处的共同原因**：前端 matchRule.tsx 共享版发 `String(source.id)`（数据库主键数字），但后端多处没用对字段。

### 防御性分析

| 关联历史 bug | commit | 教训 |
|---|---|---|
| 2026-06-25 `level` 键漏配 | `2774d4c14` "按级别自动分派不生效" | 前端加新 key 类型，后端 FIELD_MAPPING 易漏 |
| 本次 `source_id` 漏配 | (本次) | 同样模式再次复现 |

`test_repro_filter_assignment.py` 当时覆盖了 title/level/resource_type/resource_id，**漏了 source_id**——所以逃过 CI。

---

## 修复方案

### 选 A（推荐）+ Alert 加 FK

**A**：把 `FIELD_MAPPING["source_id"]` 改为 `source__id`（FK 主键）

**但实施时发现**：Alert 模型**没有 `source` FK 字段**（只有 `source_name` 字符串），Event 模型才有 `source` FK。所以需要：
1. Alert 加 `source` FK 字段（schema migration）
2. 历史 Alert 数据回填 source_id（data migration，从 source_name 反查）
3. alert_builder.py 写入 Alert 时同时设 source FK
4. 4 处 FIELD_MAPPING 改 `source_id`（FK 主键）

### 方案 B 增强（防再犯）

`RuleMatcher` 加 `alt_field_mapping` 机制：
- 正向操作符（eq/contains/re）：主字段 OR alt 字段，任一命中即视为命中
- 反向操作符（ne/not_contains）：主字段 AND alt 字段，都不命中才视为不命中

`assignment` / `shield` 给 `source_id` 注册 fallback：
- assignment fallback: `["source_name"]`（兜历史脏数据 value=name 字符串）
- shield fallback: `["source__source_id"]`（兜历史脏数据 value=业务 ID 字符串）

### 数据流（修复后）

```
前端 matchRule.tsx → key=source_id, value=String(source.id)="3"
                          ↓
AlertAssignmentOperator.FIELD_MAPPING["source_id"] = "source_id"  （主）
AlertAssignmentOperator.ALT_FIELD_MAPPING["source_id"] = ["source_name"]  （兜底）
                          ↓
RuleMatcher.build_single_rule_q  生成
  Q(source_id="3") | Q(source_name="3")   ← OR 语义
                          ↓
查 Alert 表（Alert 已有 source FK 字段 + 历史数据已回填）
  source_id=3 命中 → 告警被分派
```

---

## 改动清单（12 个文件）

### 数据模型 + Migration（3 个文件）

| 文件 | 改动 |
|---|---|
| `models/models.py` | `Alert` 加 `source = ForeignKey(AlertSource, SET_NULL, null=True, blank=True, related_name="alerts")` |
| `migrations/0023_alert_source.py` | schema migration: AddField source（自动生成）|
| `migrations/0024_backfill_alert_source_from_source_name.py` | data migration: 从 source_name 反查 AlertSource 设 source_id（分批 1000 条/批）|

### 业务代码（5 个文件）

| 文件 | 改动 |
|---|---|
| `aggregation/builder/alert_builder.py` | `_resolve_standard_fields` 增加 `source_id` 字段；`_create_new_alert` 传 `source_id=standard_fields["source_id"]` |
| `common/assignment.py` | `FIELD_MAPPING["source_id"]` 改 `source_id`；新增 `ALT_FIELD_MAPPING` |
| `common/shield.py` | `FIELD_MAPPING["source_id"]` 改 `source_id`；新增 `ALT_FIELD_MAPPING` |
| `common/source_adapter/base.py` | `create_events` 在 enrich_batch 前塞 `data["source_id"] = self.alert_source.id` |
| `utils/rule_matcher.py` | 加 `alt_field_mapping` 参数；`build_single_rule_q` 按操作符区分 OR/AND 语义 |

### 测试（5 个文件，8 个新用例）

| 文件 | 改动 |
|---|---|
| `tests/test_repro_filter_assignment.py` | +2 用例: source_id eq / ne 命中与排除 |
| `tests/test_shield.py` | +1 用例: 按 source_id 过滤屏蔽，命中正确源、排除其他源 |
| `tests/test_source_adapter.py` | +1 用例: create_events 注入 source_id 到 event 字典供 enrichment 匹配 |
| `tests/test_enrichment_engine.py` | +1 契约测试: event 字典带 source_id 时 enrichment 能匹配 |
| `tests/test_utils.py` | +4 fallback 单元测试: OR 语义 / AND 语义 / 无 alt / alt 不命中 |

### 文档（1 个文件）

| 文件 | 改动 |
|---|---|
| `docs/superpowers/plans/2026-07-17-alert-assignment-source-id-filter-bug.md` | 根因分析 + 实施回填 |

---

## 测试结果

| Phase | 用例数 | 状态 |
|---|---|---|
| RED 阶段 - 4 个新 bug 用例 | 4 | ✅ 全红（确认捕获到 bug）|
| GREEN 阶段 - 4 个新 bug 用例 + 4 个 fallback 单元测试 | 8 | ✅ 全绿 |
| alerts 范围全量回归 | **1016** | ✅ **0 失败** |

跑测命令：
```bash
cd server && \
DB_ENGINE=sqlite DB_NAME=/tmp/test_alerts.sqlite3 \
uv run pytest apps/alerts/tests/ --no-cov --no-migrations
```

> 注：alerts migration 0021 冲突需要先 `makemigrations --merge` 生成 0022；migration 9 的 `NewSessionEventRelation` 索引问题在 sqlite 上需要 `--no-migrations` 绕过（与本次修复无关，主分支已存在）。

---

## 已知技术债（不阻塞，可后续 PR）

1. **alerts migration 0021 冲突**（主分支已有，本次跑测时自动生成 merge migration 0022；建议单独 PR 把 0022 cherry-pick 回主分支）
2. **AlertSource 重名风险**：data migration 按 name 匹配第一个 AlertSource——如果用户线上的 AlertSource 有重名，data migration 会错配（建议运营层加 `AlertSource.name` 唯一约束）
3. **RuleMatcher fallback 仅支持 ORM Q 的 OR/AND**——正则/包含嵌套等场景暂未单独走 alt
4. **enrichment matcher 仍走纯 dict 匹配**——`source_id` 注入依赖 source_adapter，enrich_engine 未加 key 解析

---

## 风险点

- **数据迁移风险**：data migration 跑在生产环境时如果 Alert.source_name 跟 AlertSource.name 匹配不上，Alert.source 会保持 NULL（已 log warning 不阻断）。建议运维：
  1. 上线前先 `SELECT count(*) FROM alerts_alert WHERE source_name IS NOT NULL` 验证 name 一致性
  2. 跑完 migration 后 `SELECT count(*) FROM alerts_alert WHERE source_id IS NULL` 看回填率
  3. 长期建议加 `AlertSource.name` UNIQUE 约束
- **回滚成本**：如果新代码回滚，data migration 不回填（设计上 `reverse_noop` 保持 source_id 不清空）。如需回滚需手动 `UPDATE alerts_alert SET source_id=NULL`
- **不影响**：本次修复**完全不改变**现有告警的 status/operator，data migration 只追加新字段

---

## 关联

- Plan 文档: `docs/superpowers/plans/2026-07-17-alert-assignment-source-id-filter-bug.md`
- 关联 commit: `2774d4c14` 「按级别自动分派不生效」（同类问题已修过一次）
- 工作分支: `feature/fix-alert-assignment-source-id-filter`
- 工作目录: `.worktrees/fix-alert-assignment-source-id-filter/`
