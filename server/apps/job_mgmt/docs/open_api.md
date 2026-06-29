# 作业管理开放接口文档

> 供第三方 App（如补丁管理）调用作业管理能力

## 概览

| 接口 | 通道 | 鉴权 | 说明 |
|------|------|------|------|
| 查询节点列表 | NATS `bklite.node_list` | 无 | 同步，分页返回节点 |
| 查询目标列表 | NATS `bklite.job_target_list` | 无 | 同步，分页返回目标 |
| 脚本执行 | NATS `bklite.job_script_execute` | 无 | 异步，返回 task_id |
| 文件上传 | REST `POST /api/v1/job_mgmt/api/open/upload_file` | Api-Authorization | 同步，返回 file_id + file_key |
| 文件删除 | REST `DELETE /api/v1/job_mgmt/api/open/delete_file` | Api-Authorization | 同步，删除文件 |
| 文件分发 | NATS `bklite.job_file_distribute` | 无 | 异步，返回 task_id |
| 批量查询状态 | NATS `bklite.job_status_batch_query` | 无 | 同步 |
| 查询作业详情 | NATS `bklite.job_detail_query` | 无 | 同步 |

## 鉴权说明

### NATS 接口
无需鉴权，信任内网 NATS 通道。NATS subject 前缀由 `NATS_NAMESPACE` 配置决定（默认 `bklite`）。

### REST 文件上传接口
使用 `UserAPISecret` 的 `api_secret` 作为 token：

```
Api-Authorization: <api_secret>
```

`api_secret` 可在系统管理中创建，绑定特定用户和团队。

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
       │  3. NATS: bklite.job_file_distribute                 │
       │     { file_keys: [file_key], ... }                   │
       │─────────────────────────────────────────────────────▶│
       │◀─────────────────── { task_id } ─────────────────────│
       │                                                      │
       │          ... 等待执行 ...                             │
       │                                                      │
       │  4. HTTP POST callback_url (server → 第三方)          │
       │◀─────────────── { task_id, status } ─────────────────│
       │                                                      │
       │  5. NATS: bklite.job_detail_query (可选，获取详情)     │
       │─────────────────────────────────────────────────────▶│
       │◀─────────── { execution_results, ... } ──────────────│
```

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

> ⚠️ **安全校验**：`file_id` 和 `file_key` 必须同时匹配才能删除，防止猜测 ID 或 key 进行越权删除。

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

**NATS Subject**: `bklite.job_file_distribute`

**Request:**
```json
{
  "name": "分发补丁包",
  "file_keys": ["job-files/2026/04/30/abc123.rpm"],
  "target_source": "node_mgmt",
  "target_list": [
    {"node_id": "xxx", "name": "web-01", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": "region-1"}
  ],
  "target_path": "/tmp/patches/",
  "overwrite_strategy": "overwrite",
  "timeout": 600,
  "team": [1],
  "callback_url": "http://patch-mgmt:8080/api/callback/task_done"
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
| team | array | 是 | 团队 ID 列表 |
| callback_url | string | 否 | 任务完成回调地址 |

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

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | integer | 是 | 作业执行 ID |
| team | array | 是 | 调用方团队 ID 列表，必须与作业执行记录归属团队有交集 |

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
