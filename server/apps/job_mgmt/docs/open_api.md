# 作业管理开放接口文档

> 供第三方 App（如补丁管理）调用作业管理能力

## 概览

| 接口 | 通道 | 鉴权 | 说明 |
|------|------|------|------|
| 查询节点列表 | NATS `bklite.node_list` | 无 | 同步，分页返回节点 |
| 查询目标列表 | NATS `bklite.job_target_list` | 无 | 同步，分页返回目标 |
| 查询目标列表 v2 | OpenAPI `POST /openapi/v1/job-mgmt/targets-v2` | Authorization Bearer | 同步，有上界键集分页 |
| 作业列表 | NATS `bklite.job_list` | 无 | 同步，返回脚本库与 Playbook 及参数定义 |
| 作业列表 | REST `GET /api/v1/job_mgmt/api/open/job_list` | Api-Authorization | 同步，执行前获取作业背景信息 |
| 脚本执行 | NATS `bklite.job_script_execute` | 无 | 异步，返回 task_id |
| 脚本执行 | REST `POST /api/v1/job_mgmt/api/open/script_execute` | Api-Authorization | 异步，返回 task_id |
| 脚本执行（推荐） | OpenAPI `POST /openapi/v1/job-mgmt/script-execute` | Authorization Bearer | 异步，团队由 Secret 绑定 |
| 批量查询状态 | REST `POST /api/v1/job_mgmt/api/open/job_status` | Api-Authorization | 同步，按 task_ids 查询状态 |
| 批量查询状态（推荐） | OpenAPI `POST /openapi/v1/job-mgmt/job-status` | Authorization Bearer | 同步，跨组织按不存在返回 |
| 查询作业详情 | REST `GET /api/v1/job_mgmt/api/open/job_detail/{task_id}` | Api-Authorization | 同步，返回执行详情与状态 |
| 查询作业详情（推荐） | OpenAPI `GET /openapi/v1/job-mgmt/job-detail` | Authorization Bearer | 同步，task_id 走 query；跨组织按不存在返回 |
| 文件上传 | REST `POST /api/v1/job_mgmt/api/open/upload_file` | Api-Authorization | 同步，返回 file_id + file_key |
| 文件删除 | REST `DELETE /api/v1/job_mgmt/api/open/delete_file` | Api-Authorization | 同步，删除文件 |
| 文件分发（推荐） | OpenAPI `POST /openapi/v1/job-mgmt/file-distribute` | Authorization Bearer | 异步，团队由 Secret 绑定 |
| 文件分发（旧版） | NATS `bklite.job_file_distribute` | 无 | 迁移兼容，异步返回 task_id |
| 批量查询状态 | NATS `bklite.job_status_batch_query` | 无 | 同步 |
| 查询作业详情 | NATS `bklite.job_detail_query` | 无 | 同步 |

## 鉴权说明

### NATS 接口
NATS subject 前缀由 `NATS_NAMESPACE` 配置决定（默认 `bklite`）。

旧版 `job_file_distribute` 暂时保留供存量调用迁移和紧急回滚；新接入必须使用统一 OpenAPI 网关。
listener subject 日志用于流量计数，NATS 连接审计用于识别存量调用方；已知调用全部迁移且观测窗口归零后，设
`JOB_FILE_DISTRIBUTE_NATS_ENABLED=0` 拒绝旧入口。若新路径异常，置回 `1` 即可回滚，不回滚已签发 Secret 和网关审计。
NATS 旧入口仍按现有契约信任内网通道，请求自报 `team` 不是可信身份。

### REST 接口
使用 `UserAPISecret` 的 `api_secret` 作为 token：

```
Api-Authorization: <api_secret>
```

`api_secret` 可在系统管理中创建，绑定特定用户和团队。作业列表、脚本执行与状态查询的团队以 Secret 绑定为准，请求体中的 `team` 会被忽略；跨团队任务按不存在处理。

---

## 调用流程

