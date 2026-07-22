# 新增配置文件采集

Status: cancelled

> Migrated from `spec/solution_plan/CMDB/20260412.新增配置文件采集.md` as historical change evidence.

日期：2026-04-17

## 方案概览

本方案基于 PRD 与 Requirement，为 CMDB 新增"配置文件采集"任务类型，支持对主机上的操作系统层文本配置文件进行周期采集、差异版本沉淀与实例详情查看。

总体策略：

- 复用现有采集框架：配置文件采集作为新的 `task_type` 接入现有 `CollectModels` 体系，`driver_type` 固定为 `JOB`，通过 `JobCollect` 分发链路执行，复用任务创建、周期调度、执行状态管理等已有能力，不新增独立服务。
- 配置文件专属参数存入 `params` JSONField：与现有各类采集任务的扩展模式保持一致，不新增数据库列，无需 schema 迁移。
- 内容与元数据分离：配置文件版本正文通过 `MinioBackend` SDK 直接上传到 MinIO，CMDB 数据库仅存储版本元数据（路径、时间戳、状态、MinIO 对象 key），不影响实例详情基础属性展示性能。注意，设计一张表，存放模型ID实例ID和MinIO配置的映射，用于查询此实例的配置文件合集，及一个实例可以有多个配置文件
- 增量版本策略：每次采集与上一版本对比，内容无差异时不生成新版本，有差异时生成新版本，版本号为采集时间戳。
- 保持轻量：不引入文件编辑、回写、目录扫描等超出需求范围的能力。

## 范围与约束

### In Scope

- 配置文件采集任务的创建、编辑、删除、手动执行、周期执行与结果查看。
- 操作系统层文本配置文件的周期采集（Linux 与 Windows）。
- 基于内容差异的版本生成与版本管理。
- 配置文件版本正文存储到 MinIO，CMDB 仅管理元数据。
- 主机实例详情新增"配置文件"专用 Tab。
- 配置文件版本列表、版本内容查看与两版本文本差异对比。
- 文件大小限制说明与超限提示。
- 非文本文件识别与拒绝。

### Out of Scope

- 二进制文件采集与解析。
- 目录级批量采集、通配符扫描、自动发现整机全部配置文件。
- 配置文件在线编辑、回写主机、版本回滚。
- 跨实例的配置文件聚合分析与统一对比。
- 非主机场景下的专用展示入口建设。

## 已确认决策

- 配置文件采集作为 `CollectModels` 的新 `task_type`（`CollectPluginTypes` 新增 `CONFIG_FILE = "config_file"`），`driver_type` 固定为 `JOB`，复用现有任务管理流程。
- 配置文件专属字段（路径、文件名、大小上限）存入现有 `params` JSONField，与其他采集类型使用 `params` 存放额外参数的模式一致，不新增数据库列。
- 采集执行走 `JobCollect` 分支，在 `JobCollect.main()` 的 `task_type` 分发中新增 `CONFIG_FILE → ConfigFileCollect` 入口。
- MinIO 操作使用 `MinioBackend` SDK 直接调用 `storage.save()` / `storage.open()` / `storage.delete()` 上传下载纯文本内容（参考 `server/apps/mlops/tasks/base.py` 中的实现模式），不使用 `S3JSONField`。
- 一个配置文件采集任务对应一个目标主机实例 + 一个配置文件路径。用户如需对同一主机采集多个配置文件，需创建多个任务。
- 新增 `ConfigFileVersion` 数据模型，存储版本元数据；文件内容以文本格式直接存入 MinIO。
- 单文件采集大小上限建议 **1 MB**（需人工确认），超限时不生成版本并明确提示。
- 默认采集频率 10 分钟。
- 版本号使用 ISO 8601 格式的采集时间戳（如 `2026-04-17T10:30:00`）。
- 文本差异对比在后端生成 unified diff 格式返回，前端渲染展示。
- 前端实例详情页配置文件 Tab 路由为 `web/src/app/cmdb/(pages)/assetData/detail/configFiles/`，遵循现有 App Router 结构。

## 数据与架构落点

### 1）采集任务层（CollectModels 扩展）

