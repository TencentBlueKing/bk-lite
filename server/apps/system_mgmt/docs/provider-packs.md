# 集成 Provider 包约定

## 目的

约定 `server/apps/system_mgmt/providers/` 下 Provider 包的目录、模块职责、放置位置，以及包外顶层宿主的边界。改包布局、Loader、Manifest、adapter 入口或能力执行路径时先读本文，以当前代码为最终证据。

本文写两件事，不要混成一件：

1. **运行期约定**：业务代码如何执行登录 / 同步 / 通知 / 拉群（见「运行期约定」）。包作者与测试应稳定在这一层。
2. **打包与发现**：目录长什么样、Loader 扫哪里、单包失败如何隔离。这是发现期体检，不是业务调用点。

本文 **不覆盖**：上传 ZIP、待应用、滚动重启、插件管理面。新类型在上传通道落地前，只放进 `builtin/` 后发镜像。

## 信任模型

包在 Web / 任务 / NATS 等进程内 `import`，与平台代码同一权限（ORM、密钥、登录签发）。放入扫描根的 Python 等同平台代码。本期无沙箱、无签名、无热加载。Registry 在各进程内存中；改包后必须让相关进程都重新加载（当前即重启），不能只在某一个进程 `import`。

## 运行期约定

业务服务不直接 `import` 某个厂商包。它们走 `RuntimeApplicationService`：按实例上的 `provider_key` 取 Manifest，再按 capability 的 `adapter_key` 取已注册类，调用具名 operation。

```text
RuntimeApplicationService.execute(
    provider_key=...,
    capability_key=...,
    operation=...,
    config=instance.get_runtime_config(),
    **kwargs,
)
```

稳定面：

- 包实现继承 `providers/base.py` 中对应基类（`BaseLoginAuthAdapter` 等）。测连另有 `base_connection` adapter，不走四个 capability key。
- 每个 operation 是 **classmethod**，签名为 `(config, provider_key, capability_key, **kwargs)`。`config` 是实例运行时配置（含解密后的 secret）。其余 kwargs 由调用方服务传入（如登录的 `redirect_uri` / `auth_code`），以现有服务与内置 adapter 为准，不要另造 operation 名。
- 返回值必须是 `CapabilityExecutionResult`（或可被其 `model_validate` 的 dict）。未实现的 operation 用基类默认的 `provider.operation_not_implemented`，不要抛给 Runtime 以外的异常类型充当业务失败。
- Runtime 用 `getattr(adapter_cls, operation)` 分发。Manifest 未声明的 capability、未注册的 `adapter_key`、未知 `provider_key` 在 Runtime 侧失败，不得靠调用方猜路径。

平台只认四个 capability key。Manifest 不得声明此外的 key；未声明的能力不得建空模块。

```text
login_auth
user_sync
im_notification
im_group
```

当前 `schemas.py` 校验的是 capability / 字段 key 不重复、`reset_capabilities` 与 `business_template` 引用有效，**尚未**把白名单写进 schema。仍按白名单实现；新增 key 等于改平台，不是改一个包。

| capability | 基类 | 宿主会调用的 operation |
|---|---|---|
| （实例测连） | Manifest 的 `base_connection_*` | `test_connection`（Runtime 传入 `capability_key="base"`） |
| `login_auth` | `BaseLoginAuthAdapter` | `test_connection`，`build_login_url`，`authenticate` |
| `user_sync` | `BaseUserSyncAdapter` | `test_connection`，`sync_users`，`list_departments` |
| `im_notification` | `BaseIMNotificationAdapter` | `test_connection`，`list_external_users`，`send_message` |
| `im_group` | `BaseIMGroupAdapter` | `test_connection`，`get_constraints`，`validate_create`，`create_group`，`get_group`，`add_members`，`send_group_message` |

能力 Tab / 状态文案走平台 i18n，不走包内 yaml。`im_group` 的 `connection_template` 保持空列表。

注册表不变量（实现时遵守；Loader 目前不全部强制）：

