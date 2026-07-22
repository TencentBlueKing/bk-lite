# 系统管理-许可管理 Tech Plan（2026-04-08）

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/archive/2026-04-17-license-mgmt/tech_plan.md`。完整内容保留如下。

需求文档：[spec/requirements/系统管理/20260407.许可管理.md](spec/requirements/系统管理/20260407.许可管理.md)
方案文档：[spec/solution_plan/系统管理/20260407.许可管理.md](spec/solution_plan/系统管理/20260407.许可管理.md)

技术目标：在不污染社区版 `system_mgmt` 模型与 migration 链的前提下，以企业版独立 app `license_mgmt` 落地许可管理能力，完成许可主数据、默认提醒、单许可提醒、节点提醒、日志容量提醒、注册码读取与跨模块新增资源校验的完整闭环。

非目标：不改造社区版仓库结构、不将许可数据回写到 `system_mgmt.SystemSettings`、不实现自动续期/自动扩容/商业化流程、不建设统一容量中心、不在第一版引入复杂 M2M 关系或跨模块强事务联动。

影响范围：

- 后端企业版：`server/apps/license_mgmt`
- 后端公共接入：`server/apps/system_mgmt` 菜单权限初始化、跨模块新增资源校验中间件接入点、`apps.rpc` RPC 调用封装
- 前端企业版：`web/src/app/system-manager/enterprise`
- 前端公共接入：`web/src/app/system-manager/constants/menu.json`、`web/src/app/system-manager/(pages)/settings/page.tsx`

---

## 1. 文件与目录结构

```text
spec/
└─ tech_plan/
   └─ 系统管理/
      └─ 20260408.许可管理.md                                               (A)

server/
└─ apps/
   ├─ license_mgmt/                                                        (A, enterprise only)
   │  ├─ __init__.py                                                       (A)
   │  ├─ apps.py                                                           (A)
   │  ├─ urls.py                                                           (A)
   │  ├─ nats_api.py                                                       (A)
   │  ├─ constants/
   │  │  └─ enums.py                                                       (A)
   │  ├─ config.py                                                         (A)
   │  ├─ registration_code.py                                               (A, deployed runtime value)
   │  ├─ models/
   │  │  ├─ __init__.py                                                    (A)
   │  │  ├─ license.py                                                     (A)
   │  │  └─ reminder.py                                                    (A)
   │  ├─ serializers/
   │  │  ├─ __init__.py                                                    (A)
   │  │  ├─ license_serializer.py                                          (A)
   │  │  └─ reminder_serializer.py                                         (A)
   │  ├─ services/
   │  │  ├─ __init__.py                                                    (A)
   │  │  ├─ license_service.py                                             (A)
   │  │  ├─ license_decode_service.py                                      (A)
   │  │  ├─ reminder_service.py                                            (A)
   │  │  ├─ registration_code_service.py                                   (A)
   │  │  └─ permission_guard_service.py                                    (A)
   │  ├─ viewset/
   │  │  ├─ __init__.py                                                    (A)
   │  │  ├─ license_viewset.py                                             (A)
   │  │  └─ reminder_viewset.py                                            (A)
   │  ├─ middleware/
   │  │  └─ license_guard.py                                               (A)
   │  └─ migrations/
   │     └─ 0001_initial.py                                                (A)
   ├─ system_mgmt/
   │  ├─ models/menu.py                                                    (M)
   │  ├─ nats_api.py                                                       (M, menu/permission init if needed)
   │  └─ viewset/channel_viewset.py                                        (R)
   └─ rpc/
      └─ license_mgmt.py                                                   (A)

web/
└─ src/app/system-manager/
   ├─ constants/
   │  └─ menu.json                                                         (M)
   └─ (pages)/settings/
      └─ page.tsx                                                          (M)

web/
└─ src/app/system-manager/enterprise/
   ├─ api/
   │  └─ license_mgmt/
   │     └─ index.ts                                                       (A)
   ├─ types/
   │  └─ license.ts                                                        (A)
   └─ (pages)/settings/license/
      ├─ page.tsx                                                          (A)
      └─ components/
         ├─ licenseList.tsx                                                (A)
         ├─ globalReminderPanel.tsx                                        (A)
         ├─ licenseReminderModal.tsx                                       (A)
         ├─ moduleSummary.tsx                                              (A)
         ├─ nodeReminderModal.tsx                                          (A)
         └─ logMemoryReminderModal.tsx                                     (A)
