# License 管控的 enterprise footprint 识别设计

- 日期：2026-06-08
- 模块：`server/config/components`、`server/apps/system_mgmt`、`server/apps/license_mgmt`
- 主题：避免通过删除 `apps/license_mgmt` 目录绕过企业版许可校验

## 1. 背景与目标

当前服务端把“是否启用 license 管控”近似等同于“`server/apps/license_mgmt` 目录是否存在”。这个判断散落在多个入口：

- `server/config/components/app.py`
- `server/config/components/extra.py`
- `server/apps/system_mgmt/management/commands/init_realm_resource.py`

这会带来一个明显绕过点：如果仓库里仍保留其它 app 的 enterprise 增强内容，但用户强制删除 `apps/license_mgmt` 目录，系统就会按社区版路径启动，其它 app 也不会再进入许可校验。

本次目标：

- 不再只根据 `apps/license_mgmt` 目录存在与否判断企业版状态。
- 追加判断各 app 下 `enterprise` 目录是否存在**有效内容**。
- 对只有 `__init__.py` 的空壳 `enterprise` 目录不触发企业版识别。
- 一旦检测到 enterprise 内容仍存在，但 `license_mgmt` 缺失，系统必须在启动阶段失败，不能静默降级。

非目标：

- 不调整现有 license 授权规则、授权码模型和中间件拦截逻辑。
- 不引入人工维护的 enterprise app 白名单作为主判断来源。
- 不把空目录、`__pycache__`、隐藏文件视为 enterprise 有效内容。

## 2. 仓库现状与判定事实

当前仓库已存在多类 enterprise 内容：

| app | enterprise 内容 | 是否应计入 footprint |
|---|---|---|
| `core` | `license_filter.py` | 是 |
| `system_mgmt` | `urls.py`、`sensitive_info.py` | 是 |
| `monitor` | `language/`、`support-files/plugins/` | 是 |
| `node_mgmt` | `support-files/controllers/`、`support-files/collectors/` | 是 |
| `console_mgmt` | 仅 `__init__.py` | 否 |

设计结论：

- “有效 enterprise 内容”不只包含可导入 Python 模块，也包含会被运行时消费的资源文件，如语言包、JSON、插件定义、support-files。
- 只要 `enterprise` 目录下存在除 `__init__.py` 之外的有效文件，就说明该 app 仍然带有企业版 footprint。

## 3. 方案对比

### 方案 A：集中式 enterprise 探测器（采用）

新增统一探测器，扫描 `server/apps/*/enterprise`，输出：

- `has_enterprise_footprint`
- `enterprise_apps`
- `license_mgmt_present`

所有现有入口都改为消费这一个结果。

优点：

- 判断口径唯一，避免不同入口结果漂移。
- 能同时覆盖 Python enterprise 模块和非 Python 资源目录。
- 能在启动早期 fail closed，堵住“删目录降级”的绕过路径。

缺点：

- 需要把现有 3 处判断统一改造为依赖公共函数。

### 方案 B：在现有入口各自补扫描逻辑

在 `app.py`、`extra.py`、`init_realm_resource.py` 分别补 enterprise 目录扫描。

缺点：

- 逻辑重复，后续容易再次漂移。
- 某个入口漏改时，仍可能出现启动配置和菜单资源判断不一致。

### 方案 C：维护 enterprise app 白名单

通过固定配置声明哪些 app 算 enterprise，再检查这些 app 是否存在 enterprise 内容。

缺点：

- 需要长期维护配置，容易与实际目录结构脱节。
- 不能天然适配未来新增 enterprise app。

## 4. 设计总览

### 4.1 新的判定模型

建议增加一个集中式探测接口，例如：

```python
EnterpriseDetectionResult(
    has_enterprise_footprint: bool,
    enterprise_apps: list[str],
    license_mgmt_present: bool,
)
```

语义如下：

- `enterprise_apps`：存在有效 enterprise 内容的 app 列表。
- `has_enterprise_footprint`：`enterprise_apps` 是否非空。
- `license_mgmt_present`：`apps/license_mgmt` 目录是否完整存在。

### 4.2 有效内容判定规则

扫描范围：`server/apps/*/enterprise`

忽略项：

- `__init__.py`
- `__pycache__`
- 隐藏文件/目录

命中项：

- 任意其它 Python 文件
- 任意语言包文件
- 任意 JSON / YAML / 配置资源
- `support-files` 下被运行时读取的插件、控制器、采集器等文件

判定原则：

- 按“是否存在运行时有意义的文件”判断，而不是按“是否可 import”判断。
- 只要某个 app 命中至少一个有效文件，该 app 就进入 `enterprise_apps`。