在现有 `CollectModels` 基础上扩展，**不新增数据库列**：

- `CollectPluginTypes` 新增枚举值 `CONFIG_FILE = "config_file"`。
- `driver_type` 固定为 `CollectDriverTypes.JOB`。
- 配置文件专属参数通过 `params` JSONField 存储（与现有其他采集类型使用 `params` 存放额外参数的模式一致）：

```json
{
  "config_file_path": "/etc/nginx/nginx.conf",
  "config_file_name": "nginx.conf",
  "file_size_limit": 1048576
}
```

| params 内 key | 说明 |
|---------------|------|
| `config_file_path` | 配置文件绝对路径（必填） |
| `config_file_name` | 配置文件名称（展示用，可修改） |
| `file_size_limit` | 单文件大小上限（字节），默认 1048576（1MB） |

- 目标主机实例通过现有 `instances` JSONField 关联，取 `instances[0]` 获取 `instance_id` / `model_id` / `inst_name`。

路径校验规则（在序列化器中按 `task_type=CONFIG_FILE` 条件校验 `params` 内容）：
- Linux 绝对路径：以 `/` 开头。
- Windows 绝对路径：以盘符开头（如 `C:\`、`D:\`）。
- 路径不可为空、不可包含通配符（`*`、`?`）。
- 自动提取文件名填充 `config_file_name`：取路径最后一个 `/` 或 `\` 之后的部分。

### 2）版本元数据模型（新增 ConfigFileVersion）

```
ConfigFileVersion
├── id: AutoField (主键)
├── collect_task_id: ForeignKey → CollectModels (采集任务)
├── instance_id: CharField (主机实例 ID)
├── model_id: CharField (模型 ID)
├── version: CharField (版本号，采集时间戳 ISO 8601)
├── file_path: CharField (采集时的文件绝对路径，冗余存储)
├── file_name: CharField (配置文件名称，冗余存储)
├── content_hash: CharField (文件内容 SHA256 哈希，用于差异判断)
├── content_key: CharField (MinIO 对象 key，用于定位版本内容)
├── file_size: PositiveIntegerField (文件大小，字节)
├── status: CharField (采集结果状态：SUCCESS / FILE_NOT_FOUND / PERMISSION_DENIED / FILE_TOO_LARGE / NOT_TEXT / ERROR)
├── error_message: TextField (失败原因描述，可为空)
├── created_at: DateTimeField (记录创建时间)
└── Meta: index_together = [(instance_id, file_path), (collect_task_id,)]
```

说明：
- `content_hash` 用于快速判断内容是否变化，避免每次都从 MinIO 读取上一版本进行比对。
- `content_key` 仅在 `status=SUCCESS` 且内容有变化时生成。
- 采集失败时也生成记录（`content_key` 为空），用于展示采集历史与失败原因。

### 3）MinIO 存储层

使用 `MinioBackend` SDK 直接操作（参考 `server/apps/mlops/tasks/base.py` 中的实现模式）：

```python
from django_minio_backend import MinioBackend
from django.core.files.base import ContentFile

storage = MinioBackend(bucket_name="cmdb-config-file")

# 上传
saved_path = storage.save(object_key, ContentFile(content.encode("utf-8")))

# 下载
with storage.open(saved_path) as f:
  content = f.read().decode("utf-8")

# 删除
storage.delete(saved_path)
```

- Bucket：`cmdb-config-file`（新建，需注册到 `config/components/minio.py` 的 `MINIO_PRIVATE_BUCKETS` 中）。
- 对象路径格式：`{model_id}/{instance_id}/{file_path_hash}/{timestamp}.txt`
  - `file_path_hash`：文件绝对路径的 MD5 前 12 位，避免路径中特殊字符影响对象 key。
  - `timestamp`：采集时间戳，如 `20260417T103000`。
- 存储格式：纯文本内容直接存储，读取时按 UTF-8 返回。

### 4）采集执行层

配置文件采集接入现有 `JobCollect` 分发链路：

```
┌──────────────────────────────────────────────────────────────┐
│                   配置文件采集执行流程                          │
└──────────────────────────────────────────────────────────────┘