```

说明：

- `license_mgmt` 仅存在于企业版代码中，社区版仓库不注册、不提交该 app。
- 前端入口仍属于 `system-manager` 信息架构，不新增顶层产品入口。
- 许可管理前端真实实现位于 `web/src/app/system-manager/enterprise/...`，社区版不提交许可页面业务代码。
- 菜单权限仍接入 `system_mgmt`，但许可业务实现不进入 `system_mgmt` 主模型和主 migration。
 - `server/apps/license_mgmt/config.py` 中的大写配置项会通过 `server/config/components/extra.py` 自动合并到 `django.conf.settings`。
 - `server/apps/license_mgmt/registration_code.py` 为运行期注册码来源，不作为数据库配置来源。

---

## 2. 核心数据结构 / Schema 定义

### 2.1 Python Dataclasses

```python
from dataclasses import dataclass, field
from typing import Literal

LicenseStatus = Literal["active", "disabled", "expired"]
ReminderMode = Literal["follow", "custom"]
ReminderType = Literal["node", "log_memory"]


@dataclass(slots=True, frozen=True)
class LicenseRecordPayload:
    license_no: str
    license_key: str
    valid_from: str
    valid_until: str
    module_codes: list[str]


@dataclass(slots=True, frozen=True)
class LicenseGlobalReminderPayload:
    default_channel_ids: list[int]
    default_user_ids: list[int]
    default_remind_days: int


@dataclass(slots=True, frozen=True)
class LicenseReminderOverridePayload:
    license_id: int
    mode: ReminderMode
    channel_ids: list[int] = field(default_factory=list)
    user_ids: list[int] = field(default_factory=list)
    remind_days: int | None = None


@dataclass(slots=True, frozen=True)
class ModuleReminderPayload:
    module_code: str
    reminder_type: ReminderType
    mode: ReminderMode
    threshold_value: int | None = None
    channel_ids: list[int] = field(default_factory=list)
    user_ids: list[int] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class NodeReminderOverridePayload:
    module_code: str
    object_type: str
    threshold_value: int
    channel_ids: list[int]
    user_ids: list[int]


@dataclass(slots=True, frozen=True)
class LicenseAccessCheckResult:
    allowed: bool
    reason: str = ""
    module_code: str = ""
```

### 2.2 Django Model 结构建议

```python
# server/apps/license_mgmt/models/license.py
class LicenseRecord(models.Model):
    license_no = models.CharField(max_length=128, unique=True)
    license_key = models.TextField()
    registration_code_snapshot = models.CharField(max_length=255, blank=True, default="")
    valid_from = models.DateField()
    valid_until = models.DateField()
    status = models.CharField(max_length=32, db_index=True)
    disabled_reason = models.CharField(max_length=255, blank=True, default="")
    disabled_at = models.DateTimeField(null=True, blank=True)
    module_codes = models.JSONField(default=list)
    created_by = models.CharField(max_length=64, blank=True, default="")
    updated_by = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# server/apps/license_mgmt/models/reminder.py
class LicenseGlobalReminderConfig(models.Model):
    default_channel_ids = models.JSONField(default=list)
    default_user_ids = models.JSONField(default=list)
    default_remind_days = models.PositiveIntegerField(default=30)
    updated_by = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class LicenseReminderOverride(models.Model):
    license = models.OneToOneField("license_mgmt.LicenseRecord", on_delete=models.CASCADE)
    mode = models.CharField(max_length=32, default="follow")
    channel_ids = models.JSONField(default=list)
    user_ids = models.JSONField(default=list)
    remind_days = models.PositiveIntegerField(null=True, blank=True)
    updated_by = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class ModuleReminderConfig(models.Model):
    module_code = models.CharField(max_length=64)
    reminder_type = models.CharField(max_length=32)
    mode = models.CharField(max_length=32, default="follow")
    threshold_value = models.PositiveIntegerField(null=True, blank=True)
    channel_ids = models.JSONField(default=list)
    user_ids = models.JSONField(default=list)
    updated_by = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("module_code", "reminder_type"),)


class NodeReminderOverride(models.Model):
    module_code = models.CharField(max_length=64)
    object_type = models.CharField(max_length=128)
    threshold_value = models.PositiveIntegerField()
    channel_ids = models.JSONField(default=list)
    user_ids = models.JSONField(default=list)
    updated_by = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("module_code", "object_type"),)
