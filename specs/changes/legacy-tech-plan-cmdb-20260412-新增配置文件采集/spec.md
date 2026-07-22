# 新增配置文件采集 - Tech Plan

Status: cancelled

> Migrated from `spec/tech_plan/CMDB/20260412.新增配置文件采集.md` as historical change evidence.

日期：2026-04-17

## 技术目标与非目标

### 技术目标

- 配置文件采集复用现有 `push_butch_node_params → 节点管理 → Stargazer → 采集` 链路，不新增独立调度通道。
- `CollectPluginTypes` 新增 `CONFIG_FILE = "config_file"`，`driver_type` 固定为 `JOB`。
- 配置文件专属参数存入现有 `CollectModels.params` JSONField，不新增数据库列。
- 配置文件采集任务目标范围复用现有 `CollectModels.instances` / `CollectModels.ip_range`，支持“选择主机”与“填写 IP 段”两种录入方式。
- 修改 `should_sync_node_params()` 移除 CONFIG_FILE 排除条件，新增 `ConfigFileNodeParams` 将采集配置推送到节点管理。
- Stargazer 侧新增 `ConfigFileInfo` 插件（继承 `SSHPlugin`），执行远程脚本采集目标文件内容。
- Stargazer 采集结果**不推送 VictoriaMetrics**，而是通过 NATS publish 回传到 CMDB 的 `receive_config_file_result` handler；CMDB 同时提供一个等价的 HTTP 补偿接口用于手工回放/重试写库。
- CMDB 侧 NATS handler 接收结果 → SHA256 哈希比对 → MinIO 上传（纯文本） → `ConfigFileVersion` 版本记录写入。
- `ConfigFileCollect` 不再直接执行 SSH，改为根据任务目标范围汇总当前回调状态，供 `sync_collect_task` 更新任务摘要。
- 新增 `ConfigFileVersionViewSet` 提供版本列表、版本内容、文件列表、diff 接口。
- 前端配置文件任务表单复用主机采集的目标范围切换交互，支持“填写 IP 段 / 选择主机”双模式；实例详情在 `web/src/app/cmdb/(pages)/assetData/detail/configFiles/` 新增配置文件 Tab。

### 非目标

- 不改造现有 `BaseCollect` / `MetricsCannula` 采集插件体系。
- 不新增独立服务或独立 Celery Worker。
- 不改变 Stargazer 现有 `collect_plugin_task → publish_metrics_to_nats` 的通用采集推送流程，仅为 CONFIG_FILE 做路由分支。
- 不支持二进制文件、目录扫描、通配符、配置文件编辑/回写。
- 不改造权限系统，复用现有 `InstanceTaskPermission`。

---

## 1) 文件与目录结构 (File Tree)

```text
server/
├─ apps/cmdb/
│  ├─ constants/
│  │  └─ constants.py                                    (M) CollectPluginTypes 新增 CONFIG_FILE（已完成）
│  ├─ models/
│  │  ├─ __init__.py                                     (M) 新增 config_file_version 导入
│  │  └─ config_file_version.py                          (A) ConfigFileVersion 模型
│  ├─ collection/
│  │  └─ collect_tasks/
│  │     ├─ job_collect.py                               (已有 CONFIG_FILE 入口，无需改)
│  │     └─ config_file_collect.py                       (M) 重写为查询状态模式（不再直接 SSH）
│  ├─ services/
│  │  ├─ collect_service.py                              (M) should_sync_node_params 移除 CONFIG_FILE 排除
│  │  └─ config_file_service.py                          (A) MinIO 读写、diff、process_collect_result
│  ├─ node_configs/
│  │  └─ ssh/
│  │     └─ config_file.py                               (A) ConfigFileNodeParams
│  ├─ nats/
│  │  └─ nats.py                                         (M) 新增 receive_config_file_result handler
│  ├─ serializers/
│  │  ├─ collect_serializer.py                           (M) CONFIG_FILE 时校验 params
│  │  └─ config_file_serializer.py                       (A) ConfigFileVersion 序列化器
│  ├─ views/
│  │  └─ config_file.py                                  (A) ConfigFileVersionViewSet（含 receive_result POST 补偿接口）
│  ├─ urls.py                                            (M) 注册 config_file_versions 路由
│  └─ utils/
│     └─ config_file_path.py                             (A) 路径校验与文件名提取
│
├─ config/components/
│  └─ minio.py                                           (M) MINIO_PRIVATE_BUCKETS 新增 cmdb-config-file

agents/stargazer/
├─ plugins/inputs/config_file/
│  ├─ config_file_info.py                                (A) 配置文件采集插件（继承 SSHPlugin）
│  └─ plugin.yml                                         (A) 采集配置声明（executor_type: job）
└─ tasks/handlers/
   └─ plugin_handler.py                                  (M) CONFIG_FILE 路由分支：不推 VM，NATS 回传 CMDB

web/
└─ src/app/cmdb/
   ├─ api/
   │  └─ configFile.ts                                   (A) 配置文件 API 调用
   ├─ types/
   │  └─ configFile.ts                                   (A) 类型定义
   └─ (pages)/assetData/detail/
      └─ configFiles/
         └─ page.tsx                                     (A) 配置文件 Tab 页面
```

`(A)` = 新增，`(M)` = 修改。

---

## 2) 核心数据结构 / Schema 定义

### 2.1 CollectPluginTypes（已完成）

```python
# server/apps/cmdb/constants/constants.py
# 已新增：
CONFIG_FILE = "config_file"
# CHOICE 已包含 (CONFIG_FILE, "配置文件采集")
```

### 2.2 params 内配置文件专属字段约定

```python
# 当 task_type == "config_file" 时，CollectModels.params 结构：
{
    "config_file_path": "/etc/nginx/nginx.conf",   # 必填，绝对路径
    "config_file_name": "nginx.conf",               # 必填，展示名称
    "file_size_limit": 1048576                       # 可选，默认 1MB
}
```

