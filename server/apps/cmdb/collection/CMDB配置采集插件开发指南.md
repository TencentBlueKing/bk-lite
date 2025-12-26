# CMDB 配置采集插件开发指南

## 概述

本文档说明如何在 CMDB 系统中新增一个配置采集对象插件。整个流程涉及三个核心部分：

1. **采集对象树的补充**：定义节点配置参数（node_configs）
2. **推送到节点管理的配置**：通过节点管理将配置推送到采集节点
3. **执行同步的时候，查询 VM 和格式化处理**：从 VictoriaMetrics 查询采集数据并格式化

## 架构设计

### 核心模块说明

```
apps/cmdb/
├── node_configs/          # 节点配置参数（用于推送到节点管理）
│   ├── base.py           # 基类 BaseNodeParams
│   ├── config_factory.py # 工厂类 NodeParamsFactory
│   ├── ssh/              # SSH 类型采集配置
│   ├── databases/        # 数据库类型采集配置
│   ├── cloud/            # 云厂商类型采集配置
│   └── network/          # 网络设备类型采集配置
├── collect_tasks/         # 采集任务（编排采集流程）
│   ├── base.py           # 基类 BaseCollect
│   ├── host.py           # 主机采集任务
│   ├── databases.py      # 数据库采集任务
│   └── middleware.py     # 中间件采集任务
└── collection/
    ├── collect_plugin/    # 采集插件（查询 VM 并格式化数据）
    │   ├── base.py       # 基类 CollectBase
    │   ├── host.py       # 主机采集插件
    │   ├── databases.py  # 数据库采集插件
    │   └── middleware.py # 中间件采集插件
    └── constants.py       # 定义采集指标映射关系
```

### 设计模式

系统采用了以下设计模式：

1. **自动注册模式**：通过 `__init_subclass__` 钩子自动注册子类
2. **工厂模式**：`NodeParamsFactory` 根据 `model_id` 创建对应的配置类
3. **模板方法模式**：基类定义流程骨架，子类实现具体细节
4. **策略模式**：不同采集对象使用不同的采集策略

---

## 第一部分：采集对象树的补充（node_configs）

### 1.1 目的

`node_configs` 模块负责生成推送到节点管理的配置参数，包括：
- 采集插件名称
- 凭据信息（用户名、密码、端口等）
- 环境变量配置
- 采集间隔、超时时间等
- HTTP Headers（通过 Jinja2 模板渲染成 Telegraf 配置）

### 1.2 基类说明

#### BaseNodeParams（apps/cmdb/node_configs/base.py）

核心属性和方法：

```python
class BaseNodeParams(metaclass=ABCMeta):
    PLUGIN_MAP = {}              # 插件名称映射 {model_id: plugin_name}
    plugin_name = None           # 插件名称（子类必须设置）
    _registry = {}               # 自动注册的子类映射 {model_id: cls}
    interval = 300               # 采集间隔（秒）
    timeout = 30                 # 超时时间
    response_timeout = 30        # 响应超时
    executor_type = "protocol"   # 执行器类型：protocol/job
    
    # 自动注册机制
    def __init_subclass__(cls, **kwargs):
        # 子类定义 supported_model_id 和 plugin_name 时自动注册
        
    # 必须由子类实现
    @abstractmethod
    def set_credential(self, *args, **kwargs):
        """生成凭据配置"""
        
    # 可选实现
    def env_config(self, *args, **kwargs):
        """生成环境变量配置（用于存放敏感信息如密码）"""
        
    def custom_headers(self):
        """生成 HTTP Headers（会传递给 Telegraf）"""
        
    def push_params(self):
        """生成节点管理创建配置的参数（通常不需要重写）"""
```

#### SSHNodeParamsMixin（apps/cmdb/node_configs/ssh/base.py）

SSH 类型采集的混入类，提供了通用的凭据和环境变量配置：

```python
class SSHNodeParamsMixin:
    executor_type = "job"  # SSH 类型使用 job 执行器
    
    def set_credential(self, *args, **kwargs):
        # 返回 SSH 连接所需的用户名、密码（引用环境变量）、端口等
        
    def env_config(self, *args, **kwargs):
        # 返回密码的环境变量配置
```

### 1.3 新增步骤

#### 步骤 0：在 COLLECT_OBJ_TREE 中注册采集对象（**必须先做**）

**⚠️ 重要**：必须先在前端配置树中注册采集对象，否则前端无法展示该采集类型，用户无法创建采集任务！

**文件路径**：`apps/cmdb/constants/constants.py`

在 `COLLECT_OBJ_TREE` 列表中添加新的采集对象配置：

