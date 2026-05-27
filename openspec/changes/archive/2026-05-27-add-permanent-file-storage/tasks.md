## 1. Model 层修改

- [x] 1.1 在 `DistributionFile` 模型添加 `is_permanent` 字段（`BooleanField(default=False)`）
- [x] 1.2 更新模型 docstring 说明新字段用途
- [x] 1.3 执行 `makemigrations` 生成迁移文件
- [x] 1.4 执行 `migrate` 应用迁移

## 2. 对外 API 层修改

- [x] 2.1 修改 `OpenFileUploadView.post` 方法，解析 `permanent` 参数
- [x] 2.2 创建 `DistributionFile` 记录时传入 `is_permanent` 值
- [x] 2.3 更新 API docstring 说明新参数
- [x] 2.4 **确认内部接口 `DistributionFileViewSet.upload` 不做修改**（保持临时保存）

## 3. 清理任务修改

- [x] 3.1 修改 `cleanup_expired_distribution_files_task` 查询条件，添加 `is_permanent=False` 过滤

## 4. 文档更新

- [x] 4.1 更新 `open_api.md` 文档，说明 `permanent` 参数用法

## 5. 测试验证

- [x] 5.1 更新 `test_open_upload.py`，添加永久文件上传测试用例
- [x] 5.2 运行 `make test` 确保所有测试通过