任务目标范围沿用 `CollectModels` 现有字段，不写入 `params`：

```python
# 方式一：选择主机
instances = [
    {"_id": 1, "model_id": "host", "inst_name": "node-a", "ip_addr": "10.0.0.1"},
    {"_id": 2, "model_id": "host", "inst_name": "node-b", "ip_addr": "10.0.0.2"},
]
ip_range = ""

# 方式二：填写 IP 段
instances = []
ip_range = "10.0.0.1-10.0.0.10"
```

约束：

- `instances` 与 `ip_range` 二选一，不允许同时生效。
- 当 `ip_range` 非空时，Stargazer HTTP 入口按 IP 段拆分为多个单 host 任务执行。
- 当 `instances` 非空时，节点管理通过 `hosts=ip1,ip2,...` 方式逐台主机触发采集。

### 2.3 ConfigFileVersion Django Model

```python
# server/apps/cmdb/models/config_file_version.py

from django.core.files.base import ContentFile
from django.db import models
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.cmdb.models.collect_model import CollectModels

CONFIG_FILE_BUCKET = "cmdb-config-file"


class ConfigFileVersionStatus:
    """配置文件版本采集状态枚举"""
    SUCCESS = "success"
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    FILE_TOO_LARGE = "file_too_large"
    NOT_TEXT = "not_text"
    ERROR = "error"

    CHOICES = (
        (SUCCESS, "采集成功"),
        (FILE_NOT_FOUND, "文件不存在"),
        (PERMISSION_DENIED, "权限不足"),
        (FILE_TOO_LARGE, "文件超限"),
        (NOT_TEXT, "非文本文件"),
        (ERROR, "采集异常"),
    )


class ConfigFileVersion(models.Model):
    """
    配置文件版本元数据。
    每次采集回传时生成一条记录（成功或失败），成功且内容有变化时才写入 MinIO。
    content_hash 用于增量判断，避免每次从 MinIO 读取上一版本做全文对比。
    content 字段使用 FileField + MinioBackend，参考 TimeSeriesPredictTrainData.train_data 模式。
    """
    collect_task = models.ForeignKey(
        CollectModels, on_delete=models.CASCADE,
        related_name="config_file_versions",
        help_text="关联的采集任务"
    )
    instance_id = models.CharField(max_length=128, help_text="主机实例 ID")
    model_id = models.CharField(max_length=64, help_text="模型 ID")
    version = models.CharField(max_length=32, help_text="版本号（采集时间戳 ISO 8601）")
    file_path = models.CharField(max_length=512, help_text="采集时的文件绝对路径")
    file_name = models.CharField(max_length=256, help_text="配置文件名称")
    content_hash = models.CharField(
        max_length=64, blank=True, default="",
        help_text="文件内容 SHA256 哈希"
    )
    content = models.FileField(
        verbose_name="配置文件内容",
        storage=MinioBackend(bucket_name=CONFIG_FILE_BUCKET),
        upload_to=iso_date_prefix,
        blank=True, null=True,
        help_text="存储在 MinIO 中的配置文件文本内容",
    )
    file_size = models.PositiveIntegerField(default=0, help_text="文件大小（字节）")
    status = models.CharField(
        max_length=32, choices=ConfigFileVersionStatus.CHOICES,
        help_text="采集结果状态"
    )
    error_message = models.TextField(
        blank=True, default="", help_text="失败原因描述"
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="记录创建时间")

    class Meta:
        verbose_name = "配置文件版本"
        verbose_name_plural = "配置文件版本"
        ordering = ["-created_at"]
        index_together = [
            ("instance_id", "file_path"),
            ("collect_task_id",),
        ]

    def save_content(self, text: str) -> None:
        """
        将文本内容直接保存到 MinIO。
        通过 FileField.save() 自动处理 MinIO 上传和路径生成。
        """
        file_name = f"{self.instance_id}_{self.version}.txt"
        self.content.save(file_name, ContentFile(text.encode("utf-8")), save=False)

    def read_content(self) -> str:
        """
        从 MinIO 读取配置文件内容。
        Returns: 文本内容。若 content 为空返回空字符串。
        """
        if not self.content:
            return ""
        with self.content.open("rb") as f:
            return f.read().decode("utf-8")
```

### 2.4 序列化器

```python
# server/apps/cmdb/serializers/config_file_serializer.py

from rest_framework import serializers
from apps.cmdb.models.config_file_version import ConfigFileVersion


class ConfigFileVersionSerializer(serializers.ModelSerializer):
    """版本列表序列化器"""
    class Meta:
        model = ConfigFileVersion
        fields = [
            "id", "collect_task_id", "instance_id", "model_id",
            "version", "file_path", "file_name", "content_hash",
            "content", "file_size", "status", "error_message", "created_at",
        ]


class ConfigFileListSerializer(serializers.Serializer):
    """配置文件列表（按实例聚合去重）"""
    file_path = serializers.CharField()
    file_name = serializers.CharField()
    collect_task_id = serializers.IntegerField()
    latest_version = serializers.CharField()
    latest_status = serializers.CharField()
    latest_created_at = serializers.DateTimeField()
```

### 2.5 路径校验工具

```python
# server/apps/cmdb/utils/config_file_path.py

import re

_LINUX_ABS_RE = re.compile(r"^/[^\0*?]+$")
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:\\[^\0*?]*$")


def validate_absolute_path(path: str) -> bool:
    """
    校验路径是否为有效的绝对路径（Linux 或 Windows）。
    拒绝空串、通配符（* ?）、非绝对路径。
    """
    if not path or not path.strip():
        return False
    path = path.strip()
    return bool(_LINUX_ABS_RE.match(path) or _WIN_ABS_RE.match(path))


def extract_file_name(path: str) -> str:
    """
    从绝对路径中提取文件名。
    兼容 Linux (/) 和 Windows (\\) 路径分隔符。
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name if name else path
```