- 包目录名、`PROVIDER_MANIFEST.key`、内置四家的 `provider_key` 三者一致。内置固定为 `feishu` / `wechat` / `wecom` / `ad`。
- `adapter_key` 与 `base_connection_adapter_key` 必须以 `{manifest.key}.` 为前缀（如 `wecom.login_auth`）。Loader 强制该前缀；违规时 **跳过该包**，已成功的包保留。注册表按这些 key **全局**唯一。
- 有包目录时，`adapter_path` / `base_connection_adapter_path` 是 **包内相对路径**。Loader 拼上该包模块前缀再 `import_string`。内置例：`adapters.login_auth.WeComLoginAuthAdapter`，对应模块 `apps.system_mgmt.providers.builtin.wecom`。禁止在有目录的包里写死本包绝对模块路径。测试里无包目录的假 Manifest 仍可写绝对导入。

## 包放置位置

Loader 只扫描内置根。包必须是该根下可导入的 Python 包。`system_mgmt.ready()` 不主动扫包；注册表读路径懒加载。

| 来源 | 扫描根 | 导入前缀 |
|---|---|---|
| 产品内置（飞书 / 微信 / 企微 / AD） | `providers/builtin/`（`BUILTIN_PROVIDER_ROOT`） | `apps.system_mgmt.providers.builtin.<目录名>` |
| 跨包工具 | `providers/common/`，不是 Provider 包 | — |
| 上传安装的包 | 不在本文 | — |

| 来源 | 放哪 |
|---|---|
| 产品内置 | `providers/builtin/{feishu,wechat,wecom,ad}/`。目录名与 key 固定。不要改名，不要把自研逻辑写进这四家。 |
| 跨包工具 | 只放 `providers/common/`，且仅当 **至少两个包** 共用。现在 `common/` 几乎为空；AD 专用 LDAP 放在 AD 包内。 |
| 上传安装的包 | 不在本文。不要为此在 `builtin/` 预留 ZIP 空壳，也不要恢复 `providers/custom/` 扫描。 |

不要把任何 Provider 包放到 `providers/common/`，也不要恢复顶层 `providers/adapters/`。缺少 `builtin/` 仍是平台缺陷，加载失败。

### 单包失败隔离

任一包缺文件、语言文件、Manifest 校验失败、目录名与 `key` 不一致、Adapter 导入失败或 key 冲突：**只跳过该包**，记 ERROR，其它包继续注册。加载结束后进程仍可用已成功的包；失败包对应的已有实例会表现为未知 Provider。

这不是静默跳过：日志必须带上包名。隔离的是 **发现/导入**，不是运行期——已加载 adapter 里抛出的异常仍按该次调用失败处理。

产品 CI 仍须断言内置四家都能加载；四家在发布物里缺一家是发版问题，不是靠现场「整表回滚」来发现。

新增产品 Provider：加在 `builtin/`，同一套目录结构。该包坏掉不应再带走其余内置包。

## 包目录

每个包导出 `PROVIDER_MANIFEST`。

```text
providers/builtin/<key>/
  __init__.py                 # 导出 PROVIDER_MANIFEST
  manifest.py                 # Python Manifest
  language/
    en.yaml
    zh-Hans.yaml
  adapters/
    client.py                 # 必须有（发现期占位，见下）
    base_connection.py        # 必须有：对应 Manifest 的 base_connection_adapter_path
    login_auth.py             # 仅声明了才有
    user_sync.py
    im_notification.py
    im_group.py
```

约束：

- 禁止顶层 `providers/adapters/`。基类在 `providers/base.py`。
- **每个包** 必须有 `adapters/`、`adapters/client.py`、`adapters/base_connection.py`。Loader 只检查这些文件存在，以便四家体检一致；微信/AD 公共面小也要有 `client.py`。
- `client.py` 用来放本包共用的 token / HTTP 分页 / 代理，或 LDAP bind/search。这是包内实现细节，不是 Runtime 的调用面。Loader **不会**检查能力模块是否真的走 client。能力文件不要求零 `requests`：OAuth 用户 token、发信 POST、群测连等专用调用可以留在能力模块；企微拉群可用 wechatpy，视为该包请求实现。
- 不要空 `assets/`。图标继续按 `provider_key` 由前端解析；新 key 在前端没有映射时会没有图标。本期不为包做图标资源约定。

### 可选的包内政策模块