① CollectModelViewSet → exec_task / Celery Beat 触发
   ↓
② sync_collect_task(task_id)
   → instance.is_job == True (driver_type=JOB)
   → JobCollect(task=instance).main()
   ↓
③ JobCollect.main() 按 task_type 分发：
   ├─ HOST        → HostCollect
   ├─ DB          → DBCollect
   ├─ MIDDLEWARE  → MiddlewareCollect
   └─ CONFIG_FILE → ConfigFileCollect  ← 新增入口
   ↓
④ ConfigFileCollect 通过已有 Job 执行通道（SSH）在目标主机执行采集脚本：
   ├─ 从 task.params 获取 config_file_path / file_size_limit
   ├─ 从 task.instances[0] 获取目标主机 instance_id
   ├─ 检查文件是否存在
   ├─ 检查文件大小是否超限
   ├─ 检查文件是否为文本（file 命令或读取头部字节判断）
   └─ 读取文件内容并返回
   ↓
⑤ 采集结果回到 Celery Worker：
   ├─ 失败场景 → 生成 ConfigFileVersion（status=错误类型，无 content_key）
   └─ 成功场景 →
       ├─ 计算 content_hash (SHA256)
       ├─ 查询该文件最近一个 SUCCESS 版本的 content_hash
       ├─ 哈希一致 → 不生成新版本，仅更新任务执行状态
       └─ 哈希不一致 →
           ├─ 通过 MinioBackend.save() 上传文本内容 → 获取 content_key
           └─ 生成 ConfigFileVersion（status=SUCCESS）
   ↓
⑥ 更新 CollectModels 执行状态（exec_status / exec_time）
```

采集脚本设计（运行在目标主机上）：
- Linux：`bash` 脚本，使用 `file` 命令判断文本类型、`stat` 获取大小、`cat` 读取内容。
- Windows：`PowerShell` 脚本，使用 `Get-Item` 获取大小、文本编码检测、`Get-Content` 读取内容。
- 脚本输出 JSON 格式结果：`{ "status": "success|error", "content": "...", "size": 1234, "error": "..." }`

### 5）API 层

新增以下 API（挂载在现有 CMDB URL 体系下，路由注册在 `server/apps/cmdb/urls.py` 的 `router` 中）：

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/collect/` | POST | 创建采集任务（task_type=config_file 时, params 中携带配置文件专属字段） |
| `/api/config_file_versions/` | GET | 按实例 + 文件路径查询版本列表 |
| `/api/config_file_versions/{id}/content/` | GET | 获取指定版本的文件内容（通过 MinioBackend.open() 从 MinIO 读取文本） |
| `/api/config_file_versions/diff/` | GET | 两版本文本差异对比（参数：version_id_1, version_id_2） |
| `/api/config_files/` | GET | 按实例查询配置文件列表（去重聚合） |

说明：
- 创建/编辑采集任务复用现有 `CollectModelViewSet`，序列化器按 `task_type` 条件对 `params` 内容做校验（路径格式、文件名自动填充等）。
- 版本内容接口通过 `MinioBackend` 实时读取并返回，不缓存到数据库。
- diff 接口在后端使用 Python `difflib.unified_diff` 生成差异文本返回前端。

### 6）前端交互层

**采集任务创建/编辑页面**

- 当用户选择任务类型为"配置文件采集"时，表单增加：
  - "配置文件绝对路径"（必填，输入框），附路径格式说明。
  - "配置文件名称"（必填，输入框），路径填写后自动填充，允许修改。
  - "文件大小限制说明"（只读提示），如"当前支持的单文件上限为 1 MB"。
- 默认采集频率 10 分钟。
- 路径校验不通过时，阻止保存并提示"请输入有效的绝对路径"。

**主机实例详情页**

前端路由位于 `web/src/app/cmdb/(pages)/assetData/detail/configFiles/`，遵循现有 App Router Tab 结构（与 `baseInfo/`、`changeRecords/`、`relationships/` 同级）。