### 2.6 前端类型定义

```typescript
// web/src/app/cmdb/types/configFile.ts

export interface ConfigFileItem {
  file_path: string;
  file_name: string;
  collect_task_id: number;
  latest_version: string;
  latest_status: string;
  latest_created_at: string;
}

export interface ConfigFileVersion {
  id: number;
  collect_task_id: number;
  instance_id: string;
  model_id: string;
  version: string;
  file_path: string;
  file_name: string;
  content_hash: string;
  file_size: number;
  status: string;
  error_message: string;
  created_at: string;
}

export interface ConfigFileDiffResponse {
  version_1: string;
  version_2: string;
  diff_text: string;
}
```

---

## 3) 核心函数 / 接口签名

### 3.1 采集配置推送 — should_sync_node_params 修改

```python
# server/apps/cmdb/services/collect_service.py
# 原代码：
#   return (not instance.is_k8s) and instance.task_type != CollectPluginTypes.CONFIG_FILE
# 修改为：

@staticmethod
def should_sync_node_params(instance):
    """移除 CONFIG_FILE 排除条件，允许配置文件采集推送到节点管理"""
    return not instance.is_k8s
```

### 3.2 ConfigFileNodeParams — 推送节点配置

```python
# server/apps/cmdb/node_configs/ssh/config_file.py

from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class ConfigFileNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    """
    配置文件采集节点参数。
    继承 SSHNodeParamsMixin 复用 SSH 凭据、接入点等逻辑。
    在 set_credential 中注入配置文件专属参数与 host -> instance 映射。
    自动注册到 BaseNodeParams._registry["config_file"]。
    """
    supported_model_id = "config_file"
    plugin_name = "config_file_info"

    def set_credential(self):
        """
        在基础 SSH 参数上追加配置文件专属参数。
        若任务通过“选择主机”模式创建，则额外携带 host_instance_map，
        供 Stargazer 在多 host 拆分回调时反查对应实例。
        """
        params = super().set_credential()
        params = self.instance.params or {}
        credential_data.update({
            "config_file_path": params.get("config_file_path", ""),
            "config_file_name": params.get("config_file_name", ""),
            "file_size_limit": params.get("file_size_limit", 1048576),
            "callback_subject": "receive_config_file_result",
            "host_instance_map": "{\"10.0.0.1\": {\"instance_id\": \"1\", \"model_id\": \"host\"}}",
        })
        return credential_data
```

### 3.3 Stargazer — ConfigFileInfo 插件

```python
# agents/stargazer/plugins/inputs/config_file/config_file_info.py

from plugins.script_executor import SSHPlugin


class ConfigFileInfo(SSHPlugin):
    """
    配置文件采集插件。
    继承 SSHPlugin 复用 NATS → nats-executor SSH 执行链路。
    重写 list_all_resources：
    - 根据 os_type 构建 bash/powershell 采集脚本
    - 执行远程脚本获取文件内容
    - 返回结果包含 content_base64、content_hash、size、status
    """

    async def list_all_resources(self, need_raw=False) -> dict:
        """
        执行配置文件采集。
        1. 从 params 提取 config_file_path、file_size_limit
        2. 构建采集脚本（bash 或 powershell）
        3. 通过 nats_request SSH 执行脚本
        4. 解析 JSON 输出
        Returns:
            dict: {
                "success": bool,
                "result": {
                    "collect_task_id": int,
                    "instance_id": str,
                    "model_id": str,
                    "file_path": str,
                    "file_name": str,
                    "version": str,
                    "status": "success|file_not_found|permission_denied|file_too_large|not_text|error",
                    "size": int,
                    "error": str,
                    "content_base64": str,
                    "content_hash": str
                }
            }
        """
        ...

    def _build_bash_script(self, file_path: str, size_limit: int) -> str:
        """Linux bash 采集脚本（见 4.8 节）"""
        ...

    def _build_powershell_script(self, file_path: str, size_limit: int) -> str:
        """Windows PowerShell 采集脚本（见 4.9 节）"""
        ...
```

### 3.4 Stargazer — collect_plugin_task 路由分支

```python
# agents/stargazer/tasks/handlers/plugin_handler.py
# 在现有 collect_plugin_task 中新增 CONFIG_FILE 路由分支：

async def collect_plugin_task(ctx, params, task_id):
    # ... 原有逻辑 ...
    collect_service = CollectionService(params)
    metrics_data = await collect_service.collect()

    plugin_name = params.get("plugin_name")
    if plugin_name == "config_file_info":
        # 配置文件不推 VictoriaMetrics，通过 NATS 回传 CMDB
        callback_subject = params.get("callback_subject", "receive_config_file_result")
        await nats_publish(callback_subject, metrics_data)
    else:
        # 其他类型推送到 VictoriaMetrics（原有逻辑）
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)
```

### 3.5 CMDB NATS Handler — 接收采集结果

```python
# server/apps/cmdb/nats/nats.py
# 新增 handler，与现有 get_cmdb_module_data、search_instances 并列

@nats_client.register
def receive_config_file_result(data: dict) -> dict:
    """
    接收 Stargazer 回传的配置文件采集结果。
    data 结构（当前主口径，扁平结构）:
        {
            "collect_task_id": int,
            "instance_id": str,
            "model_id": str,
            "file_path": str,
            "file_name": str,
            "version": str,
            "status": "success|file_not_found|permission_denied|file_too_large|not_text|error",
            "size": int,
            "error": str,
            "content_base64": str,
            "content_hash": str
        }
    兼容口径：仍兼容旧版包装结构 `{task_id, config_file_path, collect_result: {...}}`，用于历史回放。
    """
    from apps.cmdb.services.config_file_service import ConfigFileService
    ConfigFileService.process_collect_result(data)
    return {"result": True}
```

### 3.6 ConfigFileService — 完整服务层