```python
COLLECT_OBJ_TREE = [
    # ...其他分类
    {
        "id": "middleware",
        "name": "中间件",
        "children": [
            {"id": "nginx", "model_id": "nginx", "name": "Nginx", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB, "tag": ["JOB", "Linux"], "desc": "发现与采集Nginx基础配置信息",
             "encrypted_fields": ["password"]},
            # 新增 Tomcat 采集对象
            {"id": "tomcat", "model_id": "tomcat", "name": "Tomcat", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB, "tag": ["JOB", "Linux"], "desc": "发现与采集Tomcat基础配置信息",
             "encrypted_fields": ["password"]},
            # ...其他中间件
        ],
    }
]
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| `id` | string | ✅ | 采集对象唯一标识，前端使用 | `"tomcat"` |
| `model_id` | string | ✅ | 对应 CMDB 模型 ID，**必须与后续步骤中的 `supported_model_id` 一致** | `"tomcat"` |
| `name` | string | ✅ | 前端展示名称 | `"Tomcat"` |
| `task_type` | string | ✅ | 采集插件类型，从 `CollectPluginTypes` 枚举中选择 | `CollectPluginTypes.MIDDLEWARE` |
| `type` | string | ✅ | 采集驱动类型，从 `CollectDriverTypes` 枚举中选择 | `CollectDriverTypes.JOB` |
| `tag` | list | ❌ | 标签数组，前端展示用 | `["JOB", "Linux"]` |
| `desc` | string | ❌ | 描述信息，前端展示用 | `"发现与采集Tomcat基础配置信息"` |
| `encrypted_fields` | list | ✅ | **需要加密的凭据字段列表**，前端会对这些字段加密处理 | `["password"]` |

**采集插件类型（task_type）**：

```python
class CollectPluginTypes:
    VM = "vm"              # VMware 虚拟化
    SNMP = "snmp"          # SNMP 协议（网络设备）
    K8S = "k8s"            # Kubernetes
    CLOUD = "cloud"        # 云平台 API
    PROTOCOL = "protocol"  # 数据库协议
    HOST = "host"          # 主机采集
    DB = "db"              # 数据库采集（SSH 方式）
    MIDDLEWARE = "middleware"  # 中间件采集
    IP = "ip"              # IP 范围采集
    OTHER = "other"        # 其他
```

**采集驱动类型（type）**：

```python
class CollectDriverTypes:
    PROTOCOL = "protocol"  # 协议采集（直接连接目标，如 MySQL、VMware API）
    JOB = "job"            # 脚本采集（通过节点管理 JOB 执行脚本）
```

**encrypted_fields 说明**：

必须列出所有敏感字段，前端会对这些字段进行加密后再传给后端：

| 采集类型 | 常见加密字段 |
|---------|-------------|
| SSH 类型 | `["password"]` |
| 数据库类型 | `["password"]` |
| 云平台类型 | `["accessKey", "accessSecret"]` 或 `["secretSecret"]` |
| 网络设备（SNMP v3） | `["authkey", "privkey"]` |
| 网络设备（SNMP v2c） | `["community"]` |

**完整示例：新增 ActiveMQ 采集**

```python
{
    "id": "middleware",
    "name": "中间件",
    "children": [
        # ...其他中间件
        {
            "id": "activemq",                           # 唯一标识
            "model_id": "activemq",                     # 模型 ID（与 supported_model_id 一致）
            "name": "ActiveMQ",                         # 前端展示名称
            "task_type": CollectPluginTypes.MIDDLEWARE, # 采集插件类型
            "type": CollectDriverTypes.JOB,             # 驱动类型：JOB（SSH 脚本采集）
            "tag": ["JOB", "Linux", "消息队列"],         # 标签
            "desc": "发现与采集ActiveMQ基础配置信息",     # 描述
            "encrypted_fields": ["password"]            # 加密字段：SSH 密码
        },
    ],
}
```

**新增数据库类型示例：PostgreSQL**

```python
{
    "id": "databases",
    "name": "数据库",
    "children": [
        # ...其他数据库
        {
            "id": "postgresql",
            "model_id": "postgresql",
            "name": "PostgreSQL",
            "task_type": CollectPluginTypes.PROTOCOL,  # 协议采集（直接连接数据库）
            "type": CollectDriverTypes.PROTOCOL,
            "tag": ["Agentless", "TCP", "SQL"],
            "desc": "采集PostgreSQL配置信息",
            "encrypted_fields": ["password"]           # 数据库密码
        },
    ],
}
```

**新增云平台类型示例：AWS**

```python
{
    "id": "cloud",
    "name": "云平台",
    "children": [
        # ...其他云平台
        {
            "id": "aws_account",
            "model_id": "aws_account",
            "name": "AWS",
            "task_type": CollectPluginTypes.CLOUD,
            "type": CollectDriverTypes.PROTOCOL,
            "tag": ["SDK", "API"],
            "desc": "采集AWS账户下EC2、RDS等资产清单",
            "encrypted_fields": ["accessKey", "secretKey"]  # AWS 凭据
        },
    ],
}
```

#### 步骤 1：确定采集类型和存放位置

根据采集对象类型选择对应目录：

| 采集类型 | 目录 | 说明 |
|---------|------|------|
| SSH 协议采集 | `apps/cmdb/node_configs/ssh/` | 通过 SSH 远程执行脚本采集 |
| 数据库协议采集 | `apps/cmdb/node_configs/databases/` | 通过数据库协议连接采集 |
| 云厂商 API 采集 | `apps/cmdb/node_configs/cloud/` | 调用云厂商 API 采集 |
| 网络设备采集 | `apps/cmdb/node_configs/network/` | 通过 SNMP 等协议采集 |

#### 步骤 2：创建配置类文件

以新增 Tomcat 中间件采集为例（SSH 类型）：

**文件路径**：`apps/cmdb/node_configs/ssh/tomcat.py`

```python
# -- coding: utf-8 --
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class TomcatNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    """Tomcat 采集节点配置"""
    
    # 必须设置：模型 ID（对应 CMDB 中的对象模型）
    supported_model_id = "tomcat"
    
    # 必须设置：插件名称（对应 Stargazer 中的采集脚本）
    plugin_name = "tomcat_info"
    
    # 可选：采集间隔（秒），默认 300
    interval = 300
    
    # 可选：如果 IP 字段名不是 "host"，需要重写
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_field = "ip_addr"  # 如果实例数据中 IP 字段是 ip_addr
```

如果需要**自定义凭据**（如数据库连接信息），参考 MySQL 的实现：

**文件路径**：`apps/cmdb/node_configs/databases/mysql.py`

```python
from apps.cmdb.node_configs.base import BaseNodeParams


