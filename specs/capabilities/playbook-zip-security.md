## ADDED Requirements

### Requirement: Playbook ZIP 解压必须使用安全函数

Playbook ZIP 文件解压时，系统 SHALL 使用 `_safe_extract_zip()` 函数同时执行路径安全检查和资源限制检查，防止路径遍历、符号链接写入以及异常 archive expansion 导致的磁盘或内存压力。

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

#### Scenario: ZIP 成员数量超限被拒绝
- **WHEN** Playbook ZIP 成员数量超过配置上限
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: ZIP 解压总量超限被拒绝
- **WHEN** Playbook ZIP 的总展开字节数超过配置上限
- **THEN** 系统拒绝解压并抛出 ValueError