```python
# server/apps/cmdb/services/config_file_service.py

from apps.cmdb.models.config_file_version import ConfigFileVersion


class ConfigFileService:
    """
    配置文件版本管理服务。
    职责：NATS 回传结果处理、unified diff 生成、版本列表聚合查询。
    MinIO 上传/下载通过 ConfigFileVersion.save_content() / read_content() 完成，
    参考 TimeSeriesPredictTrainData 使用 FileField(storage=MinioBackend) 模式。
    """

    @staticmethod
    def process_collect_result(data: dict) -> None:
        """
        处理 Stargazer 回传的采集结果（由 NATS handler 或 HTTP receive_result 接口调用）。
        流程：
        1. 统一归一化扁平/旧包装 payload
        2. 错误结果 → 创建失败版本记录 → 收敛 CollectModels 任务状态
        3. 成功结果 → base64 解码 → SHA256 哈希比对
        4. 哈希一致 → 不生成新版本，但收敛任务状态为 SUCCESS
        5. 哈希不一致 → version.save_content() 上传 MinIO + 创建新版本 + 收敛任务状态
        """
        ...

    @staticmethod
    def generate_diff(content_1: str, content_2: str, label_1: str, label_2: str) -> str:
        """生成两段文本的 unified diff"""
        ...

    @staticmethod
    def get_file_list(instance_id: str) -> list[dict]:
        """按实例查询配置文件列表，每个 file_path 聚合取最新版本信息"""
        ...
```

### 3.7 ConfigFileCollect — 重写为查询状态模式

```python
# server/apps/cmdb/collection/collect_tasks/config_file_collect.py

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileVersion


class ConfigFileCollect:
    """
    配置文件采集执行类（查询模式）。
    不执行实际采集（采集由 Stargazer 通过节点管理链路异步完成）。
    仅查询 ConfigFileVersion 最新状态，构建 format_data 供 sync_collect_task 更新任务摘要。
    由 JobCollect.collect_config_file() 调用。
    """

    def __init__(self, task_id: int): ...

    def __call__(self) -> tuple[dict, dict]:
        """
        不直接执行采集，而是基于 collect_data.config_file.items 聚合当前回调状态。
        若任务仍有目标主机未回传，则返回 pending；
        若全部主机已回传，则按 success/error 聚合摘要。
        """
        ...
```

### 3.8 API 端点

```text
路由注册位置: server/apps/cmdb/urls.py

GET  /api/config_file_versions/                     → list()        按 instance_id + file_path 查版本列表
GET  /api/config_file_versions/{id}/content/        → content()     获取版本文件内容
GET  /api/config_file_versions/diff/                → diff()        两版本差异对比
GET  /api/config_file_versions/file_list/           → file_list()   按实例查配置文件列表
POST /api/config_file_versions/receive_result/      → receive_result() HTTP 补偿写库接口
```

### 3.9 ConfigFileVersionViewSet

```python
# server/apps/cmdb/views/config_file.py

from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin
from apps.cmdb.models.config_file_version import ConfigFileVersion
from apps.cmdb.serializers.config_file_serializer import ConfigFileVersionSerializer
from apps.cmdb.services.config_file_service import ConfigFileService


class ConfigFileVersionViewSet(ListModelMixin, GenericViewSet):
    """配置文件版本管理视图"""
    queryset = ConfigFileVersion.objects.all()
    serializer_class = ConfigFileVersionSerializer

    def list(self, request, *args, **kwargs) -> Response:
        """
        查询版本列表。
        必传 query_params: instance_id, file_path
        可选 query_params: status
        返回按 created_at 降序排列的版本记录列表（分页）。
        """
        ...

    @action(methods=["GET"], detail=True, url_path="content")
    def content(self, request, pk=None) -> Response:
        """
        获取指定版本的文件全文内容。
        通过 version.read_content() 从 MinIO 读取文本内容并返回。
        返回: {"content": "文件全文内容"}
        """
        ...

    @action(methods=["GET"], detail=False, url_path="diff")
    def diff(self, request) -> Response:
        """
        两个版本之间的文本差异对比。
        必传 query_params: version_id_1, version_id_2
        返回: {"version_1": "...", "version_2": "...", "diff_text": "unified diff"}
        """
        ...

    @action(methods=["GET"], detail=False, url_path="file_list")
    def file_list(self, request) -> Response:
        """
        按实例查询配置文件列表（去重聚合）。
        必传 query_params: instance_id
        返回: 每个 file_path 的最新版本信息列表。
        """
        ...

    @action(methods=["POST"], detail=False, url_path="receive_result")
    def receive_result(self, request) -> Response:
        """
        HTTP 补偿写库接口。
        接收与 NATS handler 相同的 payload，调用 ConfigFileService.process_collect_result。
        主要用于手工回放、调试和补偿，不替代 NATS 主链路。
        """
        ...
```

### 3.10 CollectModelSerializer 扩展

```python
# server/apps/cmdb/serializers/collect_serializer.py
# CollectModelSerializer 新增 validate 逻辑：

from apps.cmdb.utils.config_file_path import validate_absolute_path, extract_file_name

def validate(self, attrs):
    """当 task_type == config_file 时校验 params 中的配置文件专属字段"""
    if attrs.get("task_type") == CollectPluginTypes.CONFIG_FILE:
        params = attrs.get("params", {})
        path = params.get("config_file_path", "")
        if not validate_absolute_path(path):
            raise serializers.ValidationError({"params": "请输入有效的绝对路径"})
        if not params.get("config_file_name"):
            params["config_file_name"] = extract_file_name(path)
        if not params.get("file_size_limit"):
            params["file_size_limit"] = 1048576
        if not attrs.get("instances") and not attrs.get("ip_range"):
            raise serializers.ValidationError("请选择主机或填写IP范围")
        if attrs.get("instances"):
            attrs["ip_range"] = ""
        elif attrs.get("ip_range"):
            attrs["instances"] = []
        attrs["params"] = params
        attrs["driver_type"] = CollectDriverTypes.JOB
    return attrs
```