- 新增"配置文件"Tab：
  - 列表展示当前实例下已纳入采集的配置文件：文件名称、文件路径、最新版本时间、最新采集状态。
  - 点击文件名称 → 进入版本列表页面。
  - 空状态：当无配置文件采集记录时，展示"暂无配置文件采集记录"提示。
- 版本列表页面：
  - 展示版本号（时间戳）、采集时间、采集结果状态。
  - 点击版本 → 查看该版本完整文本内容。
  - 勾选两个版本 → 点击"对比"按钮 → 展示 unified diff 差异视图。
- 版本内容查看：
  - 以代码块/等宽字体渲染纯文本内容。
  - 支持全文复制。

## 分阶段计划

### 阶段一：后端模型与采集执行能力

**里程碑目标**

- 完成数据模型扩展、采集执行链路与 MinIO 存储链路。

**交付内容**

- `CollectPluginTypes` 新增 `CONFIG_FILE` 枚举值。
- 序列化器扩展：`task_type=config_file` 时对 `params` 中的 `config_file_path` / `config_file_name` / `file_size_limit` 做校验。
- 新增 `ConfigFileVersion` 数据模型与数据库迁移。
- `config/components/minio.py` 的 `MINIO_PRIVATE_BUCKETS` 注册新 bucket `cmdb-config-file`。
- 实现 `ConfigFileCollect` 采集类，接入 `JobCollect.main()` 的 `task_type` 分发逻辑。
- 实现 Linux / Windows 采集脚本：文件存在检测、大小检测、文本类型检测、内容读取。
- 实现内容哈希比对与增量版本生成逻辑。
- 通过 `MinioBackend` SDK 实现版本内容的上传与读取。
- 实现采集失败场景的状态记录与错误信息填充。
- 路径校验工具函数（Linux / Windows 绝对路径识别、文件名提取）。

**里程碑结果**

- 可通过后端接口创建配置文件采集任务并执行。
- 采集成功时，版本内容存入 MinIO，元数据存入 `ConfigFileVersion`。
- 采集失败时，错误信息可查询。
- 内容无变化时不生成新版本。

### 阶段二：版本查询与差异对比 API

**里程碑目标**

- 完成所有版本查看与差异对比相关 API。

**交付内容**

- 配置文件列表接口（按实例聚合）。
- 版本列表接口（按实例 + 文件路径查询，分页）。
- 版本内容接口（通过 `MinioBackend.open()` 读取文本返回）。
- 两版本 diff 接口（unified diff 格式）。

**里程碑结果**

- 所有前端所需数据接口就绪，可独立测试。

### 阶段三：前端交互落地

**里程碑目标**

- 完成采集任务配置页面扩展与实例详情配置文件 Tab 全部交互。

**交付内容**

- 采集任务创建/编辑页面：`task_type=config_file` 时动态展示配置文件专属字段与校验。
- 主机实例详情新增"配置文件"Tab（`detail/configFiles/page.tsx`）。
- 配置文件列表页面。
- 版本列表页面。
- 版本内容查看页面。
- 两版本文本差异对比页面。
- 空状态、加载状态、错误状态处理。

**里程碑结果**

- 用户可端到端完成配置文件采集任务创建、执行、版本查看与差异对比。

### 阶段四：联调测试与上线准备

**里程碑目标**

- 前后端联调、回归测试与上线准备。

**交付内容**

- 前后端全链路联调。
- Linux 与 Windows 双场景采集脚本验证。
- 异常场景覆盖测试（路径不存在、权限不足、文件超限、非文本、文件为空等）。
- 性能验证：大量版本列表查询、MinIO 读写稳定性。
- 回滚预案确认。

**里程碑结果**

- 功能通过验收标准，具备上线条件。

## 阶段验收清单

