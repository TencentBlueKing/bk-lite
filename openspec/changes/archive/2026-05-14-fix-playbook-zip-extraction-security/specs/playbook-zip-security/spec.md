## ADDED Requirements

### Requirement: Playbook ZIP 解压必须使用安全函数

Playbook ZIP 文件解压时，系统 SHALL 使用 `_safe_extract_zip()` 函数进行安全检查，防止路径遍历攻击。

#### Scenario: 正常 ZIP 文件解压成功
- **WHEN** 用户上传包含合法路径的 Playbook ZIP 文件
- **THEN** 系统成功解压文件到 workspace 目录

#### Scenario: 恶意路径遍历 ZIP 被拒绝
- **WHEN** 用户上传包含 `../` 路径遍历条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: 符号链接 ZIP 条目被拒绝
- **WHEN** 用户上传包含符号链接条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: 绝对路径 ZIP 条目被拒绝
- **WHEN** 用户上传包含绝对路径条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError
