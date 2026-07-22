# 移除所有者权限逻辑

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-12-remove-owner-logic/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## 背景

当前系统中，数据的可见性由两个条件决定：
1. 用户所在的组（team）
2. 用户是否为数据的创建者（created_by）

这导致一个问题：**创建者被移出组后，仍然能看到自己创建的数据**，脱离了平台的组权限体系。

## 目标

简化权限模型：**权限只看组，不看创建者**

```
之前: 能看到数据 = 在组内 ∪ 是创建者
之后: 能看到数据 = 在组内 (仅此一条)
```

## 范围

- **模块**: opspilot 下的 bot（智能体）、skill（技能）、knowledge_base（知识库）
- **影响**: 全局修改 `viewset_utils.py`，所有使用 AuthViewSet 的模块都会受影响

## 具体变更

### 后端

1. **移除创建者权限查询** - `server/apps/core/utils/viewset_utils.py`
   - 移除 `filter_by_group()` 中的 `creator_query = Q(created_by=request.user.username)`
   - 权限判断只基于 team 字段

2. **移除创建者特权** - `server/apps/opspilot/viewsets/bot_view.py`
   - 移除 L110 的 `if created_by != username: pop team` 逻辑
   - 有编辑权限就能修改 team 字段

3. **移除创建者特权** - `server/apps/opspilot/viewsets/llm_view.py`
   - 移除 L150 的 `if created_by != username: pop team` 逻辑
   - 有编辑权限就能修改 team 字段

### 前端

4. **移除所有者展示** - `web/src/app/opspilot/components/entity-card/index.tsx`
   - 移除 L203 的 `所有者: ${created_by}` 展示
   - 智能体和技能卡片都使用此组件

5. **移除所有者展示** - `web/src/app/opspilot/(pages)/knowledge/page.tsx`
   - 移除 L236 的 `所有者: ${card.created_by}` 展示

## 不变更

- 数据库 `created_by` 字段保留（用于审计）
- 创建时仍记录 `created_by`（只是不用于权限判断和展示）

## 验收标准

1. 用户 A 在组 X 创建数据 D
2. 将用户 A 移出组 X
3. 用户 A 无法再看到数据 D
4. 卡片上不再显示"所有者"信息

## Implementation Decisions

## 权限模型变更

```
┌─────────────────────────────────────────────────────────────────┐
│                    当前权限模型                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   filter_by_group():                                            │
│     creator_query = Q(created_by=user, domain=domain)           │
│     team_query = Q(team__contains=current_team)                 │
│     query = team_query | creator_query  ← 问题所在              │
│                                                                 │
│   结果: 用户能看到 (组内数据 ∪ 自己创建的数据)                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    目标权限模型                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   filter_by_group():                                            │
│     team_query = Q(team__contains=current_team)                 │
│     query = team_query  ← 只看组                                │
│                                                                 │
│   结果: 用户只能看到组内数据                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 代码变更设计

### 1. viewset_utils.py - filter_by_group()

**当前代码 (L146-164)**:
```python
if "created_by" in fields:
    creator_query = Q(created_by=request.user.username, domain=request.user.domain)
    if include_children:
        # ... 子组逻辑 ...
        query = team_query | creator_query
    else:
        query = Q(**{f"{org_field}__contains": current_team}) | creator_query
elif org_field in fields:
    query = Q(**{f"{org_field}__contains": current_team})
```

**目标代码**:
```python
if include_children:
    # ... 子组逻辑 ...
    query = team_query
else:
    query = Q(**{f"{org_field}__contains": current_team})
```

移除 `created_by` 分支，统一使用 team 查询。

### 2. bot_view.py - update()

**当前代码 (L110-111)**:
```python
if (not request.user.is_superuser) and (obj.created_by != request.user.username):
    data.pop("team", [])
```

**目标**: 删除这两行。有编辑权限即可修改 team。

### 3. llm_view.py - update()

**当前代码 (L150-151)**:
```python
if (not request.user.is_superuser) and (instance.created_by != request.user.username):
    params.pop("team", [])
```

**目标**: 删除这两行。有编辑权限即可修改 team。

### 4. entity-card/index.tsx

**当前代码 (L203)**:
```tsx
text={`${t('common.organization')}: ${...} | ${t('skill.form.owner')}: ${created_by}`}
```

**目标代码**:
```tsx
text={`${t('common.organization')}: ${...}`}
```

移除 `| 所有者: xxx` 部分。

### 5. knowledge/page.tsx

**当前代码 (L236)**:
```tsx
<span>{t('knowledge.form.owner')}: {card.created_by} ｜ {t('common.organization')}: {...}</span>
```

**目标代码**:
```tsx
<span>{t('common.organization')}: {...}</span>
```

移除 `所有者: xxx ｜` 部分。

## 影响分析

| 组件 | 影响 |
|------|------|
| Bot (智能体) | 权限查询、team 编辑、卡片展示 |
| LLMSkill (技能) | 权限查询、team 编辑、卡片展示 |
| KnowledgeBase (知识库) | 权限查询、卡片展示 |
| 其他 AuthViewSet 子类 | 权限查询（全局影响） |

## 风险

1. **全局影响**: `viewset_utils.py` 是通用基类，改动影响所有模块
2. **数据可见性变化**: 部分用户可能突然看不到自己创建但不在当前组的数据

## 测试要点

1. 创建者在组内 → 能看到数据 ✓
2. 创建者被移出组 → 看不到数据 ✓
3. 非创建者在组内 → 能看到数据 ✓
4. 非创建者有编辑权限 → 能修改 team ✓
5. 卡片不显示所有者 ✓

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-12
```

## Work Checklist

## 后端任务

- [x] **Task 1: 移除 viewset_utils.py 中的创建者权限查询**
  - 文件: `server/apps/core/utils/viewset_utils.py`
  - 位置: `filter_by_group()` 方法 (L146-164)
  - 操作: 移除 `creator_query` 和所有 `| creator_query` 的 OR 条件，保留纯 team 查询逻辑
  - 验证: `cd server && make test`

- [x] **Task 2: 移除 bot_view.py 中的创建者特权检查**
  - 文件: `server/apps/opspilot/viewsets/bot_view.py`
  - 位置: `update()` 方法 (L110-111)
  - 操作: 删除 `if (not request.user.is_superuser) and (obj.created_by != request.user.username): data.pop("team", [])`
  - 验证: `cd server && make test`

- [x] **Task 3: 移除 llm_view.py 中的创建者特权检查**
  - 文件: `server/apps/opspilot/viewsets/llm_view.py`
  - 位置: `update()` 方法 (L150-151)
  - 操作: 删除 `if (not request.user.is_superuser) and (instance.created_by != request.user.username): params.pop("team", [])`
  - 验证: `cd server && make test`

## 前端任务

- [x] **Task 4: 移除 entity-card 中的所有者展示**
  - 文件: `web/src/app/opspilot/components/entity-card/index.tsx`
  - 位置: L203
  - 操作: 移除 `| ${t('skill.form.owner')}: ${created_by}` 部分
  - 验证: `cd web && pnpm lint && pnpm type-check`

- [x] **Task 5: 移除 knowledge/page.tsx 中的所有者展示**
  - 文件: `web/src/app/opspilot/(pages)/knowledge/page.tsx`
  - 位置: L236
  - 操作: 移除 `{t('knowledge.form.owner')}: {card.created_by} ｜` 部分
  - 验证: `cd web && pnpm lint && pnpm type-check`

## 验证任务

- [x] **Task 6: 端到端验证**
  - 启动本地环境测试：创建者被移出组后无法看到数据，卡片不显示所有者
