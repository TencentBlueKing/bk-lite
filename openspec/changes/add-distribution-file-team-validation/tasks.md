## 1. 模型层修改

- [x] 1.1 在 `DistributionFile` 模型添加 `team` 字段（`IntegerField(null=True, blank=True)`）
- [x] 1.2 生成并执行数据库迁移（`python manage.py makemigrations job_mgmt && python manage.py migrate`）

## 2. 上传接口修改

- [x] 2.1 在 `OpenFileUploadView.post()` 中获取 `user.group_list[0]` 作为 team
- [x] 2.2 添加校验：如果 `user.group_list` 为空，返回 400 错误
- [x] 2.3 创建 `DistributionFile` 时传入 `team` 参数

## 3. 删除接口修改

- [x] 3.1 在 `OpenFileDeleteView.delete()` 中获取当前用户的 team
- [x] 3.2 修改查询条件：`DistributionFile.objects.get(id=file_id, file_key=file_key, team=user_team)`

## 4. 测试验证

- [x] 4.1 更新 `test_open_upload.py` 中的上传测试，验证 team 被正确保存
- [x] 4.2 添加删除测试：同组删除成功
- [x] 4.3 添加删除测试：跨组删除失败（返回 deleted=0）
- [x] 4.4 运行 `make test` 确保所有测试通过
