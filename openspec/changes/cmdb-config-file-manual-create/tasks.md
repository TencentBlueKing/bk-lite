## Tasks

### 1. 后端 Model 改造

- [x] `server/apps/cmdb/models/config_file_version.py`：`collect_task` 字段改为 `null=True, blank=True, on_delete=models.SET_NULL`
- [ ] 生成并应用 migration：`python manage.py makemigrations cmdb && python manage.py migrate`（需在有依赖环境中执行）

### 2. 后端权限改造

- [x] `server/apps/cmdb/views/config_file.py`：去掉 `get_filtered_queryset` 方法中对 `filter_queryset_by_task_permission` 的调用
- [x] 新增实例权限校验工具方法：根据 `instance_id` + `model_id` 调用现有的 `check_instance_permission` 校验 View 权限
- [x] 在 `list`、`content`、`diff`、`file_list`、`destroy` 接口入口处加入实例权限校验
- [x] `file_list` 接口去掉 `visible_paths` 二次过滤逻辑，直接返回 `ConfigFileService.get_file_list(instance_id)` 结果

### 3. 后端新增手动创建接口

- [x] `server/apps/cmdb/views/config_file.py`：新增 `create_manual` action（`POST`）
- [x] 接口逻辑：
  - 校验实例权限（Edit 或 Operate）
  - 校验 `file_path` 非空
  - 从 `file_path` 提取 `file_name`（复用 `extract_file_name`）
  - 生成 `version`（当前时间戳毫秒）
  - 计算 `content_hash`（SHA256）
  - 查重：同 `instance_id + file_path` 最新成功版本 hash 相同则返回"无变化"
  - 存储内容到 MinIO（复用 `save_content` + `build_object_key`）
  - 创建 `ConfigFileVersion` 记录：`collect_task=None, status="success"`
  - 返回新记录信息
- [x] `server/apps/cmdb/services/config_file_service.py`：新增 `create_manual_version` 类方法封装上述逻辑

### 4. 后端 file_list 接口适配

- [x] `ConfigFileService.get_file_list` 确认对 `collect_task=None` 的记录正常返回
- [x] 接口返回字段中补充 `collect_task_id`（已有），前端用来判断来源

### 5. 前端 API 层

- [x] `web/src/app/cmdb/api/configFile.ts`：新增 `createManualConfigFile` 方法，调用 `POST /cmdb/api/config_file_versions/create_manual/`

### 6. 前端页面改造

- [x] `web/src/app/cmdb/(pages)/assetData/detail/configFiles/page.tsx`：
  - 表格上方右侧新增"手动新增"按钮
  - 新增手动新增 Drawer 组件（文件路径 Input + 文件内容 Textarea + 上传文件按钮）
  - 表单校验：文件路径必填且以 `/` 开头，内容必填且 ≤5MB
  - 提交成功后刷新列表
  - 表格 columns 新增"来源"列（根据 `collect_task_id` 是否有值显示 Tag）
  - 空状态文案修改："当前实例暂无配置文件采集记录" → "当前实例暂无配置文件记录"

### 7. 前端类型补充

- [x] `web/src/app/cmdb/types/configFile.ts`：补充 `CreateManualConfigFileParams` 接口类型

### 8. 测试验证

- [x] 后端：手动创建接口单测（正常创建、内容重复、权限拒绝）
- [x] 前端：手动新增 → 列表刷新 → 查看内容 → 版本对比，端到端验证