```
┌──────────────┐                                    ┌──────────────────┐
│  第三方 App   │                                    │   BK-Lite Server │
└──────┬───────┘                                    └────────┬─────────┘
       │                                                      │
       │  1. REST: POST /api/v1/job_mgmt/api/open/upload_file  │
       │─────────────────────────────────────────────────────▶│
       │◀──────────────────── { file_key } ──────────────────│
       │                                                      │
       │  2. NATS: bklite.job_script_execute                  │
       │─────────────────────────────────────────────────────▶│
       │◀─────────────────── { task_id } ─────────────────────│
       │                                                      │
       │  3. POST /openapi/v1/job-mgmt/file-distribute        │
       │     Authorization: Bearer + { file_keys, ... }       │
       │─────────────────────────────────────────────────────▶│
       │◀─────────────────── { task_id } ─────────────────────│
       │                                                      │
       │          ... 等待执行 ...                             │
       │                                                      │
       │  4. NATS: bklite.job_detail_query (查询结果)           │
       │◀─────────────── { task_id, status } ─────────────────│
       │                                                      │
       │  5. 未完成时可按 task_id 重复查询                │
       │─────────────────────────────────────────────────────▶│
       │◀─────────── { execution_results, ... } ──────────────│
```

---

## REST 作业列表、执行与状态查询

与文件上传/删除相同：`Api-Authorization` 鉴权，路径挂在 `/api/v1/job_mgmt/api/open/` 下。请求体与对应 NATS 接口一致；`team` 由 Secret 绑定团队写入，调用方传入的 `team` 无效。

### 查询作业列表

**REST**: `GET /api/v1/job_mgmt/api/open/job_list`

返回当前团队脚本库与 Playbook 的作业信息及参数定义，供执行前获取背景信息。不含脚本内容 / Playbook 文件。加密参数的 `default` 以 `******` 返回。

Query：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 按名称模糊搜索 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，最大 100 |

成功返回：

```json
{
  "scripts": {
    "count": 1,
    "items": [
      {
        "id": 12,
        "job_type": "script",
        "name": "补丁安装",
        "description": "安装安全补丁",
        "script_type": "shell",
        "params": [
          {"name": "pkg", "label": "包名", "description": "rpm", "default": "openssl", "is_encrypted": false}
        ],
        "timeout": 120,
        "is_built_in": false
      }
    ]
  },
  "playbooks": {
    "count": 1,
    "items": [
      {
        "id": 3,
        "job_type": "playbook",
        "name": "nginx-deploy",
        "description": "部署 nginx",
        "version": "v1.0.0",
        "params": [{"name": "port", "default": "80", "description": "监听端口"}]
      }
    ]
  }
}
```

### 脚本执行

**REST**: `POST /api/v1/job_mgmt/api/open/script_execute`

请求字段见下方 NATS `job_script_execute`。成功返回 `{"task_id": 123}`。

### 批量查询作业状态

**REST**: `POST /api/v1/job_mgmt/api/open/job_status`

```json
{"task_ids": [123, 456]}
```

最多 100 个 ID。当前团队任务返回状态计数；其他团队或缺失返回 `{"task_id": ..., "status": "not_found"}`。

### 查询作业详情

**REST**: `GET /api/v1/job_mgmt/api/open/job_detail/{task_id}`

返回字段见下方 NATS `job_detail_query`。跨团队与不存在统一 404。

---

## 接口详情

### 1. 查询节点列表

**NATS Subject**: `bklite.node_list`

> 节点管理模块已有接口，无需传入组/权限参数即可查询所有节点。用于构建 `target_list` 中 `node_mgmt` 来源的目标。

