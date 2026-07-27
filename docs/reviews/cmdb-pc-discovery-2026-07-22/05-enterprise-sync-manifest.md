# PC 发现企业版代码同步清单

日期：2026-07-27　分支基线：feature_windyzhao @ 2bfac8037（PC 工作基线 4b5f447bb 起共 19 个提交）

## 背景

`server/apps/cmdb_enterprise/`（.gitignore:61）与 `agents/stargazer/enterprise/`
（.gitignore:38 `**/enterprise/`）被本仓库忽略，其中代码不进入本仓库 git 历史。
PC 发现功能有 7+2 个文件落在这两个目录，需手动同步到商业版源码库。
本清单按目录列出全部文件、性质（新增/修改）与关键内容摘要。

## A. server 侧：`server/apps/cmdb_enterprise/`

### A1. `collect/pc.py` — 新增（139 行）

PC 发现的 NodeParams 与 collection plugin，是整个功能在 server 侧的核心：

- `PCNodeParams`（`supported_model_id="pc"`、`plugin_name="pc_info"`、JOB 驱动）：
  - `set_credential` / `build_credentials_pool` 输出 headers 凭据负载，
    **秘密值一律为 `${ENV}` 占位符**（`_secret_env_name` 按
    `{PREFIX}_{field}_{instance_id}[_{index}]` 命名，多凭据池带下标）；
  - `env_config` 返回真实秘密值映射（password/private_key/passphrase），
    由执行通道注入环境变量，不进入 headers；
  - windows：port 默认 5986，`winrm_scheme/transport/cert_validation` 来自任务 params；
    macos：port 默认 22，私钥优先（private_key + 可选 passphrase），否则 password。
- `PCCollectionPlugin`（`plugin_source="enterprise"`，priority=10，
  metric_names=`("pc_info","pc_software_info")`）：
  - `format_data` 只收 `collect_status != "failed"` 的 `pc_info`/`pc_software_info` 行；
  - `format_metrics` 调用 `apps.cmdb.services.pc_discovery` 的
    `parse_pc_vm_rows` + `apply_pc_snapshots` 做逐 PC 对账，
    摘要写入 `result["__task_format_data__"]`，`result["pc"]` 恒为空列表——
    **刻意绕开通用任务级清理**，删除权只归逐 PC 对账（安全删除三条件）。

### A2. `collect/tree.py` — PC 条目新增（文件内 27–41 行）

`ENTERPRISE_COLLECT_OBJ_TREE` 的 `host_manage` 分组下新增采集对象：

```python
{
    "id": "pc", "model_id": "pc", "name": "PC发现",
    "task_type": CollectPluginTypes.HOST, "type": CollectDriverTypes.JOB,
    "tag": ["JOB", "Windows", "macOS"],
    "desc": "采集 Windows/macOS PC 配置与系统级安装软件",
    "encrypted_fields": ["password", "private_key", "passphrase"],
}
```

`encrypted_fields` 三字段是凭据池加密与序列化脱敏的依据，漏同步会导致
pc 任务凭据明文入库/明文回显。

### A3. `tests/test_new_collect_objects_enterprise_boundary.py` — 修改

边界参数表新增一行 `("pc", "host", "job")`，锁定 PC 对象的企业版边界归属。

## B. stargazer 侧：`agents/stargazer/enterprise/plugins/inputs/pc/`

整个 `pc/` 插件目录为新增，7 个文件：

| 文件 | 行数 | 说明 |
|---|---|---|
| `pc_inventory.py` | 333 | 采集器主体，**含安全修复，见下方高亮** |
| `pc_windows_discover.ps1` | 155 | Windows 全量发现只读脚本（WinRM/win_shell 下发） |
| `pc_macos_discover.sh` | 151 | macOS 全量发现只读脚本（SSH 下发，JSON 由 osascript JXA 编码） |
| `pc_windows_identity.ps1` | 76 | 连接测试专用最小身份脚本（不枚举软件） |
| `pc_macos_identity.sh` | 89 | 连接测试专用最小身份脚本（不枚举 /Applications） |
| `plugin.yml` | 29 | 插件声明：job 执行器、timeout=120、双 OS 脚本路径、collector 指向 `PCInventoryCollector` |
| `__init__.py` | 0 | 包标记 |