### 3.11 前端 API 调用

```typescript
// web/src/app/cmdb/api/configFile.ts

import useApiClient from '@/utils/request';

const API_PREFIX = '/api/v1/cmdb';

/** 获取实例下的配置文件列表 */
export const getConfigFileList = (instance_id: string) =>
  useApiClient().get(`${API_PREFIX}/config_file_versions/file_list/`, {
    params: { instance_id },
  });

/** 获取某配置文件的版本列表 */
export const getConfigFileVersions = (instance_id: string, file_path: string) =>
  useApiClient().get(`${API_PREFIX}/config_file_versions/`, {
    params: { instance_id, file_path },
  });

/** 获取指定版本的文件内容 */
export const getVersionContent = (versionId: number) =>
  useApiClient().get(`${API_PREFIX}/config_file_versions/${versionId}/content/`);

/** 获取两版本的 diff */
export const getVersionDiff = (version_id_1: number, version_id_2: number) =>
  useApiClient().get(`${API_PREFIX}/config_file_versions/diff/`, {
    params: { version_id_1, version_id_2 },
  });
```

---

## 4) 核心逻辑伪代码

### 4.1 采集配置推送链路（任务创建时）

```python
# 触发点: CollectModelService.create() / update()

def create(cls, request, view_self):
    # ... 创建 CollectModels 记录 ...

    if is_interval:
        CeleryUtils.create_or_update_periodic_task(...)

    # should_sync_node_params 已不再排除 CONFIG_FILE
    if cls.should_sync_node_params(instance):
        cls.push_butch_node_params(instance)
        # → NodeParamsFactory.get_node_params(instance)
        # → 若 instance.ip_range 非空，则 Stargazer HTTP 入口按 IP 段拆分单 host 任务
        # → 若 instance.instances 非空，则节点管理按 hosts=ip1,ip2,... 下发
        # → ConfigFileNodeParams(instance)  (因 supported_model_id == "config_file")
        # → push_params() 生成 Telegraf 配置，headers 含 config_file_path 等
        # → NodeMgmt.batch_add_node_child_config(node_params)
        # → 节点管理存储配置 → Stargazer Worker 拉取并周期调度采集
```

### 4.2 Stargazer 采集执行链路

```python
# 触发点: Stargazer Worker Pool 周期调度 collect_plugin_task

async def collect_plugin_task(ctx, params, task_id):
    # params 来自节点管理推送的配置，headers 被解析为:
    # {
    #   "plugin_name": "config_file_info",
    #   "model_id": "config_file",
    #   "host": "10.0.0.1",
    #   "config_file_path": "/etc/nginx/nginx.conf",
    #   "file_size_limit": "1048576",
    #   "callback_subject": "receive_config_file_result",
    #   "node_id": "xxx",
    #   "username": "root",
    #   "password": "${PASSWORD_password_cmdb_123}",
    #   ...
    # }

    collect_service = CollectionService(params)
    result = await collect_service.collect()
    # → PluginExecutor → ConfigFileInfo.list_all_resources()
    # → 构建 bash/powershell 脚本
    # → nats_request("ssh.execute.{node_id}", script)
    # → nats-executor (Go) SSH 执行脚本
    # → 脚本输出 JSON: {status, content_base64, size, error, error_type}

    # CONFIG_FILE 路由分支：不推 VM，回传 CMDB
    plugin_name = params.get("plugin_name")
    if plugin_name == "config_file_info":
        callback_subject = params.get("callback_subject", "receive_config_file_result")
        callback_data = result  # 当前实现直接返回扁平 payload
        await nats_publish(callback_subject, callback_data)
    else:
        await publish_metrics_to_nats(ctx, result, params, task_id)
```

### 4.3 CMDB 接收结果 — process_collect_result

```python
# 触发点: NATS handler receive_config_file_result → ConfigFileService.process_collect_result

@staticmethod
def process_collect_result(data: dict) -> None:
    payload = normalize_collect_payload(data)
    task_id = payload["collect_task_id"]
    instance_id = payload["instance_id"]
    model_id = payload["model_id"]
    file_path = payload["file_path"]
    result = payload
    timestamp = payload.get("version") or now().strftime("%Y-%m-%dT%H:%M:%S")

    task = CollectModels.objects.get(id=task_id)
    file_name = task.params.get("config_file_name", file_path.rsplit("/", 1)[-1])

    logger.info(f"[ConfigFileService] 收到采集结果 task_id={task_id}, instance={instance_id}")

    # 1. 处理失败结果，并同步 CollectModels 任务状态
    if result.get("status") != "success":
        status_map = {
            "file_not_found": ConfigFileVersionStatus.FILE_NOT_FOUND,
            "permission_denied": ConfigFileVersionStatus.PERMISSION_DENIED,
            "file_too_large": ConfigFileVersionStatus.FILE_TOO_LARGE,
            "not_text": ConfigFileVersionStatus.NOT_TEXT,
        }
        status = status_map.get(result.get("error_type"), ConfigFileVersionStatus.ERROR)
        ConfigFileVersion.objects.create(
            collect_task=task, instance_id=instance_id, model_id=model_id,
            version=timestamp, file_path=file_path, file_name=file_name,
            status=status, error_message=result.get("error", ""),
        )
        sync_collect_model_status(task, status=status, version=timestamp, changed=False, error=result.get("error", ""))
        logger.warning(f"[ConfigFileService] 采集失败 task_id={task_id}, status={status}")
        return

    # 2. 解码内容 + 获取哈希
    content = base64.b64decode(result["content_base64"]).decode("utf-8")
    content_hash = result.get("content_hash") or hashlib.sha256(content.encode("utf-8")).hexdigest()

    # 3. 增量判断
    last = (ConfigFileVersion.objects
            .filter(instance_id=instance_id, file_path=file_path,
                    status=ConfigFileVersionStatus.SUCCESS)
            .order_by("-created_at").first())
    if last and last.content_hash == content_hash:
        sync_collect_model_status(task, status="success", version=timestamp, changed=False, version_obj=last)
        logger.info(f"[ConfigFileService] 内容无变化 task_id={task_id}")
        return

    # 4. 创建版本 + 通过 FileField 上传 MinIO
    version = ConfigFileVersion(
        collect_task=task, instance_id=instance_id, model_id=model_id,
        version=timestamp, file_path=file_path, file_name=file_name,
        content_hash=content_hash,
        file_size=result.get("size", 0),
        status=ConfigFileVersionStatus.SUCCESS,
    )
    version.save_content(content)  # 纯文本 → FileField.save() → MinIO 上传
    version.save()
    sync_collect_model_status(task, status="success", version=timestamp, changed=True, version_obj=version)
    logger.info(f"[ConfigFileService] 新版本保存完成 task_id={task_id}, version={timestamp}")
```

