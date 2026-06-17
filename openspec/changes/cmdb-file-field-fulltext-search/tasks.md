# Tasks

遵循 TDD：先写失败测试再实现。测试约定见 `server/docs/testing-guide.md`。
环境说明：本 worktree 装有 `cmdb_enterprise`，`is_file_attr_type('attachment'/'image')` 为真；
带 `@pytest.mark.django_db` 的用例会连远端 10.10.41.149 Postgres（超时），故新用例尽量不依赖 DB。

## 1. `convert_file` 纯函数（文件名词干） ✅

- [x] 1.1 失败用例覆盖：单文件去扩展名、多文件分隔、去路径(basename)、Windows 路径、复合扩展名只去最后一段、无扩展名保留、空值/空列表→""、JSON 字符串输入、解析失败→""、无 name 项跳过。（`tests/test_display_field.py`）
- [x] 1.2 实现 `DisplayFieldConverter.convert_file`（`display_field/handler.py`）。
- [x] 1.3 全绿。

## 2. `build_display_fields` 识别文件类型 ✅

- [x] 2.1 失败用例：注册假企业扩展 → attachment/image 字段产出正确 `_display`；解析失败 `_display=""` 而非原始 JSON；社区(摘除 model_ops 槽位)不产出。
- [x] 2.2 实现：`build_display_fields` 增加 `is_file_attr_type` 分支 + 文件型 except 降级 `""`。
- [x] 2.3 社区无企业版回归用例（显式 pop `model_ops`）。
- [x] 2.4 全绿。

## 3. 排除链路确认 ✅

- [x] 3.1 `ExcludeFieldsCache._build_exclude_fields` 测试：原始文件字段 `doc` 被排除、`status` 被排除、`inst_name` 不排除、`doc_display`/`status_display` **不**排除（确保冗余可搜索）。
- [x] 3.2 `remove_display_fields` 剥离 `*_display`（既有用例覆盖）。
- [~] 3.3 全文检索三个 `full_text*` 方法无需改动：已遍历 `keys(n)` 并排除原始 attr_id，`_display` 自动纳入检索（设计确认，无代码改动）。

## 4. 存量回填（模型字段变更钩子） ✅

- [x] 4.1 失败用例：`rebuild_file_instances_display` 回填含文件值实例的文件名词干、无文件值实例不写、空实例集返回 0。（`tests/test_model_service_methods.py`，fake_graph，无 DB）
- [x] 4.2 实现 `ModelManage.rebuild_file_instances_display`（`services/model.py`，沿用 enum 范式）。
- [x] 4.3 视图 `model_attr_update` 增加 `elif is_file_attr_type(attr_type)` 触发回填（`views/model.py` + import）。
- [x] 4.4 视图用例 `test_model_attr_update_file_triggers_rebuild`（`tests/test_model_views.py`，django_db → 仅 CI 执行；本地远端 DB 不可达）。
- [x] 4.5 视图模块 import 冒烟校验（无循环导入/拼写错）。

## 5. 收尾

- [x] 5.1 触达的离线用例全绿（33 passed）：convert_file/build_display/exclude/rebuild_file/remove_display。
- [ ] 5.2 在有测试 DB 的 CI 上跑全量 `cd server && make test`，确认 django_db 用例（含 enum/org/user 转换、view 测试）无回归。
- [ ] 5.3 真机/集成验证：建含附件字段的模型→上传 `report.pdf`→全文检索 `report` 命中、`pdf`/URL 片段不命中。
- [ ] 5.4 （可选）一次性管理命令 `rebuild_file_display` 全量回填——按 design Open Question 决策。
- [x] 5.5 更新记忆 `cmdb-file-field-feature-state`：补「文件字段已支持按文件名词干全文检索 + 回填钩子」；并纠正「cmdb_enterprise 在本 worktree 实为已安装」。