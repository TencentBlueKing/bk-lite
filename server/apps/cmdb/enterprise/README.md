# CMDB 企业版代码分层规范（v2）

## 目标与不变式

`apps/cmdb/enterprise` 是 CMDB 商业版能力的**唯一代码区域**，且必须是 cmdb app 内的普通包（不是独立 Django app）。

设计目标：

- 社区版只定义**扩展契约**与极少数**发现接缝**
- 企业版只提供**增量实现**，且**含自有的模型/任务/调度/配置**
- 删除 `apps/cmdb/enterprise` 后，CMDB **行为**自动回退到社区版

**不变式（诚实声明其边界）**：

- **行为、字段类型、任务代码、调度内容、配置注册** —— 全部随 `enterprise/` 一起消失（真 add-only）。
- **有状态能力的表结构是社区基础设施**：企业能力需要的 DB 模型与迁移**正常放社区** `apps/cmdb/models/` 与 `apps/cmdb/migrations/`（与 `config_file_version.py` 同列），不放 enterprise。原因：enterprise 非独立 app，把模型放其中会让表结构与迁移结构错乱（注册依赖惰性导入、makemigrations 不可靠）。社区只持有这些表的 **schema**，企业版独占其**读写行为**；删除 enterprise 后表闲置但无害。**schema 是社区脚手架，行为是 add-only**。

禁止：隐式覆盖、同名替换、monkey patch 替换社区主流程。

---

## 两层结构

```text
apps/cmdb/                              # 社区版
  extensions/loader.py                  #   共享 load_provider（缺 provider→默认；provider 破损→报错）
  model_ops/extensions.py               #   ModelEnterpriseExtension  + get_model_enterprise_extension()
  instance_ops/extensions.py            #   InstanceEnterpriseExtension + get_instance_enterprise_extension()
  collect/extensions.py                 #   CollectEnterpriseExtension + get_collect_enterprise_extension()

  models/                               #   有状态能力的表结构（社区基础设施，正常归属 cmdb）
  migrations/                           #   表迁移（社区，正常归属 cmdb）
  tasks/__init__.py                     #   接缝①：guarded 导入 enterprise 任务
  config.py                             #   接缝②：guarded 合并 enterprise beat
  apps.py  (AppConfig.ready)            #   接缝③：guarded 调用 enterprise bootstrap（配置/采集注册）

  enterprise/                           # 企业版：唯一行为代码区，删掉即回退
    bootstrap.py                        #   install()：注册桶等运行时配置 + 采集注册编排
    beat.py                             #   ENTERPRISE_BEAT_SCHEDULE
    tasks/                              #   企业 @shared_task
    model_ops/provider.py               #   字段类型规则等
    instance_ops/{provider,service,storage,constants}.py
    collect/{provider,tree,dameng}.py   #   采集域（达梦在此）
```

社区业务代码**只能依赖域门面**（`apps.cmdb.<domain>.extensions`），不得直接 import 更深的 enterprise 模块。

---

## 发现接缝（唯一允许的 community→enterprise 导入）

普通业务代码**禁止** `import apps.cmdb.enterprise.xxx`。允许的 community→enterprise 导入只有以下**四处**，且全部 guarded（`try/except ModuleNotFoundError`）或经 loader 回退：

| # | 位置 | 作用 | 缺失 enterprise 时 |
|---|---|---|---|
| 域 loader | `extensions/loader.py` | 加载 `enterprise.<domain>.provider` | 回退空契约 |
| ① | `tasks/__init__.py` | 导入 `enterprise.tasks` 使 Celery 发现 | 静默跳过，任务不注册 |
| ② | `config.py` | 合并 `enterprise.beat.ENTERPRISE_BEAT_SCHEDULE` | 合并 no-op |
| ③ | `apps.py:ready()` | 调 `enterprise.bootstrap.install()` | 静默跳过 |

> 为什么需要 ①②③：enterprise 不是独立 app，无法靠「per-app 自动发现」注册任务/beat/配置，故由 cmdb app 在这三个标准聚合点做 guarded 转接。每处都是固定接缝，**不是**散落的动态导入。
> 注意**模型不在此列**：有状态能力的表正常定义在社区 `apps/cmdb/models/`、迁移在 `apps/cmdb/migrations/`，企业 provider 直接 import 这些社区模型即可（社区 import 社区，无需接缝）。新增企业需求**不得**再增加新的 community→enterprise 接缝。

---

## 各场景接入范式

### 1. 行为扩展（读路径 / 写路径 / 生命周期）

在对应域契约上加方法，社区在固定 seam 调用：

- 读路径增强：`extend_*(request, payload) -> payload`
- 写路径校验/规范化：`validate_*` / `normalize_*(...) -> data`
- 生命周期回调：`commit_*` / `on_*_create|update|delete(...)`