class MysqlNodeParams(BaseNodeParams):
    supported_model_id = "mysql"
    plugin_name = "mysql_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        """生成 MySQL 连接凭据"""
        _password = f"PASSWORD_password_{self._instance_id}"
        credential_data = {
            "port": self.credential.get("port", 3306),
            "user": self.credential.get("user", ""),
            "password": "${" + _password + "}",  # 引用环境变量
        }
        return credential_data

    def env_config(self, *args, **kwargs):
        """将真实密码放在环境变量中（节点管理会加密存储）"""
        return {f"PASSWORD_password_{self._instance_id}": self.credential.get("password", "")}
```

#### 步骤 3：自动注册机制说明

**无需手动注册**！系统会自动扫描 `node_configs` 目录下的所有模块：

1. `apps/cmdb/node_configs/__init__.py` 中的 `_auto_register_node_params()` 函数会递归导入所有子模块
2. 当子类被导入时，`BaseNodeParams.__init_subclass__()` 钩子会自动执行
3. 自动将 `supported_model_id` 和类映射关系注册到 `_registry` 中
4. 自动将 `supported_model_id` 和 `plugin_name` 映射关系注册到 `PLUGIN_MAP` 中

#### 步骤 4：在 collection/constants.py 中定义采集指标

虽然不是 `node_configs` 的一部分，但为了后续流程，需要在 `apps/cmdb/collection/constants.py` 中定义采集指标：

```python
# 中间件采集指标映射
MIDDLEWARE_METRIC_MAP = {
    "nginx": ["nginx_info_gauge"],
    "tomcat": ["tomcat_info_gauge"],  # 新增 Tomcat
    # ...
}
```

**注意**：指标名称必须与 Stargazer 采集脚本中上报到 VictoriaMetrics 的指标名称完全一致。

---

## 第二部分：推送到节点管理的配置

### 2.1 目的

将配置参数推送到节点管理系统，节点管理会：
1. 根据配置生成 Telegraf 采集配置文件
2. 分发到指定的采集节点
3. 定期执行采集任务
4. 将采集数据推送到 VictoriaMetrics

### 2.2 推送流程

```
用户创建/更新采集任务
    ↓
CollectModelService.create/update
    ↓
NodeParamsFactory.get_node_params(instance)  # 根据 model_id 获取对应的配置类
    ↓
node_params.push_params()  # 生成推送参数
    ↓
NodeMgmt().batch_add_node_child_config(params)  # RPC 调用节点管理 API
    ↓
节点管理接收配置
    ↓
Jinja2 渲染 Telegraf 配置（base.child.toml.j2）
    ↓
分发到采集节点并启动采集
```

### 2.3 推送参数格式

`push_params()` 方法生成的参数格式（在 `BaseNodeParams` 中已实现，通常不需要重写）：

```python
[
    {
        "id": "cmdb_123",                    # 配置实例 ID
        "collect_type": "http",              # 采集类型（固定为 http）
        "type": "tomcat",                    # 模型 ID
        "content": "渲染后的 Telegraf 配置",   # Jinja2 模板渲染结果
        "node_id": "节点管理中的节点 ID",
        "collector_name": "Telegraf",        # 采集器名称
        "env_config": {                      # 环境变量（敏感信息）
            "PASSWORD_password_cmdb_123": "actual_password"
        }
    }
]
```

### 2.4 配置模板说明

Jinja2 模板位置：`apps/cmdb/support-files/base.child.toml.j2`

模板会接收 `context` 参数（由 `render_template()` 生成）：

```toml
[[inputs.http]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
  interval = "{{ interval }}s"
  timeout = "{{ timeout }}s"
  response_timeout = "{{ response_timeout }}s"
  
  # 通过 Headers 传递采集参数
  headers = {{ headers | to_toml }}
  
  # 其他配置...
```

Headers 中包含的关键参数（由 `custom_headers()` 生成）：

```python
{
    "cmdbplugin_name": "tomcat_info",      # 插件名称
    "cmdbhosts": "192.168.1.1,192.168.1.2",  # IP 列表
    "cmdbexecutor_type": "job",            # 执行器类型
    "cmdbmodel_id": "tomcat",              # 模型 ID
    "cmdbport": "22",                      # SSH 端口（如果是 SSH 类型）
    "cmdbusername": "root",                # SSH 用户名
    "cmdbpassword": "${PASSWORD_password_cmdb_123}",  # 引用环境变量
    # ...其他凭据信息
}
```

### 2.5 实际调用链路

```python
# apps/cmdb/services/collect_service.py

class CollectModelService:
    @classmethod
    def create(cls, request, view_self):
        # ...创建采集任务实例
        
        # 推送配置到节点管理
        if not instance.is_k8s:
            cls.push_butch_node_params(instance)
    
    @staticmethod
    def push_butch_node_params(instance):
        # 工厂模式获取配置类
        node = NodeParamsFactory.get_node_params(instance)
        
        # 生成推送参数
        node_params = node.main()  # 内部调用 push_params()
        
        # RPC 调用节点管理
        node_mgmt = NodeMgmt()
        result = node_mgmt.batch_add_node_child_config(node_params)
```

---

## 第三部分：执行同步时查询 VM 和格式化处理

### 3.1 目的

定时任务触发后，从 VictoriaMetrics 查询采集到的原始数据，并格式化成 CMDB 实例数据。

### 3.2 整体流程

```
定时任务触发（Celery）
    ↓
sync_collect_task(task_id)
    ↓
BaseCollect.run() → 编排采集流程
    ↓
MetricsCannula.collect_controller() → 采集控制器
    ↓
CollectBase.run() → 查询 VM 并格式化
    ↓
    ├─ query_data() → 查询 VictoriaMetrics
    ├─ format_data() → 解析原始指标数据
    └─ format_metrics() → 转换为 CMDB 实例字段
    ↓
Management.controller() → 与现有数据对比，生成增删改操作
    ↓
返回格式化数据（add/update/delete/association）
```

### 3.3 模块说明

#### 3.3.1 采集任务类（collect_tasks）

**作用**：编排采集流程，选择对应的采集插件

**基类**：`apps/cmdb/collect_tasks/base.py` → `BaseCollect`

```python
class BaseCollect(object):
    COLLECT_PLUGIN = None  # 子类必须指定采集插件类
    
    def __init__(self, instance_id, default_metrics=None):
        self.task = CollectModels.objects.get(id=instance_id)
        # ...初始化
    
    def run(self):
        """执行采集"""
        # 创建指标纳管控制器
        metrics_cannula = MetricsCannula(
            inst_id=self.inst_id,
            organization=self.organization,
            inst_name=self.inst_name,
            task_id=self.task_id,
            collect_plugin=self.COLLECT_PLUGIN,  # 传入采集插件类
            # ...
        )
        
        # 执行采集并返回结果
        result = metrics_cannula.collect_controller()
        format_data = self.format_collect_data(result)
        return metrics_cannula.collect_data, format_data
```

**示例**：中间件采集任务（`apps/cmdb/collect_tasks/middleware.py`）

```python
from apps.cmdb.collect_tasks.base import BaseCollect
from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics


class MiddlewareCollect(BaseCollect):
    COLLECT_PLUGIN = MiddlewareCollectMetrics  # 指定采集插件
```

#### 3.3.2 采集插件类（collection/collect_plugin）

**作用**：查询 VM、解析数据、字段映射

**基类**：`apps/cmdb/collection/collect_plugin/base.py` → `CollectBase`

```python
class CollectBase(metaclass=ABCMeta):
    # 子类必须定义采集指标
    @property
    @abstractmethod
    def _metrics(self):
        """返回该对象类型的采集指标列表"""
        raise NotImplementedError
    
    # 子类必须实现数据格式化
    @abstractmethod
    def format_data(self, data):
        """解析 VM 返回的原始数据"""
        raise NotImplementedError
    
    @abstractmethod
    def format_metrics(self):
        """将解析后的数据映射为 CMDB 字段"""
        raise NotImplementedError
    
    # 基类提供的通用方法
    def prom_sql(self):
        """生成 PromQL 查询语句"""
        sql = " or ".join(f"{m}{{instance_id={self._instance_id}}}" for m in self._metrics)
        return sql
    
    def query_data(self):
        """查询 VictoriaMetrics"""
        sql = self.prom_sql()
        data = Collection().query(sql)
        return data.get("data", [])
    
    def run(self):
        """执行采集流程（基类已实现，通常不需要重写）"""
        data = self.query_data()
        self.raw_data = data.get("result", [])
        self.format_data(data)
        self.format_metrics()
        return self.result
```

### 3.4 新增步骤

#### 步骤 1：创建采集任务类

**文件路径**：`apps/cmdb/collect_tasks/middleware.py`（已存在，如需新增类型则创建新文件）

```python
from apps.cmdb.collect_tasks.base import BaseCollect
from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics


class MiddlewareCollect(BaseCollect):
    """中间件采集任务（包括 Tomcat、Nginx 等）"""
    COLLECT_PLUGIN = MiddlewareCollectMetrics
```

#### 步骤 2：在 constants.py 中定义采集指标

**文件路径**：`apps/cmdb/collection/constants.py`

```python
MIDDLEWARE_METRIC_MAP = {
    "nginx": ["nginx_info_gauge"],
    "zookeeper": ["zookeeper_info_gauge"],
    "kafka": ["kafka_info_gauge"],
    "tomcat": ["tomcat_info_gauge"],  # 新增 Tomcat 指标
    # ...
}
```

**说明**：
- 指标名称（如 `tomcat_info_gauge`）必须与 Stargazer 采集脚本中上报的指标名称一致
- 一个对象可以有多个指标（如主机采集有多个关联对象）

#### 步骤 3：创建采集插件类

**文件路径**：`apps/cmdb/collection/collect_plugin/middleware.py`（已存在，在其中添加映射）

```python
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.constants import MIDDLEWARE_METRIC_MAP
import codecs
import json


class MiddlewareCollectMetrics(CollectBase):
    """中间件采集插件"""
    
    @property
    def _metrics(self):
        """从 constants 中获取该对象类型的指标"""
        assert self.model_id in MIDDLEWARE_METRIC_MAP, \
            f"{self.model_id} needs to be defined in MIDDLEWARE_METRIC_MAP"
        return MIDDLEWARE_METRIC_MAP[self.model_id]
    
    def format_data(self, data):
        """
        解析 VM 返回的原始数据
        VM 返回格式：
        {
            "result": [
                {
                    "metric": {
                        "__name__": "tomcat_info_gauge",
                        "instance_id": "cmdb_123",
                        "result": "{...JSON字符串...}",  # Stargazer 采集结果
                        ...
                    },
                    "value": [timestamp, "1"]
                }
            ]
        }
        """
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            _time, value = value[0], value[1]
            
            # 时间戳校验（超过一天的数据不处理）
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True
            
            # 解析 result 字段中的 JSON 数据
            result_data = {}
            if index_data["metric"].get("result", False):
                result_json = index_data["metric"].get("result", "{}")
                if result_json and result_json != "{}":
                    try:
                        # 反转义 JSON 字符串
                        unescaped_json = codecs.decode(result_json, 'unicode_escape')
                        result_data = json.loads(unescaped_json)
                    except Exception:
                        result_data = {}
                if isinstance(result_data, dict) and not result_data:
                    continue
            
            # 合并 metric 元数据和 result 数据
            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
                **result_data,  # Stargazer 采集的实际数据
            )
            
            # 按指标名称分类存储
            self.collection_metrics_dict[metric_name].append(index_dict)
    
    def get_inst_name(self, data):
        """生成实例名称（通常是 IP-对象类型-端口）"""
        return f"{data['ip_addr']}-{self.model_id}-{data['port']}"
    
    @property
    def model_field_mapping(self):
        """
        定义 VM 数据字段到 CMDB 模型字段的映射
        
        映射规则：
        - 字符串：直接取对应字段值
        - 元组：(转换函数, 字段名)
        - 可调用对象（函数）：动态计算值
        """
        mapping = {
            "tomcat": {
                "inst_name": self.get_inst_name,  # 函数：动态生成
                "ip_addr": "ip_addr",              # 字符串：直接映射
                "port": "port",
                "version": "version",
                "install_path": "install_path",
                "conf_path": "conf_path",
                "log_path": "log_path",
                "java_version": "java_version",
                "java_path": "java_path",
                "max_threads": (self.transform_int, "max_threads"),  # 元组：转换函数
                # ...其他字段
            },
            # ...其他中间件类型
        }
        return mapping
    
    @staticmethod
    def transform_int(data):
        """类型转换：转为整数"""
        return int(float(data))
    
    def format_metrics(self):
        """
        将解析后的数据转换为 CMDB 实例格式
        
        处理流程：
        1. 遍历 collection_metrics_dict 中的各个指标数据
        2. 根据 model_field_mapping 进行字段映射
        3. 将结果存入 self.result
        """
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            mapping = self.model_field_mapping.get(self.model_id, {})
            
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    # 元组：(转换函数, 字段名)
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    # 可调用对象：动态计算
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    # 字符串：直接映射
                    else:
                        data[field] = index_data.get(key_or_func, "")
                
                if data:
                    result.append(data)
            
            # 存储到 result 字典
            self.result[self.model_id] = result
```

### 3.5 字段映射高级用法

#### 用法 1：字符串直接映射

```python
"version": "version",  # CMDB字段 "version" = VM数据中的 "version"
```

#### 用法 2：元组（转换函数 + 字段名）

```python
"max_threads": (self.transform_int, "max_threads"),  
# 先从 VM 数据中取 "max_threads"，再用 transform_int() 转为整数
```

#### 用法 3：函数动态计算

```python
"inst_name": self.get_inst_name,  
# 调用 get_inst_name(index_data) 动态生成实例名称

"inst_name": lambda data: f"{data['ip']}-{data['port']}",
# 使用 lambda 表达式
```

#### 用法 4：关联关系映射

```python
# 主机采集中，网卡、磁盘等组件关联到主机
"nic": {
    "inst_name": self.set_component_inst_name,
    "nic_mac": "nic_mac",
    "nic_model": "nic_model",
    self.asso: self.set_asso_instances  # 特殊字段，用于生成关联关系
}

def set_asso_instances(self, data, *args, **kwargs):
    """生成关联关系数据"""
    model_id = kwargs["model_id"]
    return [
        {
            "model_id": self.model_id,  # 源对象类型
            "inst_name": data.get('self_device'),  # 源实例名称
            "asst_id": "contains",  # 关联类型
            "model_asst_id": f"{self.model_id}_contains_{model_id}"  # 关联关系 ID
        }
    ]
```

### 3.6 完整示例：新增 Tomcat 采集

假设 Stargazer 已经实现了 `tomcat_info` 插件，上报指标 `tomcat_info_gauge`，数据格式如下：

```json
{
  "metric": {
    "__name__": "tomcat_info_gauge",
    "instance_id": "cmdb_123",
    "result": "{\"ip_addr\":\"192.168.1.1\",\"port\":\"8080\",\"version\":\"9.0.50\",\"install_path\":\"/opt/tomcat\",\"conf_path\":\"/opt/tomcat/conf\",\"log_path\":\"/opt/tomcat/logs\",\"java_version\":\"1.8.0_291\",\"java_path\":\"/usr/bin/java\",\"max_threads\":\"200\"}"
  },
  "value": [1640000000, "1"]
}
```

#### 步骤 1：在 constants.py 中添加指标

```python
MIDDLEWARE_METRIC_MAP = {
    "nginx": ["nginx_info_gauge"],
    "tomcat": ["tomcat_info_gauge"],  # 新增
}
```

#### 步骤 2：在 middleware.py 中添加字段映射

```python
@property
def model_field_mapping(self):
    mapping = {
        "tomcat": {
            "inst_name": self.get_inst_name,
            "ip_addr": "ip_addr",
            "port": "port",
            "version": "version",
            "install_path": "install_path",
            "conf_path": "conf_path",
            "log_path": "log_path",
            "java_version": "java_version",
            "java_path": "java_path",
            "max_threads": (self.transform_int, "max_threads"),
        },
        # ...其他
    }
    return mapping
```

#### 步骤 3：格式化后的结果

`format_metrics()` 执行后，`self.result` 的内容：

```python
{
    "tomcat": [
        {
            "inst_name": "192.168.1.1-tomcat-8080",
            "ip_addr": "192.168.1.1",
            "port": "8080",
            "version": "9.0.50",
            "install_path": "/opt/tomcat",
            "conf_path": "/opt/tomcat/conf",
            "log_path": "/opt/tomcat/logs",
            "java_version": "1.8.0_291",
            "java_path": "/usr/bin/java",
            "max_threads": 200
        }
    ]
}
```

---

## 第四部分：完整流程示例（Tomcat）

### 4.1 目录结构与文件清单

```
apps/cmdb/
├── constants/
│   └── constants.py  # 步骤 0：在 COLLECT_OBJ_TREE 中注册（**必须先做**）
├── node_configs/
│   └── ssh/
│       └── tomcat.py  # 步骤 1：节点配置
├── collection/
│   ├── constants.py  # 步骤 2：定义指标
│   └── collect_plugin/
│       └── middleware.py  # 步骤 3：添加字段映射
└── collect_tasks/
    └── middleware.py  # 已存在，无需修改
```

### 4.2 步骤 0：在 COLLECT_OBJ_TREE 中注册（**必须先做**）

**文件**：`apps/cmdb/constants/constants.py`

在 `COLLECT_OBJ_TREE` 中添加 Tomcat：

```python
COLLECT_OBJ_TREE = [
    # ...
    {
        "id": "middleware",
        "name": "中间件",
        "children": [
            {"id": "nginx", "model_id": "nginx", "name": "Nginx", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB, "tag": ["JOB", "Linux"], "desc": "发现与采集Nginx基础配置信息",
             "encrypted_fields": ["password"]},
            # 新增 Tomcat
            {"id": "tomcat", "model_id": "tomcat", "name": "Tomcat", "task_type": CollectPluginTypes.MIDDLEWARE,
             "type": CollectDriverTypes.JOB, "tag": ["JOB", "Linux"], "desc": "发现与采集Tomcat基础配置信息",
             "encrypted_fields": ["password"]},
            # ...
        ],
    }
]
```

**关键点**：
- `model_id` 必须与后续步骤中的 `supported_model_id` 保持一致
- `encrypted_fields` 列出需要加密的凭据字段（前端会加密处理）

### 4.3 步骤 1：创建节点配置类

**文件**：`apps/cmdb/node_configs/ssh/tomcat.py`

```python
# -- coding: utf-8 --
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class TomcatNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    """Tomcat 采集节点配置"""
    supported_model_id = "tomcat"
    plugin_name = "tomcat_info"
    interval = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_field = "ip_addr"
```

### 4.4 步骤 2：定义采集指标

**文件**：`apps/cmdb/collection/constants.py`

```python
MIDDLEWARE_METRIC_MAP = {
    "nginx": ["nginx_info_gauge"],
    "tomcat": ["tomcat_info_gauge"],  # 新增
    # ...
}
```

### 4.5 步骤 3：添加字段映射

**文件**：`apps/cmdb/collection/collect_plugin/middleware.py`

在 `model_field_mapping` 属性中添加：

```python
@property
def model_field_mapping(self):
    mapping = {
        "tomcat": {
            "inst_name": self.get_inst_name,
            "ip_addr": "ip_addr",
            "port": "port",
            "version": "version",
            "install_path": "install_path",
            "conf_path": "conf_path",
            "log_path": "log_path",
            "java_version": "java_version",
            "java_path": "java_path",
            "max_threads": (self.transform_int, "max_threads"),
        },
        # ...其他中间件
    }
    return mapping
```

### 4.6 完成！

现在可以：
1. 在 CMDB 前端创建 Tomcat 采集任务（前端会从 `COLLECT_OBJ_TREE` 中读取配置）
2. 系统自动推送配置到节点管理
3. 定时任务执行采集并同步到 CMDB

---

## 第五部分：高级场景

### 5.1 多对象采集（如主机 + 组件）

某些采集任务会同时采集主机和其关联的组件（网卡、磁盘等），需要：

#### 1. 在 constants.py 中定义多个指标

```python
HOST_COLLECT_METRIC = {
    "physcial_server": [
        "physcial_server_info_gauge",  # 主机信息
        "disk_info_gauge",              # 磁盘组件
        "memory_info_gauge",            # 内存组件
        "nic_info_gauge",               # 网卡组件
        "gpu_info_gauge"                # GPU组件
    ],
}
```

#### 2. 在字段映射中定义多个对象

```python
@property
def model_field_mapping(self):
    mapping = {
        "physcial_server": {
            "inst_name": self.set_inst_name,
            "serial_number": "serial_number",
            "cpu_model": "cpu_model",
            # ...
        },
        "nic": {
            "inst_name": self.set_component_inst_name,
            "nic_mac": "nic_mac",
            "nic_model": "nic_model",
            self.asso: self.set_asso_instances,  # 关联到主机
        },
        # ...其他组件
    }
    return mapping
```

#### 3. 格式化时处理关联关系

```python
def format_metrics(self):
    for metric_key, metrics in self.collection_metrics_dict.items():
        # 根据指标名称确定对象类型
        if metric_key == "disk_info_gauge":
            model_id = "disk"
        elif metric_key == "nic_info_gauge":
            model_id = "nic"
        else:
            model_id = self.model_id
        
        result = []
        mapping = self.model_field_mapping.get(model_id, {})
        
        for index_data in metrics:
            data = {"model_id": model_id}  # 添加 model_id 字段
            assos_result = {}
            
            for field, key_or_func in mapping.items():
                # 处理关联关系
                if field == self.asso:
                    assos_result = key_or_func(index_data, model_id=model_id)
                    continue
                
                # 处理普通字段
                if isinstance(key_or_func, tuple):
                    data[field] = key_or_func[0](index_data[key_or_func[1]])
                elif callable(key_or_func):
                    data[field] = key_or_func(index_data, model_id=model_id)
                else:
                    data[field] = index_data.get(key_or_func, "")
            
            if data:
                data["assos_result"] = assos_result  # 添加关联关系
                result.append(data)
        
        # 存储到 result（按 model_id 分类）
        if model_id not in self.result:
            self.result[model_id] = []
        self.result[model_id].extend(result)
```

### 5.2 云厂商采集（阿里云、腾讯云、AWS）

云厂商采集通常不需要 SSH 凭据，而是使用 AccessKey/SecretKey。

#### 示例：阿里云 ECS 采集

**节点配置**：`apps/cmdb/node_configs/cloud/aliyun.py`

```python
from apps.cmdb.node_configs.base import BaseNodeParams


class AliyunNodeParams(BaseNodeParams):
    supported_model_id = "aliyun_account"
    plugin_name = "aliyun_info"
    interval = 600  # 云资源采集间隔可以更长
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "protocol"  # 使用 protocol 执行器
    
    def set_credential(self, *args, **kwargs):
        """阿里云 API 凭据"""
        _secret = f"PASSWORD_secret_{self._instance_id}"
        return {
            "access_key": self.credential.get("access_key", ""),
            "secret_key": "${" + _secret + "}",
            "region": self.credential.get("region", "cn-hangzhou"),
        }
    
    def env_config(self, *args, **kwargs):
        """Secret Key 通过环境变量传递"""
        _secret = f"PASSWORD_secret_{self._instance_id}"
        return {_secret: self.credential.get("secret_key", "")}
```

**采集插件**：`apps/cmdb/collection/collect_plugin/aliyun.py`

```python
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.constants import ALIYUN_COLLECT_CLUSTER


class AliyunCollectMetrics(CollectBase):
    @property
    def _metrics(self):
        return ALIYUN_COLLECT_CLUSTER  # 多个云资源类型
    
    def format_data(self, data):
        # 解析阿里云 API 返回的数据
        # ...
    
    @property
    def model_field_mapping(self):
        return {
            "aliyun_ecs": {
                "inst_name": "instance_id",
                "instance_id": "instance_id",
                "instance_name": "instance_name",
                "region": "region",
                "zone": "zone",
                "cpu": "cpu",
                "memory": "memory",
                # ...
            },
            # ...其他云资源类型
        }
    
    def format_metrics(self):
        # 根据不同的指标名称，映射到不同的对象类型
        # ...
```

---

## 第六部分：常见问题与调试

### Q1：新增的配置类没有生效？

**检查清单**：
1. 确认 `supported_model_id` 和 `plugin_name` 已正确设置
2. 确认文件位于 `node_configs` 目录下的某个子目录（会被自动扫描）
3. 重启 Django 服务（模块导入在启动时执行）
4. 检查日志中是否有注册警告

**调试方法**：
```python
# 在 Django Shell 中检查注册情况
from apps.cmdb.node_configs.base import BaseNodeParams

print(BaseNodeParams._registry)  # 查看已注册的类
print(BaseNodeParams.PLUGIN_MAP)  # 查看插件映射
```

### Q2：推送到节点管理失败？

**常见原因**：
1. 节点管理服务不可达（检查 RPC 配置）
2. 凭据格式错误（检查 `set_credential()` 返回值）
3. 模板渲染失败（检查 Headers 参数格式）

**调试方法**：
```python
# 在 collect_service.py 中添加日志
logger.debug(f"推送节点参数: {node_params}")
logger.debug(f"推送节点参数结果: {result}")
```

### Q3：采集数据为空？

**检查清单**：
1. Stargazer 是否正常上报数据到 VM？（检查 VM 数据源）
2. `_metrics` 中的指标名称是否与 Stargazer 上报的一致？
3. `instance_id` 是否匹配？（`prom_sql()` 会用 `instance_id` 过滤）

**调试方法**：
```python
# 直接查询 VM
from apps.cmdb.collection.query_vm import Collection

sql = "tomcat_info_gauge{instance_id=cmdb_123}"
data = Collection().query(sql)
print(data)  # 检查是否有数据返回
```

### Q4：字段映射后数据不正确？

**检查清单**：
1. `format_data()` 是否正确解析了 `result` 字段？
2. `model_field_mapping` 中的字段名是否与 VM 数据中的一致？
3. 类型转换函数是否正确？（如 `transform_int`）

**调试方法**：
```python
# 在 format_data() 中打印原始数据
logger.debug(f"原始数据: {index_data}")
logger.debug(f"解析后数据: {result_data}")

# 在 format_metrics() 中打印映射结果
logger.debug(f"映射后数据: {data}")
```

### Q5：如何支持多凭据？

**回答**：当前架构中，每个采集任务实例对应一个凭据配置。如果需要支持多凭据（如一个任务采集多个主机，每个主机有不同的密码），需要：

1. 在 `CollectModels.instances` 中为每个实例存储独立的凭据
2. 在 `set_credential()` 中遍历所有实例，生成多组凭据配置
3. 在推送时生成多个节点管理配置（每个实例一个配置）

---

## 第七部分：最佳实践

### 1. 命名规范

| 名称 | 规范 | 示例 |
|------|------|------|
| model_id | 小写蛇形 | `tomcat`, `mysql`, `aliyun_ecs` |
| plugin_name | 小写蛇形 + `_info` 后缀 | `tomcat_info`, `mysql_info` |
| 指标名称 | 小写蛇形 + `_gauge` 后缀 | `tomcat_info_gauge` |
| 类名 | 大驼峰 + 功能后缀 | `TomcatNodeParams`, `MiddlewareCollectMetrics` |

### 2. 复用现有模块

- SSH 类型采集：继承 `SSHNodeParamsMixin`
- 数据库类型采集：参考 `databases.py`，复用 `DBCollectCollectMetrics`
- 中间件类型采集：参考 `middleware.py`，复用 `MiddlewareCollectMetrics`

### 3. 字段映射设计

- 优先使用字符串直接映射（性能最好）
- 需要类型转换时使用元组
- 复杂逻辑使用独立方法（便于测试）

### 4. 错误处理

- 在 `format_data()` 中捕获 JSON 解析异常
- 在 `format_metrics()` 中校验必填字段
- 在 `set_credential()` 中提供默认值

### 5. 性能优化

- 采集间隔根据资源类型合理设置（主机 300s，云资源 600s）
- 避免在 `format_metrics()` 中进行耗时操作
- 使用批量查询（`prom_sql()` 支持 `or` 连接多个指标）

---

## 附录：核心类继承关系

```
BaseNodeParams (metaclass=ABCMeta)
  ├─ SSHNodeParamsMixin (Mixin)
  │   ├─ HostNodeParams
  │   ├─ TomcatNodeParams
  │   └─ RedisNodeParams
  ├─ MysqlNodeParams (数据库类型，不使用 Mixin)
  ├─ AliyunNodeParams (云厂商类型)
  └─ NetworkNodeParams (网络设备)

BaseCollect
  ├─ HostCollect
  ├─ DBCollect
  ├─ MiddlewareCollect
  ├─ K8sCollect
  ├─ AliyunCollect
  └─ VmwareCollect

CollectBase (metaclass=ABCMeta)
  ├─ HostCollectMetrics
  ├─ DBCollectCollectMetrics
  ├─ MiddlewareCollectMetrics
  ├─ K8sCollectMetrics
  ├─ AliyunCollectMetrics
  └─ VmwareCollectMetrics
```

---

## 总结

新增一个配置采集对象插件需要**四个步骤**（按顺序执行）：

**步骤 0（必须先做）**：在 `apps/cmdb/constants/constants.py` 的 `COLLECT_OBJ_TREE` 中注册采集对象
- 设置 `model_id`、`task_type`、`type` 等字段
- 配置 `encrypted_fields` 列出需要加密的凭据字段
- **前端依赖此配置展示采集对象列表**

**步骤 1**：在 `node_configs` 中创建节点配置类
- 设置 `supported_model_id`（必须与步骤 0 的 `model_id` 一致）和 `plugin_name`
- 实现 `set_credential()` 方法（或继承 `SSHNodeParamsMixin`）

**步骤 2**：在 `apps/cmdb/collection/constants.py` 中定义采集指标
- 在对应的指标映射字典中添加 `model_id` 和指标列表
- 指标名称必须与 Stargazer 上报的一致

**步骤 3**：在 `collection/collect_plugin` 中添加字段映射
- 在 `model_field_mapping` 中添加字段映射规则

**关键点**：
- **COLLECT_OBJ_TREE 注册是必须的第一步**，否则前端无法创建采集任务
- `model_id` 在所有步骤中必须保持一致
- 自动注册机制无需手动注册类
- 字段映射支持字符串、元组、函数三种方式
- 关联关系通过特殊字段 `self.asso` 处理
- 敏感信息通过环境变量传递

**参考示例**：
- SSH 类型：`host.py`, `redis.py`, `tomcat.py`
- 数据库类型：`mysql.py`, `databases.py`
- 云厂商类型：`aliyun.py`, `qcloud.py`, `aws.py`
