# Spec: Playbook 文件预览

## ADDED Requirements

### Requirement: 后端提供文件内容预览 API

系统 SHALL 提供 API 端点 `GET /job_mgmt/api/playbook/{id}/preview_file/`，允许用户获取 Playbook 压缩包内指定文件的内容。

**请求参数**:
- `file_path` (query, required): 文件在压缩包内的相对路径

**响应格式**:
```json
{
  "file_name": "main.yml",
  "file_path": "roles/example/tasks/main.yml", 
  "content": "---\n- name: Print hello\n  debug:\n    msg: \"{{ message }}\"",
  "file_type": "yaml",
  "file_size": 128
}
```

**权限**: 复用 `playbook_library-View` 权限

#### Scenario: 成功预览 YAML 文件
- **WHEN** 用户请求 `GET /job_mgmt/api/playbook/1/preview_file/?file_path=roles/example/tasks/main.yml`
- **THEN** 系统返回 200，响应包含 `content` 字段为文件内容，`file_type` 为 `yaml`

#### Scenario: 成功预览 Markdown 文件
- **WHEN** 用户请求 `GET /job_mgmt/api/playbook/1/preview_file/?file_path=README.md`
- **THEN** 系统返回 200，响应包含 `content` 字段为文件内容，`file_type` 为 `markdown`

#### Scenario: 文件路径不存在
- **WHEN** 用户请求的 `file_path` 不在压缩包文件列表中
- **THEN** 系统返回 404，响应包含错误信息 `{"detail": "文件不存在"}`

#### Scenario: 缺少 file_path 参数
- **WHEN** 用户请求未提供 `file_path` 参数
- **THEN** 系统返回 400，响应包含错误信息 `{"detail": "缺少 file_path 参数"}`

---

### Requirement: 文件大小限制

系统 SHALL 限制可预览文件的最大大小为 1MB。

#### Scenario: 文件超过大小限制
- **WHEN** 用户请求预览的文件大小超过 1MB
- **THEN** 系统返回 413，响应包含 `{"detail": "文件过大，不支持预览", "file_size": <actual_size>}`

#### Scenario: 文件在大小限制内
- **WHEN** 用户请求预览的文件大小不超过 1MB
- **THEN** 系统正常返回文件内容

---

### Requirement: 二进制文件检测

系统 SHALL 检测并拒绝预览二进制文件。

**二进制文件判定规则**:
1. 文件扩展名为 `.pyc`, `.pyo`, `.so`, `.dll`, `.exe`, `.bin`, `.tar`, `.gz`, `.zip` 等
2. 文件内容前 8KB 包含 null 字节 (`\x00`)

#### Scenario: 请求预览二进制文件
- **WHEN** 用户请求预览 `.pyc` 或其他二进制文件
- **THEN** 系统返回 400，响应包含 `{"detail": "不支持预览二进制文件"}`

#### Scenario: 请求预览文本文件
- **WHEN** 用户请求预览 `.yml`, `.md`, `.py`, `.sh` 等文本文件
- **THEN** 系统正常返回文件内容

---

### Requirement: 路径安全验证

系统 SHALL 验证 `file_path` 参数，防止路径遍历攻击。

#### Scenario: 路径包含 ..
- **WHEN** 用户请求 `file_path=../../../etc/passwd`
- **THEN** 系统返回 400，响应包含 `{"detail": "非法文件路径"}`

#### Scenario: 路径以 / 开头
- **WHEN** 用户请求 `file_path=/etc/passwd`
- **THEN** 系统返回 400，响应包含 `{"detail": "非法文件路径"}`

#### Scenario: 合法相对路径
- **WHEN** 用户请求 `file_path=roles/example/tasks/main.yml`
- **THEN** 系统正常处理请求

---

### Requirement: 预览前必须校验归档资源上限

系统 SHALL 在 Playbook 文件预览前校验归档总大小和可接受的 archive 元数据范围，避免通过预览路径触发整包高内存处理。

#### Scenario: 超大归档预览被拒绝
- **WHEN** 用户请求预览的 Playbook 归档总大小超过配置限制
- **THEN** 系统返回拒绝结果而不是先将整包读入内存

#### Scenario: 合法归档仍可预览目标文件
- **WHEN** 用户请求预览的 Playbook 归档在配置限制内且目标成员满足现有文本预览规则
- **THEN** 系统正常返回目标文件内容

---

### Requirement: 前端预览按钮绑定点击事件

前端 SHALL 为文件列表中的"预览"按钮绑定点击事件，点击后调用预览 API 并显示内容。

#### Scenario: 点击预览按钮
- **WHEN** 用户在文件列表中点击某文件的"预览"按钮
- **THEN** 系统调用 `GET /job_mgmt/api/playbook/{id}/preview_file/?file_path=<path>` 获取内容
- **AND** 弹出预览弹窗显示文件内容

#### Scenario: 预览加载中状态
- **WHEN** 用户点击预览按钮，API 请求进行中
- **THEN** 弹窗显示加载状态（Spin 组件）

#### Scenario: 预览失败
- **WHEN** API 返回错误（404/400/413）
- **THEN** 弹窗显示错误信息

---

### Requirement: 前端代码语法高亮

前端 SHALL 根据文件类型对预览内容应用语法高亮。

**支持的文件类型**:
| 扩展名 | 高亮语言 |
|--------|----------|
| .yml, .yaml | yaml |
| .md | markdown |
| .py | python |
| .sh | bash |
| .json | json |
| .j2, .jinja2 | django (jinja2) |
| 其他 | plaintext |

#### Scenario: YAML 文件高亮
- **WHEN** 预览 `.yml` 文件
- **THEN** 内容使用 YAML 语法高亮显示

#### Scenario: Python 文件高亮
- **WHEN** 预览 `.py` 文件
- **THEN** 内容使用 Python 语法高亮显示

#### Scenario: 未知类型文件
- **WHEN** 预览 `.txt` 或无扩展名文件
- **THEN** 内容以纯文本显示，无高亮

---

### Requirement: 预览弹窗 UI

前端 SHALL 提供预览弹窗，包含以下元素：
- 标题：显示文件名
- 内容区：显示文件内容（带语法高亮）
- 关闭按钮：关闭弹窗

#### Scenario: 打开预览弹窗
- **WHEN** 用户点击预览按钮且 API 返回成功
- **THEN** 弹窗标题显示文件名（如 "预览: main.yml"）
- **AND** 内容区显示文件内容

#### Scenario: 关闭预览弹窗
- **WHEN** 用户点击弹窗关闭按钮或弹窗外区域
- **THEN** 弹窗关闭，返回文件列表视图

#### Scenario: 长文件滚动
- **WHEN** 文件内容超过弹窗可视区域
- **THEN** 内容区可滚动查看完整内容