上表是发现期必有/按能力声明才有的骨架。此外可以在包根（`adapters/` 外）放 **本包领域政策**：只服务这一家、描述配置或范围怎么理解的纯函数，既不是厂商协议，也不是 Runtime operation。现成例子：AD 的 `pull_dns.py`（拉取 DN 列表规范化、单/多根本地作用域）。

- 按领域命名（`pull_dns.py`），禁止 `utils.py` / `helpers.py`。
- 不进 `providers/common/`：那是至少两个包才用的跨包工具。
- 不要放进 `services/` 或 serializer；宿主继续只走 Runtime / 适配器钩子（如 `normalize_business_config`）。
- Loader **不体检**这类文件。没有第二段独立政策时，摊在对应能力模块里即可，不要为对称先拆。

### 语言文件

系统只认 `en` 与 `zh-Hans`（`zh` / `zh-CN` / `zh-Hans` → `zh-Hans`，其它 → `en`）。两份 yaml 的 `description` 必填；`name` 可缺。缺语言目录或缺文件 → **跳过该包**。缺 **单条** 表单文案不得拒绝该包加载。

文案职责：

- **机器身份**在 Manifest：`key`、字段 `key`、`secret`、模板结构。
- **人读文案**在 yaml：包 `name`/`description`，模板/分组 `title`，字段 `label`/`help_text`，提示语型 `placeholder`，select 的 `option.label`（按 **option.value** 挂 key）。
- Manifest 里的英文 `name`/`description`/`label` 只作 yaml 都缺时的最后兜底，不要在 Manifest 做 `{zh, en}` 字典，也不要把 Manifest 当翻译源。

解析：`用户 locale → 该语言 yaml → en.yaml → Manifest → provider_key`。

不进 yaml：实例自己的名称、能力 Tab、样例字符串（如 `DC=example,DC=com`）。

## `providers/` 顶层模块

| 模块 | 角色 |
|---|---|
| `loader.py` | 扫描 `builtin/`、校验布局、把相对 adapter 路径拼到包模块前缀再取类、注册 Provider 与 Adapter。单包失败跳过并记 ERROR，不得清空已成功的包。 |
| `registry.py` | 进程内 Provider / Adapter 注册表。读路径经 Loader 锁懒加载。 |
| `schemas.py` | Manifest 与模板字段契约。`pack_i18n` 不对外序列化。 |
| `base.py` | 能力基类。包实现继承这里。 |
| `runtime.py` | 按实例执行能力。宿主日志直连 `system_mgmt_logger`。 |
| `pack_i18n.py` | 读包 yaml、overlay 公开 Manifest、解析请求 locale。 |
| `log.py` | **包侧** 日志入口。Adapter / `client.py` / `base.py` 只从这里 `import logger`。底层接到 `system_mgmt_logger`。不要在包内 `import apps.core.logger`。 |
| `common/` | 跨包工具（两个以上包才用）。 |
| `builtin/` | 第一方包扫描根（`BUILTIN_PROVIDER_ROOT`）。 |

宿主（`loader.py`、`runtime.py`、view/serializer）继续 `from apps.core.logger import system_mgmt_logger as logger`。

`pack_i18n.request_locale`：主源 `system_mgmt.User.locale`（个人设置写入的账号表）；无账号行再回退 `request.user.locale`；再缺则 `en`。同一请求只查一次账号 locale。不要为包文案单独加 `Accept-Language`。

## 实例与兼容

集成实例只存 `provider_key`、`config`、能力状态/开关，**不存** Adapter 路径。搬家或拆文件不得改 `provider_key`、config 字段 key、secret 标记，也不得要求数据迁移。

本期不做：包版本号、包自带依赖安装、包级启停。

## 验收

- `builtin/` 下每个子目录（跳过 `__pycache__`）按内置导入前缀加载；缺 `client.py` 或 `base_connection.py` 时 **该包** 失败并被跳过。
- 内置四家按原 key 注册，manifest 使用包内相对 adapter 路径。语言文件缺失只跳过该包，其它包仍在注册表中。
- 不再扫描 `providers/custom/`。
- 包内 Python 源文件不出现 `from apps.core.logger import`。
- 已有实例的测试连接、登录、同步、通知、拉群仍只经 Runtime 具名 operation，不因包布局变化而改契约。