## 5. 行为规则

统一行为如下：

| 条件 | 行为 |
|---|---|
| `enterprise_apps` 为空 | 视为社区版，跳过 license_mgmt 强制启用 |
| `enterprise_apps` 非空，且 `license_mgmt` 存在 | 视为企业版，按现有逻辑启用 `apps.license_mgmt` 与许可中间件 |
| `enterprise_apps` 非空，但 `license_mgmt` 缺失 | 启动阶段直接报错并阻止启动 |

这意味着：

- 不能再通过删除 `license_mgmt` 目录把带有 enterprise 内容的部署降级成社区版。
- 只有空壳 `enterprise` 目录时，才允许继续按社区版运行。

## 6. 落点设计

### 6.1 `server/config/components/app.py`

当前职责：

- 判断是否把 `apps.license_mgmt` 注入 `INSTALLED_APPS`
- 判断是否挂载两个 license middleware

改造后：

- 不再直接 `os.path.isdir(BASE_DIR/apps/license_mgmt)`。
- 统一调用 enterprise 探测器。
- 若检测到 footprint 但缺少 `license_mgmt`，在 Django 配置初始化阶段直接抛出异常。
- 只有在“footprint 存在且 license_mgmt 完整”时，才注入 `apps.license_mgmt` 与相关 middleware。

### 6.2 `server/config/components/extra.py`

当前职责：

- 基于 `apps/license_mgmt` 目录存在与否，强制把 `license_mgmt` 补进 `INSTALL_APPS`

改造后：

- 复用同一个探测结果。
- 仅在“footprint 存在且 license_mgmt 完整”时把 `license_mgmt` 补进 `INSTALL_APPS`。
- 若 footprint 存在但 `license_mgmt` 缺失，直接传播同一类异常，不允许继续加载局部配置。

### 6.3 `server/apps/system_mgmt/management/commands/init_realm_resource.py`

当前职责：

- 决定是否向 system-manager 注入 License 菜单与相关权限资源

改造后：

- `get_install_apps()` 不再自行判断目录是否存在，而是消费统一探测结果。
- 只有在企业版完整成立时才注入 license 菜单。
- 如果配置非法（有 footprint 但无 `license_mgmt`），命令执行也应直接失败，保证离线初始化行为与服务启动行为一致。

## 7. 错误处理

该问题被定义为**配置错误**，不是可容忍降级场景。

建议异常内容包含：

- 明确原因：检测到企业版内容，但缺少 `apps/license_mgmt`
- 命中的 app 列表
- 建议动作：恢复 `apps/license_mgmt`，或移除所有有效 enterprise 内容后再按社区版运行

示例语义：

```text
Detected enterprise footprint in apps: core, monitor, node_mgmt, system_mgmt, but apps/license_mgmt is missing. Refuse to start without license management.
```

要求：

- 不能静默打印日志后继续启动。
- 不能只在某个入口失败、另一个入口继续运行。
- 异常应尽量在配置初始化早期抛出，避免半初始化状态。

## 8. 测试与验收口径

至少覆盖以下场景：

1. `license_mgmt` 存在，且存在有效 enterprise 内容 -> 正常识别企业版。
2. `license_mgmt` 缺失，但所有 `enterprise` 目录都只有 `__init__.py` 或为空 -> 识别为社区版。
3. `license_mgmt` 缺失，且任一 app 存在有效 enterprise 文件 -> 启动失败。
4. 非 Python 资源文件（如 `monitor`/`node_mgmt` 的 `support-files`、语言包）也能触发 footprint。
5. `console_mgmt` 这种只有 `__init__.py` 的空壳目录不会误触发。
6. `app.py`、`extra.py`、`init_realm_resource.py` 读取到的判定结果一致。

## 9. 预期改动清单

- 新增一个统一的 enterprise footprint 探测模块
- `server/config/components/app.py` 改为消费探测结果
- `server/config/components/extra.py` 改为消费探测结果
- `server/apps/system_mgmt/management/commands/init_realm_resource.py` 改为消费探测结果
- 补充针对目录扫描与非法配置场景的测试

## 10. 决策摘要

- 采用**集中式 enterprise 探测器**，不采用分散扫描或手工白名单。
- “有效 enterprise 内容”包括 Python 代码和运行时资源文件，不限于可导入模块。
- 仅 `__init__.py` 不算 enterprise footprint。
- 发现 enterprise footprint 但缺失 `license_mgmt` 时，系统必须 fail closed，直接拒绝启动。
