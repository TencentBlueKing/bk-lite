# 脚本库组织字段必填验证

## 问题

脚本库页面 (`/job/template/script-library`) 的新增/编辑脚本功能中，**组织 (team) 字段缺少必填验证**。

当前状态：
- 前端：无 required 验证规则
- 后端：无 validate_team 验证方法
- 模型：`team = JSONField(default=list)` 允许空列表

## 影响

1. **数据隔离问题**：无组织归属的脚本，权限控制失效
2. **可发现性问题**：按组织筛选时，无组织脚本会"消失"
3. **数据一致性**：违反业务规则（脚本必须归属组织）

## 解决方案

前后端同时添加必填验证：

### 前端
- 文件：`web/src/app/job/(pages)/template/script-library/page.tsx`
- 修改：Form.Item 添加 `rules={[{ required: true, message: t('job.organizationRequired') }]}`

### 后端
- 文件：`server/apps/job_mgmt/serializers/script.py`
- 修改：ScriptCreateSerializer 和 ScriptUpdateSerializer 添加 `validate_team` 方法

## 不处理

- 存量数据迁移（按用户要求不处理）

## 验证标准

- [ ] 前端新增脚本时，组织为空提交会显示错误提示
- [ ] 前端编辑脚本时，清空组织提交会显示错误提示
- [ ] 后端 POST /api/script/ 不带 team 返回 400
- [ ] 后端 PUT /api/script/{id}/ team 为空返回 400
