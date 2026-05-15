# 任务清单

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