```

规则口径：

- `LicenseRecord.status` 负责区分当前许可与历史许可，不单独建历史表。
- `module_codes` 使用 `JSONField`，第一版不拆 `LicenseModule` 子表。
- 通知人员统一存用户 ID，不存 username 快照。
- 通知渠道统一存 channel ID。
- `LicenseGlobalReminderConfig` 为独立表，不复用 `SystemSettings`。

### 2.3 注册码来源

注册码不落库，运行时统一从模块文件读取。

技术口径：

- 注册码固定定义在 `server/apps/license_mgmt/registration_code.py`。
- 文件内容为模块级变量：`registration_code = "..."`。
- 开发环境可使用占位值，部署环境通过覆盖该文件提供真实注册码。
- 页面通过服务端接口读取注册码展示值，不直接暴露实现细节。
- `.lic` 文件内容的外层解密统一使用该注册码。

### 2.4 许可码解析 / 验签结构

根据现有“效验解析规则”，许可码采用签名载荷结构。

```python
@dataclass(slots=True, frozen=True)
class LicenseDecodedPayload:
    v: int
    pid: str
    reg: str
    con: dict
    iat: int
    nbf: int | None = None
    exp: int | None = None
    kv: int | None = None
    sig: str = ""
```

技术口径：

- 激活码结构：`base64url(JSON({...payload, sig}))`
- 验签对象：去掉 `sig` 后，对 payload 做递归 key 排序的 canonical JSON
- 签名算法：`Ed25519`
- 公钥统一通过 settings 提供，固定采用 `LICENSE_PUBLIC_KEYS = {1: "<base64_public_key>", 2: "<base64_public_key>"}` 的字典结构
- 当许可 payload 未携带 `kv` 时，使用 `settings.LICENSE_DEFAULT_PUBLIC_KEY_VERSION` 作为缺省公钥版本
- `LICENSE_PUBLIC_KEYS` 的 value 第一版固定为 Base64 编码的 Ed25519 公钥字符串，`license_decode_service` 在运行时完成解码
- 公钥轮换策略采用“新增版本、不覆盖旧版本”的方式：先在 settings 中追加新 `kv`，发码端开始签发新 `kv` 许可，待旧许可自然淘汰后再移除旧公钥
- 验签通过后，继续校验 `nbf <= now <= exp`
- `payload.reg` 必须与系统注册码明文一致
- `payload.con` 为许可能力与额度的真实来源，后续映射为模块授权、节点额度、日志容量等运行时配置

---

## 3. 核心函数 / 接口签名

```python
# server/apps/license_mgmt/services/registration_code_service.py
class RegistrationCodeService:
    @classmethod
    def ensure_code_file(cls) -> str:
        """兼容旧调用名，当前直接返回注册码。"""

    @classmethod
    def get_registration_code(cls) -> str:
        """从 registration_code.py 读取注册码并返回明文。"""
```

```python
# server/apps/license_mgmt/services/license_decode_service.py
class LicenseDecodeService:
    @classmethod
    def decode_activation_code(cls, activation_code: str) -> dict:
        """若传入 .lic 字符串则先做外层解密，再解析 activationCode。"""

    @classmethod
    def canonicalize(cls, payload: dict) -> str:
        """递归排序 key，生成 canonical JSON。"""

    @classmethod
    def verify_license(cls, activation_code: str) -> LicenseDecodedPayload:
        """完成解码、验签、时间窗口校验，并返回 payload。"""

    @classmethod
    def get_public_key_by_kv(cls, kv: int | None):
        """从 settings 中加载当前 kv 对应的 Ed25519 公钥。"""

    @classmethod
    def assert_registration_code_match(cls, payload: LicenseDecodedPayload, registration_code: str) -> None:
        """校验 payload.reg 与系统注册码一致。"""

    @classmethod
    def normalize_module_codes(cls, payload: LicenseDecodedPayload) -> list[str]:
        """从 payload.con 提取可落库的模块 code 列表。"""
```

```python
# server/apps/license_mgmt/services/license_service.py
class LicenseService:
    @classmethod
    def list_active_licenses(cls) -> list[dict]:
        """返回生效许可列表。"""

    @classmethod
    def list_history_licenses(cls) -> list[dict]:
        """返回历史许可列表。"""

    @classmethod
    def add_license(cls, *, license_key: str, operator: str) -> LicenseRecord:
        """添加许可并完成解码、验签、注册码校验、模块解析与持久化。"""

    @classmethod
    def disable_license(cls, *, license_id: int, operator: str, reason: str = "") -> LicenseRecord:
        """停用许可，仅修改状态，不直接删除数据。"""

    @classmethod
    def get_module_summary(cls) -> dict:
        """返回免激活 / 已激活 / 未激活模块摘要。"""

    @classmethod
    def is_module_allowed_for_create(cls, module_code: str) -> LicenseAccessCheckResult:
        """判断指定模块当前是否允许新增资源。"""