- 用户可在 CMDB 中创建配置文件采集任务，交互方式与主机采集任务保持一致。
- 任务录入包含"配置文件绝对路径"和"配置文件名称"两个必填字段。
- 填写路径后，系统自动填充文件名，用户可手动修改。
- 系统正确识别 Linux 与 Windows 绝对路径，并正确提取默认文件名。
- 路径非法或非绝对路径时，系统阻止保存并提示。
- 仅采集文本文件；非文本内容时明确提示且不生成有效采集结果。
- 用户可获知单文件采集大小上限；超限时明确提示且不生成新版本。
- 版本正文不写入 CMDB 实例属性，统一存于 MinIO。
- 新建任务默认采集频率 10 分钟。
- 采集后与上一版本对比：无差异不生成新版本，有差异生成新版本。
- 新版本版本号为时间戳，在版本列表中可稳定展示。
- 主机实例详情有"配置文件"专用 Tab，可查看多个配置文件。
- 点击配置文件可查看版本列表，点击版本可查看内容。
- 可选择两个版本进行文本差异对比。
- 无配置文件采集记录时显示空状态，不影响实例详情其他信息。

## 风险与应对

- 风险：采集脚本在目标主机执行时，文件读取权限不足或路径不可达。
  应对：脚本内置权限与路径预检查，失败时返回明确错误码与描述，前端展示可识别的失败原因。

- 风险：大文件传输占用网络带宽与采集通道资源。
  应对：通过文件大小上限（默认 1 MB）硬控制，超限直接拒绝，不消耗传输资源。

- 风险：MinIO 不可用导致版本内容写入/读取失败。
  应对：采集结果写入 MinIO 失败时，版本记录状态标记为 ERROR 并记录错误信息，不阻塞任务状态流转；前端访问版本内容时做异常兜底提示。

- 风险：高频采集（10 分钟）叠加大量主机实例，版本数据量膨胀。
  应对：本期通过内容哈希对比避免无差异版本产生；后续可按需增加版本保留策略（如仅保留最近 N 个版本或 M 天内版本）。

- 风险：Windows 主机 PowerShell 执行策略限制导致采集脚本无法运行。
  应对：采集脚本使用内联命令方式执行，避免依赖脚本文件执行策略；测试环节覆盖 Windows 场景。

## 依赖与协同

- 产品：确认单文件采集大小上限（建议 1 MB）、版本保留策略是否本期支持、Tab 命名文案。
- 后端：负责 `CollectPluginTypes` 扩展、`params` 校验、`ConfigFileCollect` 采集类、`ConfigFileVersion` 模型、MinIO 存储、版本管理与 API 开发。
- 前端：负责采集任务配置页面扩展、实例详情 `detail/configFiles/` Tab、版本列表/内容/差异对比页面。
- 节点管理（Node Mgmt）：确认现有 Job 执行通道可支持配置文件采集脚本的下发与结果回传。
- 测试：覆盖 Linux/Windows 采集、异常场景、版本管理、前后端联调全链路回归。

## 需人工判断/确认

- 单文件采集大小上限：方案建议 1 MB，需产品确认是否满足业务场景。
- 版本保留策略：本期仅做增量版本生成，是否需要配套版本清理策略（如保留最近 100 个版本），需人工确认。
- 一个任务对应一个文件 vs 一个任务支持多个文件：方案采用一任务一文件的简单模型，如需一任务多文件需调整设计，需产品确认。

## 遗漏项检查

- 范围边界：已明确 In Scope 与 Out of Scope，与 Requirement 一致。
- 依赖方：已覆盖产品、后端、前端、节点管理、测试。
- 验收口径：阶段验收清单对应 Requirement 中所有验收标准，可执行、可回归。
- 风险与回滚：已明确主要风险、缓解方式；上线回滚可通过数据库迁移回退 + MinIO 数据保留实现。

## 待确认项（TODO）

- TODO：确认单文件采集大小上限具体值（方案建议 1 MB），确认位置：产品侧。
- TODO：确认是否本期需要版本保留/清理策略，确认位置：产品侧。
- TODO：确认一个采集任务对应一个文件的交互模型是否满足业务需要，确认位置：产品侧。
- TODO：确认现有 Job 执行通道对 Windows PowerShell 脚本的支持程度，确认位置：`server/apps/cmdb/collection/collect_tasks/` 与 Node Mgmt。
- TODO：确认 MinIO bucket `cmdb-config-file` 命名与权限配置策略，确认位置：运维/基础设施侧。
- TODO：确认前端配置文件 Tab 的命名文案（"配置文件" or 其他），确认位置：产品侧。