**Request:**
```json
{
  "name": "web",
  "ip": "10.0",
  "os": "linux",
  "cloud_region_id": "region-1",
  "is_active": true,
  "page": 1,
  "page_size": 20
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 按名称模糊搜索 |
| ip | string | 否 | 按IP模糊搜索 |
| os | string | 否 | `linux` 或 `windows` |
| cloud_region_id | string | 否 | 云区域ID |
| is_active | bool | 否 | 是否在线 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 10，传 `-1` 返回全部 |

**Response:**
```json
{
  "count": 50,
  "nodes": [
    {
      "id": "node-abc123",
      "name": "web-01",
      "ip": "10.0.0.1",
      "operating_system": "linux",
      "cloud_region_id": "region-1"
    }
  ]
}
```

---

### 2. 查询目标列表

**NATS Subject**: `bklite.job_target_list`

> 作业管理的目标（Target）是预先配置好连接凭据的机器，可直接用于构建 `target_list` 中 `manual` 来源的目标。

**Request:**
```json
{
  "name": "web",
  "ip": "10.0",
  "os_type": "linux",
  "page": 1,
  "page_size": 20
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 按名称模糊搜索 |
| ip | string | 否 | 按IP模糊搜索 |
| os_type | string | 否 | `linux` 或 `windows` |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，传 `-1` 返回全部 |

**Response:**
```json
{
  "result": true,
  "data": {
    "count": 10,
    "items": [
      {
        "target_id": 1,
        "name": "web-01",
        "ip": "10.0.0.1",
        "os_type": "linux",
        "cloud_region_id": 1
      }
    ]
  }
}
```

> 兼容说明：该 v1 入口保留 `page_size=-1` 的“返回全部”语义。新调用方应优先使用下方 v2，避免单次返回无上界。

---

### 2.1 查询目标列表 v2（推荐）

**OpenAPI**: `POST /openapi/v1/job-mgmt/targets-v2`

v2 由统一网关验证 Bearer 凭据、审计请求并注入不可伪造的授权团队，业务层在数据库内过滤目标，再使用按 `target_id` 降序的键集分页。调用方不得提交 `team`、`caller_token` 或其他身份字段。每页最多返回 100 条，不支持 `page_size=-1`。部署可用 `JOB_TARGET_LIST_V2_MAX_PAGE_SIZE` 在 1-100 内下调上限；非法值或超过 100 时恢复为 100。

v2 默认关闭。滚动发布时，须先完成新版本部署并确认旧进程全部退出，再运行 `python manage.py reconcile_target_team_memberships --apply`，随后运行同命令的 `--check` 模式确认零漂移，最后设置 `JOB_TARGET_LIST_V2_ENABLED=true` 并滚动重启。未完成校验前不得启用，以避免迁移回填期间的旧进程写入造成授权投影漂移。回滚时先将该开关恢复为 `false` 并确认所有实例停止接收 v2 请求，再回滚应用；投影表是可重建数据，不影响保留的 v1 读路径。若必须回退 migration，仅在 v2 已停用且旧版本已全部恢复后执行反向迁移；重新发布时再次按上述顺序回填与校验。

**Request:**
```json
{
  "name": "web",
  "ip": "10.0",
  "os_type": "linux",
  "page_size": 20,
  "cursor": 1234
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 按名称模糊搜索 |
| ip | string | 否 | 按 IP 模糊搜索 |
| os_type | string | 否 | `linux` 或 `windows` |
| page_size | int | 否 | 每页最大返回数量，默认 20，范围 1-100 |
| cursor | int | 否 | 上一页返回的 `next_cursor`；首页不传 |

**Response:**
```json
{
  "result": true,
  "data": {
    "items": [],
    "next_cursor": 1200,
    "has_more": true
  }
}
```

`has_more=false` 时 `next_cursor` 为 `null`。v2 不返回需要扫描全部命中记录的精确总数。

键集分页在固定筛选条件下不会重复返回同一目标，但不是一致性快照：翻页期间新增的目标可能不进入本轮后续页，删除、团队权限或筛选字段变化可能导致跳项。

---

### 2.2 查询作业列表

**NATS Subject**: `bklite.job_list`

返回当前团队脚本库与 Playbook 的作业信息及参数定义。不含脚本内容 / Playbook 文件。加密参数的 `default` 以 `******` 返回。

**Request:**
```json
{
  "team": [1],
  "name": "补丁",
  "page": 1,
  "page_size": 20
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| team | array | 是 | 团队 ID 列表 |
| name | string | 否 | 按名称模糊搜索 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，最大 100 |

响应字段与 REST `GET /api/v1/job_mgmt/api/open/job_list` 相同。

---

### 3. 脚本执行

**NATS Subject**: `bklite.job_script_execute`

**Request:**
```json
{
  "name": "补丁安装-20260430",
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "xxx", "name": "web-01", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": "region-1"}
  ],
  "script_type": "shell",
  "script_content": "yum update -y xxx",
  "params": [],
  "timeout": 600,
  "team": [1],
  "callback_url": "http://patch-mgmt:8080/api/callback/task_done"
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 作业名称 |
| target_source | string | 是 | `node_mgmt`（节点管理）或 `manual`（目标管理） |
| target_list | array | 是 | 目标列表 |
| script_type | string | 是 | `shell` / `python` / `powershell` / `bat` |
| script_content | string | 是 | 脚本内容 |
| params | array | 否 | 参数列表 `[{name, value}]`，**按顺序传递位置参数**（见下方说明） |
| timeout | int | 否 | 超时秒数，默认 600 |
| team | array | 是 | 团队 ID 列表 |
| callback_url | string | 否 | 任务完成回调地址 |

**target_list 格式：**

- `node_mgmt`: `{"node_id": "xxx", "name": "xxx", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": "xxx"}`
- `manual`: `{"target_id": 1, "name": "xxx", "ip": "1.2.3.4"}`

**params 参数说明：**

> ⚠️ **重要**：`params` 是**顺序位置参数**，不是键值对匹配。系统会按数组顺序将各项的 `value` 拼接为命令行参数传给脚本，`name` 字段仅作可读性标注，不参与实际传递。
>
> 例如 `"params": [{"name": "dir", "value": "/tmp"}, {"name": "days", "value": "7"}]`
> 实际传递给脚本的是：`/tmp 7`（按顺序，第一个参数是 `/tmp`，第二个是 `7`）
>
> 脚本中获取参数的方式：
> | 脚本类型 | 第1个参数 | 第2个参数 |
> |----------|-----------|-----------|
> | shell | `$1` | `$2` |
> | python | `sys.argv[1]` | `sys.argv[2]` |
> | powershell | `$args[0]` | `$args[1]` |
> | bat | `%1` | `%2` |

**完整调用示例：**

示例 1：使用 node_mgmt 来源，在两台 Linux 节点上执行 shell 脚本安装补丁
```json
{
  "name": "安装安全补丁-CVE-2026-1234",
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "node-a1b2c3", "name": "web-01", "ip": "10.0.1.10", "os": "linux", "cloud_region_id": "region-bj"},
    {"node_id": "node-d4e5f6", "name": "web-02", "ip": "10.0.1.11", "os": "linux", "cloud_region_id": "region-bj"}
  ],
  "script_type": "shell",
  "script_content": "#!/bin/bash\nyum install -y patch-CVE-2026-1234\nsystemctl restart nginx",
  "params": [],
  "timeout": 300,
  "team": [1],
  "callback_url": "http://patch-mgmt:8080/api/v1/callback/task_done"
}
```

示例 2：shell 带参数（参数按位置传递，脚本中通过 `$1` `$2` 获取）
```json
{
  "name": "清理日志",
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "node-a1b2c3", "name": "web-01", "ip": "10.0.1.10", "os": "linux", "cloud_region_id": "region-bj"}
  ],
  "script_type": "shell",
  "script_content": "#!/bin/bash\nlog_dir=$1\ndays=$2\nfind \"$log_dir\" -name '*.log' -mtime +$days -delete\necho \"已清理 $log_dir 中 $days 天前的日志\"",
  "params": [{"name": "log_dir", "value": "/var/log/app"}, {"name": "days", "value": "30"}],
  "timeout": 120,
  "team": [1]
}
```

示例 3：python 带参数（参数按位置传递，脚本中通过 `sys.argv[1]` `sys.argv[2]` 获取）
```json
{
  "name": "检查磁盘使用率",
  "target_source": "manual",
  "target_list": [
    {"target_id": 5, "name": "db-01", "ip": "10.0.2.20"}
  ],
  "script_type": "python",
  "script_content": "import os, sys\nthreshold = int(sys.argv[1])\npath = sys.argv[2]\nusage = os.popen(f'df {path}').read()\nprint(usage)",
  "params": [{"name": "threshold", "value": "80"}, {"name": "path", "value": "/data"}],
  "timeout": 60,
  "team": [1],
  "callback_url": "http://monitor:9090/api/disk_alert"
}
```

示例 4：powershell 带参数（参数按位置传递，脚本中通过 `$args[0]` `$args[1]` 获取）
```json
{
  "name": "检查 Windows 服务状态",
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "node-win001", "name": "win-app-01", "ip": "10.0.3.50", "os": "windows", "cloud_region_id": "region-sh"}
  ],
  "script_type": "powershell",
  "script_content": "$serviceName = $args[0]\n$action = $args[1]\n$svc = Get-Service -Name $serviceName\nif ($action -eq 'restart') { Restart-Service $serviceName -Force }\nWrite-Output \"$serviceName status: $($svc.Status)\"",
  "params": [{"name": "service_name", "value": "nginx"}, {"name": "action", "value": "restart"}],
  "timeout": 120,
  "team": [2]
}
```

示例 5：bat 带参数（参数按位置传递，脚本中通过 `%1` `%2` 获取）
```json
{
  "name": "备份目录",
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "node-win002", "name": "win-file-01", "ip": "10.0.3.51", "os": "windows", "cloud_region_id": "region-sh"}
  ],
  "script_type": "bat",
  "script_content": "@echo off\nset src=%1\nset dest=%2\nxcopy \"%src%\" \"%dest%\" /E /I /Y\necho Backup completed from %src% to %dest%",
  "params": [{"name": "src", "value": "D:\\app\\data"}, {"name": "dest", "value": "E:\\backup\\app_data"}],
  "timeout": 600,
  "team": [2],
  "callback_url": "http://backup-mgmt:8080/api/callback/done"
}
```

**Response (成功):**
```json
{"result": true, "data": {"task_id": 123}}
```

**Response (失败):**
```json
{"result": false, "message": "脚本包含高危命令，禁止执行: xxx"}
```

---

### 4. 文件上传

**REST**: `POST /api/v1/job_mgmt/api/open/upload_file`

**Headers:**
```
Api-Authorization: <api_secret>
Content-Type: multipart/form-data
```

**Body (multipart/form-data):**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 要上传的文件 |
| expire_days | int | 否 | 过期天数，默认 `7`，取值范围 `1`–`365` |

**expire_days 参数说明:**
- 默认 `7`：文件在 7 天后由定时任务自动清理
- 所有上传文件都会过期，**不存在永久保存选项**；如需提前删除可调用删除接口
- 非整数、小于 `1` 或大于 `365` 时返回 `400`

**Response (成功):**
```json
{
  "result": true,
  "data": {
    "file_id": 456,
    "file_key": "job-files/2026/04/30/abc123.rpm"
  }
}
```

**Response (失败):**
```json
{"result": false, "message": "token 无效或已过期"}
```

---

### 5. 文件删除

**REST**: `DELETE /api/v1/job_mgmt/api/open/delete_file`

**Headers:**
```
Api-Authorization: <api_secret>
Content-Type: application/json
```

**Body:**
```json
{"files": [{"file_id": 456, "file_key": "job-files/2026/05/06/abc123.rpm"}]}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | array | 是 | 要删除的文件列表 |
| files[].file_id | int | 是 | 上传接口返回的 file_id |
| files[].file_key | string | 是 | 上传接口返回的 file_key |

> ⚠️ **安全校验**：`file_id`、`file_key` 和 API Secret 绑定的团队必须同时匹配才能删除。跨团队文件与不存在文件返回相同结果，防止枚举其他团队的文件。

**Response (成功):**
```json
{"result": true, "data": {"deleted": 1}}
```

**Response (失败):**
```json
{"result": false, "message": "files 不能为空"}
```

> 说明：如果 file_id 与 file_key 不匹配，该条目跳过不删除，不会报错，`deleted` 计数不包含跳过的条目。

---

### 6. 文件分发

**OpenAPI Endpoint（推荐）**: `POST /openapi/v1/job-mgmt/file-distribute`

**鉴权**: `Authorization: Bearer <api_secret>`

服务端使用 API Secret 绑定的唯一活动团队执行。请求 schema 不接受 `team`，也不接受调用方控制的
`callback_url` / `callback_subject`；结果通过作业状态查询获取。网关审计记录凭据主体、团队、路径与结果。

**Request:**
```json
{
  "name": "分发补丁包",
  "file_keys": ["job-files/2026/04/30/abc123.rpm"],
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "xxx", "name": "web-01", "ip": "1.2.3.4", "os": "linux"}
  ],
  "target_path": "/tmp/patches/",
  "overwrite_strategy": "overwrite",
  "timeout": 600
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 作业名称 |
| file_keys | array | 是 | 文件上传接口返回的 file_key 列表 |
| target_source | string | 是 | `node_mgmt` 或 `manual` |
| target_list | array | 是 | 目标列表 |
| target_path | string | 是 | 目标机器上的存放路径 |
| overwrite_strategy | string | 否 | `overwrite`（默认）或 `skip` |
| timeout | int | 否 | 超时秒数，默认 600 |
> ⚠️ **团队隔离**：网关接口仅允许分发 API Secret 绑定活动团队的文件与目标。跨团队、无归属、不存在或格式非法的输入都会在创建作业和派发 Celery 任务前被拒绝。

**Response:** 同脚本执行

---

### 7. 批量查询作业状态

**NATS Subject**: `bklite.job_status_batch_query`

**Request:**
```json
{"task_ids": [123, 456]}
```

**Response:**
```json
{
  "result": true,
  "data": [
    {"task_id": 123, "status": "success", "total_count": 3, "success_count": 3, "failed_count": 0},
    {"task_id": 456, "status": "running", "total_count": 3, "success_count": 1, "failed_count": 0}
  ]
}
```

**status 枚举**: `pending` / `running` / `success` / `failed` / `timeout` / `cancelled` / `not_found`

---

### 8. 查询作业详情

**NATS Subject**: `bklite.job_detail_query`

**Request:**
```json
{"task_id": 123, "team": [1]}
```

兼容旧调用：
```json
{"task_id": 123}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | integer | 是 | 作业执行 ID |
| team | array | 否 | 调用方团队 ID 列表，必须与作业执行记录归属团队有交集；不传时仅返回安全元数据，不返回脚本明文、目标列表和执行结果 |

**Response:**
```json
{
  "result": true,
  "data": {
    "task_id": 123,
    "name": "补丁安装-20260430",
    "job_type": "script",
    "status": "success",
    "script_type": "shell",
    "script_content": "yum update -y xxx",
    "timeout": 600,
    "started_at": "2026-04-30T10:00:00",
    "finished_at": "2026-04-30T10:01:30",
    "total_count": 3,
    "success_count": 3,
    "failed_count": 0,
    "target_list": [...],
    "execution_results": [
      {
        "target_key": "xxx",
        "name": "web-01",
        "ip": "1.2.3.4",
        "status": "success",
        "stdout": "Complete!",
        "stderr": "",
        "exit_code": 0,
        "error_message": ""
      }
    ]
  }
}
```

不传 `team` 的兼容响应只包含安全元数据：
```json
{
  "result": true,
  "data": {
    "task_id": 123,
    "name": "补丁安装-20260430",
    "job_type": "script",
    "status": "success",
    "timeout": 600,
    "started_at": "2026-04-30T10:00:00",
    "finished_at": "2026-04-30T10:01:30",
    "total_count": 3,
    "success_count": 3,
    "failed_count": 0,
    "detail_limited": true,
    "requires_team": true
  }
}
```

---

## 回调机制

### 触发条件
当异步任务（脚本执行 / 文件分发）进入终态（`success` / `failed` / `timeout`）且调用时传入了 `callback_url`，server 将主动 HTTP POST 通知调用方。

### 回调 Body
```json
{
  "task_id": 123,
  "status": "success",
  "total_count": 3,
  "success_count": 3,
  "failed_count": 0,
  "finished_at": "2026-04-30T10:01:30"
}
```

### 重试策略
- 失败时指数退避重试：1s → 2s → 4s
- 最多重试 3 次，超过后放弃
- 调用方应实现 `job_status_batch_query` 轮询兜底

### 调用方要求
- 回调接口应返回 HTTP 2xx 表示接收成功
- 回调超时时间为 10 秒
