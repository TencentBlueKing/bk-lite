## ADDED Requirements

### Requirement: 文件上传时记录团队归属

系统 SHALL 在文件上传时记录当前用户的团队 ID（取 `user.group_list[0]`）。

#### Scenario: 正常上传记录 team
- **WHEN** 用户通过 `POST /api/v1/job_mgmt/api/open/upload_file` 上传文件
- **THEN** 系统创建 `DistributionFile` 记录，`team` 字段为当前用户的 `group_list[0]`

#### Scenario: 用户无 team 时上传失败
- **WHEN** 用户的 `group_list` 为空
- **THEN** 系统返回 400 错误，提示 "用户未关联团队"

### Requirement: 文件删除时校验团队归属

系统 SHALL 在删除文件时校验文件的 `team` 与当前用户的 `team` 一致。

#### Scenario: 同组用户删除成功
- **WHEN** 用户请求删除文件，且文件的 `team` 与用户的 `group_list[0]` 一致
- **THEN** 系统删除文件并返回成功

#### Scenario: 跨组删除被拒绝
- **WHEN** 用户请求删除文件，但文件的 `team` 与用户的 `group_list[0]` 不一致
- **THEN** 系统不删除文件（视为文件不存在），返回 `deleted: 0`

#### Scenario: 历史文件（无 team）无法删除
- **WHEN** 用户请求删除 `team=None` 的历史文件
- **THEN** 系统不删除文件（team 校验失败），返回 `deleted: 0`