### pc_inventory.py 关键点

- 固定协议路由：windows → 既有 `ansible_adhoc(win_shell/winrm)`；
  macos → 既有 `SSHPlugin`；不实现新的 WinRM/SSH 客户端。
- `normalize_snapshot`：身份规范化（硬件 UUID 优先、序列号兜底、厂商占位值黑名单）、
  软件稳定键（windows `name|publisher`、macos 优先 Bundle ID）、
  `SW-<sha256[:32]>` 实例名；资源边界（10MiB 输出、5000 软件、1024 字段长），
  **任何边界超限降级 partial，绝不伪装 complete**（直接决定 server 侧能否删除）。
- 错误分类只输出 13 个稳定错误码（`PC_ERROR_CODES`），不把任意语言文本当认证失败证据。

### ⚠️ 安全修复高亮（漏同步会重新暴露凭据回显缺口）

端到端合同测试（`agents/stargazer/tests/test_pc_discovery_contract.py::
test_executor_failure_exposes_only_stable_code_and_no_secret`）曾暴露：
执行器原始 msg 可能回显凭据，沿 `cmdb_collect_error` 进入 VM `collect_error` label。
修复内容（pc_inventory.py）：

```python
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)

def _scrub_secrets(self, text):
    """错误文本脱敏：执行器原始 msg 可能回显凭据，按已知秘密值精确替换。"""
    masked = str(text or "")
    masked = _PRIVATE_KEY_BLOCK_RE.sub("***", masked)
    for key in ("password", "private_key", "passphrase"):
        secret = self.params.get(key)
        if isinstance(secret, str) and secret:
            masked = masked.replace(secret, "***")
    return masked
```

并在 `list_all_resources` 的 `except PCInventoryError` 分支改为
`return _error_result(exc.code, self._scrub_secrets(str(exc)))`。

## C. 不需要手动同步的部分（已入本仓库 git）

以下 PC 相关改动在**已跟踪文件**中，随本仓库提交走正常合并/发布流程，
商业版构建只需以 `feature_windyzhao`（或合并后的 master）对应提交为基线：

- server：`apps/cmdb/services/pc_discovery.py`、`models/pc_discovery.py`、
  `views/collect.py`（pc_test_connection 视图）、序列化/凭据池/任务状态等，
  及全部 `apps/cmdb/tests/test_pc_*`、`tests/e2e/`（提交 5adf111c7..2bfac8037）；
- stargazer：`api/collect.py`（连接测试 HTTP 端点）、`service/debug/pc_debug.py`、
  `tests/test_pc_inventory.py` / `test_pc_scripts_contract.py` / `test_pc_debug.py` /
  `test_pc_discovery_contract.py`（提交 cfbf44c2f、33d924a0f、2bfac8037 等）；
- web：PC 表单组件与连接测试按钮（提交 352c9dd37）。

## D. 同步后验证

商业版源码库合入后，在该环境执行（合同测试会自动使用同步过来的企业版文件）：

```bash
cd agents/stargazer && uv run pytest -q tests/test_pc_inventory.py \
  tests/test_pc_scripts_contract.py tests/test_pc_debug.py tests/test_pc_discovery_contract.py
# 期望 47 passed；尤其 test_executor_failure_exposes_only_stable_code_and_no_secret 必须过

cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py
# 期望 6 passed
```

注意：stargazer 合同测试通过相对路径 `../../../server/apps/cmdb/tests/e2e/fixtures/pc/`
引用 server fixture，两个仓库的目录相对布局需保持一致。