社区默认实现为 no-op / 原样返回。

### 2. 新字段类型

`ModelEnterpriseExtension.file_attr_types() -> set` 声明类型；`validate_attr(attr)` 落建模规则。社区用 `is_file_attr_type()` 识别，缺 enterprise 时恒空集 → 所有相关分支 inert。

### 3. 新接口 / 动作

URL 留在社区瘦 viewset，**仅委托**域契约的 `handle_*`；社区默认 `handle_*` 抛「未启用」。不在 enterprise 放 `urls.py`（否则会被 URL 自动发现挂成独立命名空间）。

### 4. 持久化（模型 / 迁移）

- 模型类**正常放社区** `apps/cmdb/models/*.py`，在 `models/__init__.py` 直接 import（与 `config_file_version.py` 同列）。
- 迁移文件正常落 `apps/cmdb/migrations/`。**不要**把模型放进 `enterprise/`——否则表结构与迁移结构会错乱。
- 企业 provider/service 直接 `from apps.cmdb.models.xxx import ...`（社区 import 社区，合法）。
- 表只被 enterprise 行为写入；社区从不主动读写企业表（schema 是社区脚手架，行为是 add-only）。

### 5. 异步任务

`@shared_task` 放 `enterprise/tasks/*.py`；接缝②使其被 Celery 发现。

### 6. 周期调度（beat）

beat 字典放 `enterprise/beat.py` 的 `ENTERPRISE_BEAT_SCHEDULE`；接缝③在 `cmdb/config.py` guarded 合并。任务未注册时 beat 会忽略，安全。

### 7. 运行时配置

企业专属 settings（如 MinIO 桶）在 `enterprise/bootstrap.py:install()` 里运行时注册（如向 `settings.MINIO_PRIVATE_BUCKETS` 追加），由接缝③触发。不改社区 `config/components/*`。

### 8. 采集注册（采集树 / 插件 / NodeParams）

经 `CollectEnterpriseExtension` 暴露 `collect_tree / plugin_packages / node_param_packages`；社区 `collect_object_tree.py`、`plugins/loader.py`、`node_configs` 统一从该门面取，不再硬编码 `apps.cmdb.enterprise`。

### 9. 规则守卫集合（不硬编码企业类型名）

社区的「不支持类型」集合（联合唯一、自动关联）通过契约方法合并企业增量：
`unsupported_unique_attr_types()` / `unsupported_auto_relation_attr_types()`。社区集合里**不出现** `attachment/image` 等企业类型名，缺 enterprise 时合并为空。

---

## 契约方法清单（当前）

```python
class ModelEnterpriseExtension:        # apps/cmdb/model_ops/extensions.py
    file_attr_types() -> set
    validate_attr(attr) -> attr
    unsupported_unique_attr_types() -> set
    unsupported_auto_relation_attr_types() -> set

class InstanceEnterpriseExtension:     # apps/cmdb/instance_ops/extensions.py
    normalize_file_fields(model_id, data, attrs, *, operator, old_instance=None) -> data
    commit_instance_files(model_id, inst_id, saved, attrs, *, operator)
    on_instance_delete(model_id, inst_id, instance)
    handle_upload(*, request, model_id, attr_id, uploaded_file) -> meta
    handle_download(*, request, file_id, check_read_permission=None) -> url
    handle_delete_temp(*, request, file_id)

class CollectEnterpriseExtension:      # apps/cmdb/collect/extensions.py
    collect_tree: list
    plugin_packages: tuple[str, ...]
    node_param_packages: tuple[str, ...]
```

---

## 错误处理

- **provider 模块/父包不存在** → 正常回退空契约。
- **provider 存在但不符契约（缺方法）** → 显式 `AttributeError`，统一日志暴露，绝不静默。

CMDB 可以没有企业版，但不能悄悄接受损坏的企业版实现。

---

## 后续商业需求接入流程

1. 判断归属能力域：`model_ops` / `instance_ops` / `collect`，或属平台场景（持久化/任务/调度/配置）。
2. 能力域行为：契约已够 → 只在 `enterprise/<domain>/` 补实现；契约不足 → 先在社区 `<domain>/extensions.py` 加显式契约方法，再由 provider 实现。
3. 平台场景：行为放进 `enterprise/{tasks,beat,bootstrap}` 复用既有三个接缝；需要建表则把模型/迁移正常放社区 `apps/cmdb/{models,migrations}`。**不得新增新的 community→enterprise 接缝**。

---

## 历史实现收敛

达梦数据库（原 `enterprise/tree.py` + `enterprise/db/dameng.py`）已收敛到 `enterprise/collect/`，经 `collect` 域门面编排，社区三处采集钩子不再直接 import enterprise。