```

```python
# server/apps/license_mgmt/services/reminder_service.py
class ReminderService:
    @classmethod
    def get_global_reminder(cls) -> dict:
        """返回全局默认提醒配置。"""

    @classmethod
    def save_global_reminder(cls, payload: LicenseGlobalReminderPayload, operator: str) -> dict:
        """保存全局默认提醒配置。"""

    @classmethod
    def get_license_reminder(cls, license_id: int) -> dict:
        """返回单许可提醒配置与跟随摘要。"""

    @classmethod
    def save_license_reminder(cls, payload: LicenseReminderOverridePayload, operator: str) -> dict:
        """保存单许可提醒配置。"""

    @classmethod
    def get_node_reminder_config(cls, module_code: str) -> dict:
        """返回节点提醒配置、默认摘要和专用节点覆盖列表。"""

    @classmethod
    def save_node_reminder_config(cls, module_code: str, payload: dict, operator: str) -> dict:
        """保存节点提醒配置。"""

    @classmethod
    def get_log_memory_reminder_config(cls) -> dict:
        """返回日志容量提醒配置。"""

    @classmethod
    def save_log_memory_reminder_config(cls, payload: ModuleReminderPayload, operator: str) -> dict:
        """保存日志容量提醒配置。"""
```

```python
# server/apps/license_mgmt/nats_api.py
LICENSE_MGMT_ENABLED = getattr(settings, "LICENSE_MGMT_ENABLED", False)


def get_registration_code():
    """NATS 暴露：返回注册码展示值。"""


def validate_module_create_access(module_code: str):
    """NATS 暴露：返回模块是否允许新增资源。"""
```

```python
# server/apps/rpc/license_mgmt.py
class LicenseMgmt(object):
    def get_registration_code(self):
        """调用 apps.license_mgmt.nats_api.get_registration_code。"""

    def validate_module_create_access(self, module_code: str):
        """调用 apps.license_mgmt.nats_api.validate_module_create_access。"""
```

```python
# server/apps/license_mgmt/middleware/license_guard.py
class LicenseCreateGuardMiddleware:
    """
    用于资源新增链路的统一许可校验中间件。
    调用前先判断 settings 中是否启用 license_mgmt；未启用时直接放行。
    """

    def __call__(self, request):
        ...
```

```python
# server/apps/license_mgmt/config.py
LICENSE_APP_PERMISSIONS = {
    "cmdb": [
        {
            "method": "POST",
            "path_regex": r"^/api/v1/cmdb/.+/create/$",
            "action": "create",
        }
    ],
    "node_mgmt": [],
    "monitor": [],
    "log": [],
}
```

约定：

- `LICENSE_APP_PERMISSIONS` 固定定义在 `license_mgmt/config.py` 中
- 配置项会经由 `server/config/components/extra.py` 自动注入 `django.conf.settings`
- 顶层 key 为 app / module 标识，如 `cmdb`、`node_mgmt`、`monitor`、`log`
- 各 app 在各自 key 下补充需要被许可校验的新增资源入口定义
- `license_mgmt.permission_guard_service` 负责从 settings 读取该配置并建立校验入口
- 第一版由 `node_mgmt`、`cmdb`、`monitor`、`log` 各自补齐本模块配置内容

接口口径建议：

- `GET /api/v1/license_mgmt/license/`
- `POST /api/v1/license_mgmt/license/`
- `POST /api/v1/license_mgmt/license/{id}/disable/`
- `GET /api/v1/license_mgmt/license/history/`
- `GET /api/v1/license_mgmt/license/registration-code/`
- `GET /api/v1/license_mgmt/module-summary/`
- `GET/PUT /api/v1/license_mgmt/reminder/global/`
- `GET/PUT /api/v1/license_mgmt/reminder/license/{license_id}/`
- `GET/PUT /api/v1/license_mgmt/reminder/node/{module_code}/`
- `GET/PUT /api/v1/license_mgmt/reminder/log-memory/`

---

## 4. 核心逻辑伪代码

### 4.1 注册码读取

```text
get_registration_code():
1. 读取 server/apps/license_mgmt/registration_code.py
2. 获取 registration_code 变量值
3. 返回给接口层
```

### 4.2 许可新增

```text
add_license(license_key, operator):
1. 校验 license_key 非空
2. 如果入参是 .lic 文件内容字符串：
   2.1 读取 registration_code.py 中的注册码
   2.2 解密外层许可证文本
   2.3 取出 activationCode