### 4.4 ConfigFileCollect.__call__() — 查询状态模式

```python
# 触发点: sync_collect_task → JobCollect → collect_config_file → ConfigFileCollect

def __call__(self):
    """
    不执行实际采集（采集由 Stargazer 异步完成并通过 NATS 回传）。
    仅查询 ConfigFileVersion 最新状态，构建 sync_collect_task 需要的返回值。
    """
    task = CollectModels.objects.get(id=self.task_id)
    file_path = task.params.get("config_file_path", "")
    instance = task.instances[0] if task.instances else {}
    instance_id = instance.get("_id", "")

    logger.info(f"[ConfigFileCollect] 查询采集状态 task_id={task.id}, path={file_path}")

    # 查询最新版本；真实任务状态以 ConfigFileService.process_collect_result 写回 CollectModels 为准
    latest = (ConfigFileVersion.objects
              .filter(collect_task=task, instance_id=instance_id)
              .order_by("-created_at").first())

    result = {}
    if latest:
        result = {
            "config_file": {
                "version": latest.version,
                "status": latest.status,
                "file_path": latest.file_path,
            }
        }

    # format_data 必须包含 __raw_data__ 以避免 sync_collect_task 报"没有发现任何有效数据"
    format_data = {
        "add": [], "update": [], "delete": [], "association": [],
        "__raw_data__": [{"__time__": latest.created_at.isoformat()}] if latest else [],
    }
    return result, format_data
```

### 4.5 MinIO 上传/下载（通过模型方法）

```python
# 上传：通过 ConfigFileVersion.save_content()
version = ConfigFileVersion(...)
version.save_content(text_content)  # 纯文本 → FileField.save() → MinIO 自动上传
version.save()

# 下载：通过 ConfigFileVersion.read_content()
text = version.read_content()  # FileField.open() → 返回文本
```

> 参考 `apps.mlops.models.timeseries_predict.TimeSeriesPredictTrainData`，
> 使用 `FileField(storage=MinioBackend(bucket_name=...))` 管理 MinIO 存储，
> 不在 Service 层手动实例化 MinioBackend，由 Django FileField 统一管理存储后端。

### 4.6 diff 生成

```python
def generate_diff(content_1: str, content_2: str, label_1: str, label_2: str) -> str:
    import difflib
    lines_1 = content_1.splitlines(keepends=True)
    lines_2 = content_2.splitlines(keepends=True)
    diff = difflib.unified_diff(lines_1, lines_2, fromfile=label_1, tofile=label_2)
    return "".join(diff)
```

### 4.7 文件列表聚合

```python
def get_file_list(instance_id: str) -> list[dict]:
    """按 (instance_id, file_path) 分组，取每组最新记录"""
    from django.db.models import Max

    latest_ids = (
        ConfigFileVersion.objects.filter(instance_id=instance_id)
        .values("file_path").annotate(latest_id=Max("id"))
        .values_list("latest_id", flat=True)
    )
    return list(ConfigFileVersion.objects.filter(id__in=latest_ids).values(
        "file_path", "file_name", "collect_task_id", "version", "status", "created_at"
    ))
```

### 4.8 采集脚本（Linux Bash）

```bash
#!/bin/bash
# 参数: $1=文件路径, $2=大小上限(字节)
FILE_PATH="$1"; SIZE_LIMIT="$2"

if [ ! -f "$FILE_PATH" ]; then
    echo '{"status":"error","error_type":"file_not_found","error":"文件不存在","content_base64":"","content_hash":"","size":0}'
    exit 0
fi
if [ ! -r "$FILE_PATH" ]; then
    echo '{"status":"error","error_type":"permission_denied","error":"无读取权限","content_base64":"","content_hash":"","size":0}'
    exit 0
fi
FILE_SIZE=$(stat -c%s "$FILE_PATH" 2>/dev/null || stat -f%z "$FILE_PATH")
if [ "$FILE_SIZE" -gt "$SIZE_LIMIT" ]; then
    echo '{"status":"error","error_type":"file_too_large","error":"文件超限: '$FILE_SIZE' > '$SIZE_LIMIT'","content_base64":"","content_hash":"","size":'$FILE_SIZE'}'
    exit 0
fi
FILE_TYPE=$(file -b --mime-type "$FILE_PATH")
case "$FILE_TYPE" in text/*|application/json|application/xml|application/yaml|application/x-yaml) ;; *)
    echo '{"status":"error","error_type":"not_text","error":"非文本: '$FILE_TYPE'","content_base64":"","content_hash":"","size":'$FILE_SIZE'}'
    exit 0 ;; esac
CONTENT=$(base64 < "$FILE_PATH")
HASH=$(sha256sum "$FILE_PATH" | awk '{print $1}')
echo '{"status":"success","content_base64":"'$CONTENT'","content_hash":"'$HASH'","size":'$FILE_SIZE',"error":""}'
```

### 4.9 采集脚本（Windows PowerShell）

