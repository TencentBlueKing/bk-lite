## Why

CMDB 配置文件功能当前只支持通过采集任务（Stargazer 远程读取）获取配置文件版本。用户无法在页面上手动录入配置文件内容，导致以下问题：

- 没有远程采集条件的主机（如网络隔离、未部署 Agent）无法管理配置文件
- 用户想要备份或登记一份配置文件，必须先创建采集任务再触发采集，流程繁琐
- 权限模型挂在采集任务上，逻辑间接且不直觉——配置文件是实例的附属物，权限应该跟实例走

## What Changes

- 在主机实例详情页的"配置文件" Tab 表格上方新增"手动新增"入口
- 用户填写文件路径和文件内容（粘贴或上传文本文件），提交后直接创建一个配置文件版本记录
- 手动新增的记录与采集记录共存于同一版本列表，支持 diff 对比
- 通过 `collect_task` 是否为空区分来源（手动/采集），前端表格新增"来源"列展示
- 配置文件权限模型从"采集任务维度"改为"实例维度"：对实例有 View 权限即可查看其所有配置文件

## Capabilities

### New Capabilities

- `cmdb-config-file-manual-create`: 支持在主机实例详情页手动新增配置文件，填写文件路径和内容直接创建版本记录。

### Modified Capabilities

- 配置文件权限控制从采集任务维度改为实例 View 权限维度。

## Impact

- **后端 Model**:
  - `server/apps/cmdb/models/config_file_version.py` — `collect_task` 改为可空
- **后端 API**:
  - `server/apps/cmdb/views/config_file.py` — 新增 `create_manual` action；权限逻辑从 `filter_queryset_by_task_permission` 改为校验实例 View 权限
  - `server/apps/cmdb/services/config_file_service.py` — 新增手动创建逻辑；去掉或改造 `filter_queryset_by_task_permission`
- **前端页面**:
  - `web/src/app/cmdb/(pages)/assetData/detail/configFiles/page.tsx` — 新增按钮、手动新增抽屉表单、来源列
  - `web/src/app/cmdb/api/configFile.ts` — 新增 `createManualConfigFile` API 方法
  - `web/src/app/cmdb/types/configFile.ts` — 补充类型定义
- **不在本次范围**:
  - 不扩展配置文件功能到非 host 模型
  - 不做手动编辑已有版本功能（只新增，不修改）
  - 不改变采集任务本身的逻辑