3. 对 activationCode 执行 base64url 解码 -> JSON
4. 提取 sig，构造 canonical payload
5. 使用 Ed25519 公钥验签
6. 校验 nbf / exp 时间窗口
7. 读取当前注册码明文，并校验 payload.reg 是否一致
8. 从 payload.con 提取 license_no / valid_from / valid_until / module_codes / 额度信息
9. 校验 license_no 是否重复
10. 创建 LicenseRecord(status=active)
11. 按需同步或初始化提醒 / 模块额度相关数据
12. 返回新增结果
13. 前端收到成功结果后刷新许可列表
```

### 4.3 许可停用

```text
disable_license(license_id, operator):
1. 查询 LicenseRecord
2. 校验当前状态是否允许停用
3. 更新 status=disabled
4. 写入 disabled_reason / disabled_at
5. 返回停用结果
6. 后续新增资源校验统一读取最新许可状态
```

### 4.4 模块新增资源校验中间件

```text
LicenseCreateGuardMiddleware(request):
1. 通过 getattr(settings, "LICENSE_MGMT_ENABLED", False) 判断是否启用 license_mgmt
2. 若未启用：直接放行
3. 若启用：识别当前请求是否属于新增资源操作
4. 若不属于新增资源操作：直接放行
5. 若属于新增资源操作：映射出 module_code（node_mgmt / cmdb / monitor / log）
6. 通过 PermissionGuardService 读取 settings 中的 `LICENSE_APP_PERMISSIONS`
7. 若当前请求未命中任何 guard：直接放行
8. 若命中 guard：通过 RPC/NATS 调用 license_mgmt.validate_module_create_access(module_code)
9. 若 allowed=False：返回明确错误响应
10. 若 allowed=True：放行
```

### 4.5 提醒配置保存

```text
save_global_reminder(payload):
1. 校验 channel_ids 非空
2. 校验 remind_days > 0
3. 校验 user_ids 均在当前用户拥有权限组下的可见范围内
4. upsert LicenseGlobalReminderConfig
5. 返回最新配置

save_license_reminder(payload):
1. 校验 mode in [follow, custom]
2. 若 mode=follow：清空覆盖字段
3. 若 mode=custom：
   3.1 校验 channel_ids 非空
   3.2 校验 remind_days > 0
   3.3 校验 user_ids 可见范围