```powershell
param([string]$FilePath, [int]$SizeLimit)
if (-not (Test-Path $FilePath -PathType Leaf)) {
    Write-Output '{"status":"error","error_type":"file_not_found","error":"文件不存在","content_base64":"","content_hash":"","size":0}'; exit
}
$fi = Get-Item $FilePath; $sz = $fi.Length
if ($sz -gt $SizeLimit) {
    Write-Output "{`"status`":`"error`",`"error_type`":`"file_too_large`",`"error`":`"文件超限`",`"content_base64`":`"`",`"content_hash`":`"`",`"size`":$sz}"; exit
}
$bytes = [IO.File]::ReadAllBytes($FilePath)
for ($i=0; $i -lt [Math]::Min($bytes.Length,8192); $i++) {
    if ($bytes[$i] -eq 0) {
        Write-Output "{`"status`":`"error`",`"error_type`":`"not_text`",`"error`":`"非文本文件`",`"content_base64`":`"`",`"content_hash`":`"`",`"size`":$sz}"; exit
    }
}
$b64 = [Convert]::ToBase64String($bytes)
$sha = [System.Security.Cryptography.SHA256]::Create()
$hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-","").ToLower()
Write-Output "{`"status`":`"success`",`"content_base64`":`"$b64`",`"content_hash`":`"$hash`",`"size`":$sz,`"error`":`"`"}"
```

---

## 4-A) 完整采集链路时序

```text
[任务创建]
┌─────────────┐   ┌──────────────┐   ┌─────────────┐   ┌───────────┐
│  CMDB API    │   │  节点管理     │   │  Stargazer   │   │  Worker   │
│  (Django)    │   │  (Node Mgmt) │   │  Agent       │   │  Pool     │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └─────┬─────┘
       │                  │                   │                  │
       │ 1. CollectModelService.create()      │                  │
       │ → push_butch_node_params()           │                  │
       │ → ConfigFileNodeParams.push_params() │                  │
       │──────────────────→                   │                  │
       │                  │ 2. 存储采集配置    │                  │
       │                  │──────────────────→│                  │
       │                  │                   │ 3. 拉取配置       │
       │                  │                   │──────────────────→│
       │                  │                   │   创建周期调度     │

[周期采集]
┌───────────┐   ┌───────────┐   ┌──────────────┐   ┌───────────┐   ┌──────────┐
│  Stargazer │   │   NATS     │   │ nats-executor│   │ 目标主机   │   │  CMDB    │
│  Worker    │   │   Server   │   │  (Go SSH)    │   │           │   │  Server  │
└─────┬──────┘   └─────┬──────┘   └──────┬───────┘   └─────┬─────┘   └────┬─────┘
      │                │                  │                  │              │
      │ 4. collect_plugin_task()          │                  │              │
      │ → ConfigFileInfo.list_all_resources()                │              │
      │ → nats_request("ssh.execute.*")   │                  │              │
      │───────────────→│                  │                  │              │
      │                │─────────────────→│                  │              │
      │                │                  │ 5. SSH exec bash │              │
      │                │                  │─────────────────→│              │
      │                │                  │  ← JSON output   │              │
      │                │                  │←─────────────────│              │
      │                │  ← SSH result    │                  │              │
      │←───────────────│←─────────────────│                  │              │
      │                │                  │                  │              │
      │ 6. 判断 plugin_name == "config_file_info"            │              │
      │ → nats_publish("receive_config_file_result", data)   │              │
      │───────────────→│                  │                  │              │
      │                │──────────────────────────────────────────────────→│
      │                │                  │                  │              │
      │                │                  │                  │  7. NATS handler
      │                │                  │                  │  receive_config_file_result
      │                │                  │                  │  → process_collect_result
      │                │                  │                  │  → SHA256 比对
      │                │                  │                  │  → MinIO 上传
      │                │                  │                  │  → ConfigFileVersion 写入

[sync_collect_task 定期执行]
┌──────────┐   ┌──────────────────────────────────────────────────────────┐
│  Celery   │   │ sync_collect_task(instance_id)                          │
│  Worker   │   │ → JobCollect → ConfigFileCollect.__call__()             │
│           │   │ → 查询 ConfigFileVersion 最新状态                        │
│           │   │ → 返回 (result, format_data) → 更新 CollectModels 摘要   │
└──────────┘   └──────────────────────────────────────────────────────────┘
```

---

## 5) 第三方依赖与环境要求

**无新增依赖。** 使用的所有包均已在项目中：

| 包 | 用途 |
|---|---|
| `django_minio_backend` | MinIO 存储操作（FileField storage backend） |
| `hashlib` (stdlib) | SHA256 哈希 |
| `difflib` (stdlib) | unified diff 生成 |
| `base64` (stdlib) | 采集脚本内容编码 |

---

## 6) 关键注释与日志规范

### 6.1 日志前缀约定

```python
# Server 端
from apps.core.logger import cmdb_logger as logger

"[ConfigFileCollect]"      — sync_collect_task 中查询采集状态
"[ConfigFileService]"      — NATS 回调结果处理、MinIO 操作、版本查询
"[ConfigFileVersionView]"  — API 请求处理

# Stargazer 端
import logging
logger = logging.getLogger("stargazer")

"[ConfigFileInfo]"         — 远程脚本构建与 SSH 执行
"[PluginHandler]"          — CONFIG_FILE 路由分支与 NATS 回传
```

### 6.2 关键日志点

```python
# Server 端 — NATS 回调结果处理（核心链路）
logger.info(f"[ConfigFileService] 收到采集结果 task_id={task_id}, instance={instance_id}")
logger.info(f"[ConfigFileService] 内容无变化，跳过版本生成 task_id={task_id}")
logger.info(f"[ConfigFileService] 新版本保存完成 task_id={task_id}, version={timestamp}, key={saved_key}")
logger.warning(f"[ConfigFileService] 采集失败 task_id={task_id}, status={status}, error={error_msg}")
logger.error(f"[ConfigFileService] 处理异常 task_id={task_id}, error={traceback.format_exc()}")

