# 任务清单

## 前端

- [x] **FE-1**: 添加组织字段必填验证规则
  - 文件: `web/src/app/job/(pages)/template/script-library/page.tsx`
  - 修改 Form.Item name="team" 添加 rules
  
- [x] **FE-2**: 添加 i18n 翻译 key (如果不存在)
  - 检查 `job.organizationRequired` 是否存在
  - 不存在则添加中英文翻译

## 后端

- [x] **BE-1**: ScriptCreateSerializer 添加 validate_team
  - 文件: `server/apps/job_mgmt/serializers/script.py`
  - 验证 team 不能为空列表
  
- [x] **BE-2**: ScriptUpdateSerializer 添加 validate_team
  - 文件: `server/apps/job_mgmt/serializers/script.py`
  - 验证 team 不能为空列表

## 验证

- [x] **QA-1**: 前端验证测试
  - 新增脚本，组织留空，点击保存，应显示错误
  - 编辑脚本，清空组织，点击保存，应显示错误

- [x] **QA-2**: 后端验证测试
  - `cd server && make test` 通过（如有相关测试）
  - 或手动测试 API