4. upsert LicenseReminderOverride
5. 返回回显结果
```

---

## 5. 影响范围与改动点

### 5.1 后端

- 新增企业版独立 app `license_mgmt`
- 新增独立 models、serializers、viewsets、services、urls、migrations
- 新增 `apps.rpc.license_mgmt` RPC 封装
- 新增 `license_mgmt.nats_api` 暴露注册码读取与许可校验能力
- 菜单初始化命令增加 `license_mgmt` 存在性判断
- 新增或接入统一资源创建校验中间件
- 新增 `license_decode_service`，用于许可码解码、canonical 化、Ed25519 验签与时间窗口校验
- 在 `license_mgmt/config.py` 的 `LICENSE_APP_PERMISSIONS` 中集中维护各 app 的新增资源校验入口定义

### 5.2 前端

- 系统管理设置页新增“许可”页签入口
- 企业版在 `system-manager/enterprise` 下新增 `license_mgmt` API 封装
- 企业版在 `system-manager/enterprise` 下新增许可管理页面、类型与相关组件
- 社区版仅保留系统管理公共壳与企业版扩展加载点
- 不复用 `system_settings` 作为许可数据源

### 5.3 不改动范围

- 社区版 `system_mgmt` 模型与 migration
- 社区版 `INSTALLED_APPS`
- 社区版前端 `system-manager` 主目录下的许可页面业务实现
- 告警、日志、监控、节点管理的已有页面信息架构
- 通知渠道通用模型本身
- 社区版仓库中的任何 `license_mgmt` 代码与 migration

---

## 6. 测试方案

### 6.1 后端单元 / 集成测试

- `LicenseRecord` 增删改查测试
- 历史许可状态归档测试
- `JSONField` 字段保存/读取测试
- 全局默认提醒保存/读取测试
- 单许可提醒 `follow / custom` 测试
- 节点提醒唯一约束测试：`module_code + object_type`
- 日志容量提醒模式切换测试
- `registration_code.py` 读取测试
- `.lic` 字符串外层解密测试
- 许可码 canonical JSON 验签测试
- 按 `kv` 从 settings 选择公钥验签测试
- `nbf / exp` 时间窗口校验测试
- `payload.reg` 与系统注册码不一致时拒绝导入测试
- `LICENSE_MGMT_ENABLED=False` 时中间件直接放行测试
- `LICENSE_MGMT_ENABLED=True` 时中间件调用 `license_mgmt` NATS 接口测试
- `LICENSE_APP_PERMISSIONS` 配置加载测试
- 停用许可后 `node_mgmt / cmdb / monitor / log` 新增入口拦截测试

### 6.2 前端验证

- “许可”页签可见性验证
- 企业版目录实现可正常被系统管理设置页接入验证
- 生效许可列表、历史许可列表展示验证
- 默认提醒：多渠道、多通知人员、多天数配置验证
- 单许可提醒：`跟随默认 / 单独配置` 验证
- 节点提醒：默认摘要、专用节点覆盖、重复对象类型校验验证
- 日志容量提醒：`跟随默认 / 单独配置` 与阈值验证
- 注册码展示与复制验证
- 新增许可 / 停用许可后列表刷新验证

### 6.3 最小门禁

- `cd server && make test`
- `cd web && pnpm lint && pnpm type-check`

---

## 7. 发布与回滚策略

### 7.1 发布策略

- 企业版直接上线
- 先确认企业版 `INSTALLED_APPS` 已注册 `license_mgmt`
- 确认菜单初始化逻辑存在 `license_mgmt` 存在性判断
- 确认 `license_mgmt` migration 可独立执行
- 确认部署环境会正确覆盖 `server/apps/license_mgmt/registration_code.py`

### 7.2 回滚策略

1. 前端回滚：移除 `system-manager/enterprise` 下的许可页面实现与菜单入口接入。
2. 后端回滚：下线 `api/v1/license_mgmt/...` 路由。
3. 数据回滚：按 `license_mgmt` 自有 migration 链回退。
4. 校验降级：必要时关闭 `LICENSE_MGMT_ENABLED`，统一放行新增资源操作。
5. 通知降级：保留配置数据，临时关闭实际发送调用。

---

## 8. 技术约束与注意事项

- `license_mgmt` 只允许单向依赖 `system_mgmt`，禁止反向 import。
- `license_mgmt` 仅存在于企业版代码，不得提交到社区版仓库主干。
- 许可管理前端业务代码仅允许放在 `web/src/app/system-manager/enterprise/...`，不得直接落入社区版 `system-manager/(pages)/settings/license`。
- 通知人员和通知渠道的可见范围，均限定为“当前用户拥有权限组下的可见范围”。
- 注册码统一来自 `server/apps/license_mgmt/registration_code.py`，部署时必须覆盖为真实值。
- `.lic` 文件外层解密使用该注册码，不再依赖本地生成或持久化的加密注册码文件。
- 中间件调用 `license_mgmt` 前必须先通过 `getattr(settings, ...)` 判断功能是否启用，避免社区版或未注册环境报错。
- 许可码验签需严格遵循“base64url -> 去 sig -> canonical JSON -> Ed25519 -> 时间窗口”顺序，禁止简化为仅 JSON 解码。
- 公钥统一放在 settings 中管理，需支持按 `kv` 取值。
- 公钥 settings 第一版推荐示例：

```python
LICENSE_DEFAULT_PUBLIC_KEY_VERSION = int(os.getenv("LICENSE_DEFAULT_PUBLIC_KEY_VERSION", 1))

LICENSE_PUBLIC_KEYS = {
    1: os.getenv("LICENSE_PUBLIC_KEY_V1", ""),
    2: os.getenv("LICENSE_PUBLIC_KEY_V2", ""),
}
```

- `license_decode_service` 应在启动或首次调用时校验：默认版本存在、对应公钥非空、`kv` 命中失败时返回明确错误。

---

## 9. 待确认项（TODO）

- TODO: 生产环境实际注入哪些 `LICENSE_PUBLIC_KEY_V*` 值，以及首发默认版本号取值需发布前确认。确认位置：部署配置、发码平台配置。