# Server 端 — MinIO 操作（通过模型 FileField）
logger.info(f"[ConfigFileService] MinIO 上传完成 version_id={version.id}, content={version.content.name}")
logger.error(f"[ConfigFileService] MinIO 读取失败 version_id={version.id}, error={e}")

# Server 端 — sync_collect_task 查询
logger.info(f"[ConfigFileCollect] 查询采集状态 task_id={task.id}, path={file_path}")

# Server 端 — API 层
logger.info(f"[ConfigFileVersionView] 版本内容请求 version_id={pk}")
logger.info(f"[ConfigFileVersionView] diff 请求 v1={version_id_1}, v2={version_id_2}")

# Stargazer 端 — 采集执行
logger.info(f"[ConfigFileInfo] 开始执行 task_id={task_id}, host={host}, path={file_path}")
logger.info(f"[ConfigFileInfo] SSH 执行完成 task_id={task_id}, status={result_status}")
logger.error(f"[ConfigFileInfo] SSH 执行异常 task_id={task_id}, error={e}")

# Stargazer 端 — 结果路由
logger.info(f"[PluginHandler] CONFIG_FILE 回传 CMDB: task_id={task_id}, subject={callback_subject}")
```

### 6.3 函数注释规范

```python
class ConfigFileNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    """
    配置文件采集节点参数。
    继承 SSHNodeParamsMixin 复用 SSH 凭据与接入点逻辑。
    在 custom_headers() 中注入 config_file_path/file_size_limit/callback_subject。
    自动注册到 BaseNodeParams._registry["config_file"]。
    """

class ConfigFileInfo(SSHPlugin):
    """
    配置文件采集插件（Stargazer 侧）。
    继承 SSHPlugin 复用 NATS → nats-executor SSH 执行链路。
    根据 os_type 构建 bash/powershell 采集脚本，执行后解析 JSON 输出。
    """

class ConfigFileService:
    """
    配置文件版本管理服务。
    职责：NATS 回传结果处理（process_collect_result）、unified diff 生成、版本列表聚合查询。
    MinIO 上传/下载通过 ConfigFileVersion 模型的 save_content() / read_content() 方法完成，
    参考 TimeSeriesPredictTrainData 使用 FileField(storage=MinioBackend) 模式。
    """

class ConfigFileCollect:
    """
    配置文件采集执行类（查询模式）。
    不执行实际采集（采集由 Stargazer 通过节点管理链路异步完成）。
    仅查询 ConfigFileVersion 最新状态，构建 format_data 供 sync_collect_task 更新任务摘要。
    """
```

---

## 7) 测试方案

### 7.1 后端测试文件

```text
server/apps/cmdb/tests/test_config_file_collect.py       (A) ConfigFileCollect 查询逻辑测试
server/apps/cmdb/tests/test_config_file_service.py        (A) ConfigFileService 测试（含 process_collect_result）
server/apps/cmdb/tests/test_config_file_path.py           (A) 路径校验测试
server/apps/cmdb/tests/test_config_file_node_params.py    (A) ConfigFileNodeParams 推送参数测试
```

### 7.2 测试用例

| 场景 | 预期 |
|------|------|
| 有效 Linux 路径 `/etc/nginx/nginx.conf` | 校验通过，提取文件名 `nginx.conf` |
| 有效 Windows 路径 `C:\Windows\System32\drivers\etc\hosts` | 校验通过，提取 `hosts` |
| 无效相对路径 `nginx.conf` | 校验失败 |
| 含通配符 `/etc/*.conf` | 校验失败 |
| 空路径 | 校验失败 |
| ConfigFileNodeParams.custom_headers() | 包含 cmdbconfig_file_path、cmdbcallback_subject 等 headers |
| ConfigFileNodeParams.push_params() | 生成有效的节点配置列表 |
| should_sync_node_params(config_file_task) | 返回 True（不再排除） |
| process_collect_result: 采集成功 + 内容有变化 | 创建 SUCCESS 版本，version.content 不为空 |
| process_collect_result: 采集成功 + 内容无变化 | 不创建新版本 |
| process_collect_result: 文件不存在 | FILE_NOT_FOUND 版本，无 content_key |
| process_collect_result: 文件超限 | FILE_TOO_LARGE 版本 |
| ConfigFileCollect: 有最新版本 | 返回版本信息和有效 __raw_data__ |
| ConfigFileCollect: 无版本 | 返回空 __raw_data__（sync_collect_task 报无有效数据） |
| diff 两版本 | 返回 unified diff 格式文本 |
| file_list 聚合 | 每个 file_path 返回最新版本 |

### 7.3 前端验证

```bash
cd web && pnpm lint && pnpm type-check
```

---

## 8) 发布与回滚策略

### 发布步骤

1. 数据库迁移：`python manage.py makemigrations cmdb && python manage.py migrate`（新增 `ConfigFileVersion` 表）。
2. MinIO bucket：服务启动时 `MINIO_BUCKET_CHECK_ON_SAVE = True` 自动创建 `cmdb-config-file` bucket。
3. 部署 Stargazer（含 ConfigFileInfo 插件）→ 部署后端代码 → 部署前端代码。

### 回滚策略

1. 代码回滚：`git revert` 对应提交。
2. 数据库回滚：`python manage.py migrate cmdb <前一迁移名>`，删除 `ConfigFileVersion` 表。
3. MinIO 数据：保留 `cmdb-config-file` bucket（无副作用），如需清理可手动执行。
4. `should_sync_node_params` 回滚后恢复 CONFIG_FILE 排除条件，已推送到节点管理的配置需手动清理。
5. `CollectPluginTypes.CONFIG_FILE` 回滚后，已创建的配置文件采集任务将无法被 `JobCollect` 分发，状态保持 NOT_START 或 ERROR，不影响其他类型任务。
