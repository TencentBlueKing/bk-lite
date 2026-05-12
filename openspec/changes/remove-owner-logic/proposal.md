# 移除所有者权限逻辑

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
