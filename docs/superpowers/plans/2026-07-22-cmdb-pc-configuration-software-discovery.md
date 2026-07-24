# CMDB PC 配置与软件发现实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不新增远程协议链路的前提下，为企业版 CMDB 提供 Windows/WinRM 与 macOS/SSH 的 PC 配置、系统级安装软件发现、安全快照对账和一致的任务表单。

**Architecture:** PC 作为企业版 `host/job` 采集对象，经 `PCNodeParams → Stargazer PCInventoryCollector → 既有 WinRM/SSH executor → VictoriaMetrics → PCCollectionPlugin → PCSnapshotReconciler` 完成端到端闭环。Server 使用 PC 专用逐设备快照对账，不让通用任务级清理处理 PC 软件；权威任务、旧快照保护和显式移交由 Django 持久状态控制。

**Tech Stack:** Python 3.12、Django 4.2、Celery、FalkorDB/GraphClient、Stargazer/Sanic、NATS、Ansible Executor/WinRM、SSH Executor、PowerShell、POSIX Shell、Next.js 16、React 19、TypeScript、Ant Design、pytest、openpyxl。

**Design:** `docs/superpowers/specs/2026-07-22-cmdb-pc-configuration-software-discovery-design.md`

## Global Constraints

- 首版只支持 Windows 与 macOS；Linux、鸿蒙 OS、Agent 和 WMI 不进入实现或验收。
- Windows 固定 WinRM，macOS 固定 SSH；一个任务只能选择一种 OS，不做自动探测、协议切换或失败降级。
- 不新增协议服务、NATS Subject、调度系统或结果存储链路。
- PC 唯一标识使用 `WIN-<UUID>` / `MAC-<IOPlatformUUID>`，无效 UUID 才回退 `WIN-SN-<Serial>` / `MAC-SN-<Serial>`。
- 软件实例唯一标识不包含版本；使用 `SW-` 加规范化输入 SHA-256 的前 32 位大写十六进制。
- 自动采集只更新白名单字段；资产编号、组织、部门、资产使用人、采购、成本、位置、价值、备注和资产状态不得覆盖。
- 完整快照通过全部安全门后才允许删除；部分或失败快照绝不删除。
- 一台 PC 同时只有一个权威任务；显式移交只有在新任务获得完整有效快照并成功写入后才能完成。
- 连接测试 15 秒；单台采集默认 120 秒、允许 30～300 秒；输出不超过 10 MB；软件不超过 5000 条；单字段不超过 1024 字符。
- 远程脚本只读、内置、版本化；禁止 `Win32_Product`、注册表写入、文件删除、软件安装/卸载和任意用户脚本。
- 后端禁止原生 SQL，所有关系数据库操作使用 Django ORM。
- 所有功能按 TDD 实施；触及代码覆盖率不低于 75%，每个任务独立提交。

---

## 文件结构与职责

### Server / CMDB

- `server/apps/cmdb/support-files/model_config.xlsx`：补充 PC 自动采集字段、`pc_software` 模型和 `pc_software --install_on--> pc` 关联。
- `server/apps/cmdb/tests/test_pc_model_config.py`：锁定模型、字段类型、人工/自动字段边界和关联方向。
- `server/apps/cmdb_enterprise/collect/tree.py`：注册企业版 PC 发现入口及加密字段。
- `server/apps/cmdb_enterprise/collect/pc.py`：定义 `PCNodeParams` 与 `PCCollectionPlugin`。
- `server/apps/cmdb/serializers/collect_serializer.py`：校验 PC 任务 OS、协议固定值、凭据形状、超时与编辑不可变约束。
- `server/apps/cmdb/models/pc_discovery.py`：保存每台 PC 的权威任务、最近快照与待移交任务。
- `server/apps/cmdb/migrations/0043_pcdiscoveryauthority.py`：创建权威来源表。
- `server/apps/cmdb/services/pc_discovery.py`：解析 VM 行、执行逐 PC 对账、移交、过期清理和结果摘要。
- `server/apps/cmdb/collection/change_records.py`：补齐自动采集删除实例审计。
- `server/apps/cmdb/services/data_cleanup_service.py`：PC 任务的过期清理分流到软件专用逻辑。
- `server/apps/cmdb/services/pc_connection_test.py`：验证测试请求、路由到接入点 Stargazer 并脱敏结果。
- `server/apps/cmdb/views/collect.py`：暴露 PC 连接测试和权威任务移交 action。
- `server/apps/rpc/stargazer.py`：封装 `debug_pc` RPC。
- `server/apps/cmdb/tests/test_pc_node_params.py`、`test_pc_task_serializer.py`、`test_pc_snapshot_parser.py`、`test_pc_reconcile.py`、`test_pc_authority.py`、`test_pc_connection_test.py`、`test_collect_change_records.py`：Server 行为测试。

### Stargazer

- `agents/stargazer/enterprise/plugins/inputs/pc/plugin.yml`：PC JOB 插件元数据、双 OS 脚本与 `PCInventoryCollector` 配置。
- `agents/stargazer/enterprise/plugins/inputs/pc/pc_inventory.py`：固定协议路由、原始输出解析、身份/软件规范化、快照状态与资源边界。
- `agents/stargazer/enterprise/plugins/inputs/pc/pc_windows_discover.ps1`：Windows 只读硬件、系统和 HKLM 软件采集。
- `agents/stargazer/enterprise/plugins/inputs/pc/pc_macos_discover.sh`：macOS 只读硬件、系统和 `/Applications` 软件采集。
- `agents/stargazer/plugins/script_executor.py`：在既有 SSH 请求中透传 PEM 私钥与密码短语，不改变 Subject。
- `agents/stargazer/service/debug/pc_debug.py`、`service/nats_server.py`：复用相同采集器执行最小身份连接测试。
- `agents/stargazer/tests/test_pc_inventory.py`、`test_pc_scripts_contract.py`、`test_pc_debug.py`：路由、解析、安全和边界测试。
- `agents/stargazer/tests/fixtures/pc/*.json`：Windows/macOS 完整、部分、空和非法快照样本。

### Web

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/pcTask.tsx`：复用 `BaseTaskForm` 的 PC 表单容器。
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx`：增加 `winrm`、`macos_ssh` 两种凭据形状。
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/utils/pcTask.ts`：OS 联动、默认值、提交/回填和警告规则的纯函数。
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`：在既有 `task_type=host` 内把 `model_id=pc` 路由到 `PCTask`。
- `web/src/app/cmdb/api/collect.ts`：连接测试和移交 API。
- `web/src/app/cmdb/types/autoDiscovery.ts`：PC 参数、凭据和连接测试响应类型。
- `web/src/app/cmdb/constants/professCollection.ts`：PC 表单默认值。
- `web/src/app/cmdb/locales/zh.json`、`en.json`：PC 表单与错误码文案。
- `web/scripts/cmdb-pc-discovery-form-test.ts`：纯函数与接线合同测试。

---

### Task 1: 建立 PC 与安装软件模型合同

**Files:**
- Modify: `server/apps/cmdb/support-files/model_config.xlsx`
- Create: `server/apps/cmdb/tests/test_pc_model_config.py`

**Interfaces:**
- Produces: `pc` 自动字段、`pc_software` 模型、`pc_software_install_on_pc` 模型关联。
- Consumes: 既有模型导入约定：第二行为字段 ID，关联表使用 `src_model_id/dst_model_id/asst_id/mapping`。

- [ ] **Step 1: 写模型配置失败测试**

```python
import openpyxl

XLSX = "apps/cmdb/support-files/model_config.xlsx"
PC_COLLECTED = {
    "host_name": "str", "ip_addr": "str", "os_type": "str",
    "os_name": "str", "os_version": "str", "os_build": "str",
    "architecture": "str", "hardware_uuid": "str", "serial_number": "str",
    "device_model": "str", "logged_in_user": "str", "last_collect_time": "time",
}
SOFTWARE_FIELDS = {
    "inst_name": "str", "organization": "organization", "name": "str",
    "version": "str", "publisher": "str", "software_key": "str",
    "product_id": "str", "install_location": "str", "install_date": "str",
    "architecture": "str", "source": "str", "last_collect_time": "time",
}

def _rows(sheet):
    rows = list(sheet.iter_rows(values_only=True))
    keys = rows[1]
    return [dict(zip(keys, row)) for row in rows[2:] if row[0]]

def test_pc_and_software_schema_contract():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    models = {row["model_id"]: row for row in _rows(wb["models"])}
    assert models["pc_software"]["classification_id"] == "fixed_asset"
    pc_attrs = {row["attr_id"]: row for row in _rows(wb["attr-pc"])}
    sw_attrs = {row["attr_id"]: row for row in _rows(wb["attr-pc_software"])}
    assert {key: pc_attrs[key]["attr_type"] for key in PC_COLLECTED} == PC_COLLECTED
    assert {key: sw_attrs[key]["attr_type"] for key in SOFTWARE_FIELDS} == SOFTWARE_FIELDS
    assert pc_attrs["user"]["editable"] is True
    association = _rows(wb["asso-pc_software"])[0]
    assert association == {
        "src_model_id": "pc_software", "dst_model_id": "pc",
        "asst_id": "install_on", "mapping": "n:1",
    }
```

- [ ] **Step 2: 运行测试并确认因缺少模型/字段失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_model_config.py`

Expected: FAIL，首个失败指向 `pc_software`、`attr-pc_software` 或 PC 自动字段不存在。

- [ ] **Step 3: 精确更新工作簿**

在 `models` 增加 `pc_software / PC安装软件 / cc-software_软件 / fixed_asset`；在 `attr-pc` 只追加上表 PC 自动字段，保留全部既有人工字段；新增 `attr-pc_software`，字段与 `SOFTWARE_FIELDS` 完全一致；新增 `asso-pc_software`：

```text
pc_software | pc | install_on | n:1
```

`inst_name` 和 `organization` 必填，`inst_name` 唯一；软件业务字段可编辑为 `False`，防止手工写入与采集对账冲突。`pc` 既有 `brand/cpu/men/disk` 不新增同义字段。

- [ ] **Step 4: 运行模型配置测试**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_model_config.py apps/cmdb/tests/test_collection_field_type_alignment.py`

Expected: PASS。

- [ ] **Step 5: 提交模型合同**

```bash
git add server/apps/cmdb/support-files/model_config.xlsx server/apps/cmdb/tests/test_pc_model_config.py
git commit -m "feat: 补充PC软件发现模型"
```

### Task 2: 注册企业版 PC 入口并约束任务参数

**Files:**
- Modify: `server/apps/cmdb_enterprise/collect/tree.py`
- Create: `server/apps/cmdb_enterprise/collect/pc.py`
- Modify: `server/apps/cmdb/serializers/collect_serializer.py`
- Create: `server/apps/cmdb/tests/test_pc_node_params.py`
- Create: `server/apps/cmdb/tests/test_pc_task_serializer.py`

**Interfaces:**
- Produces: `PCNodeParams(BaseNodeParams)`；Stargazer 参数 `os_type`, `auth_type`, `winrm_scheme`, `winrm_transport`, `winrm_cert_validation`, `private_key`, `passphrase`。其中 `winrm_scheme` 表示 `https/http`，`winrm_transport` 固定为 `ntlm`，沿用现有 HostCollector 命名。
- Consumes: `CollectModels.params["os_type"] in {"windows", "macos"}`，任务固定 `task_type="host"`, `driver_type="job"`, `model_id="pc"`。

- [ ] **Step 1: 写注册、凭据透传和序列化失败测试**

```python
def test_pc_node_params_windows_contract(pc_task):
    pc_task.params = {
        "os_type": "windows",
        "winrm_scheme": "https",
        "winrm_transport": "ntlm",
        "winrm_cert_validation": False,
    }
    pc_task.credential = [{"username": "ACME\\alice", "password": "secret", "port": 5986}]
    params = PCNodeParams(pc_task)
    headers = params.custom_headers()
    assert headers["cmdbos_type"] == "windows"
    assert headers["cmdbport"] == "5986"
    assert headers["cmdbwinrm_scheme"] == "https"
    assert headers["cmdbwinrm_transport"] == "ntlm"
    assert headers["cmdbwinrm_cert_validation"] == "False"

def test_pc_serializer_rejects_os_change(existing_windows_task):
    serializer = CollectModelSerializer(
        existing_windows_task,
        data={"params": {"os_type": "macos"}},
        partial=True,
    )
    assert serializer.is_valid() is False
    assert "操作系统" in str(serializer.errors)
```

补充参数化用例：Windows 只接受 5986/HTTPS 或显式 5985/HTTP；macOS 只接受密码或 PEM 私钥；超时边界 29、301 拒绝，30、300 接受；非 PC 任务行为不变。

- [ ] **Step 2: 运行定向测试确认失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_node_params.py apps/cmdb/tests/test_pc_task_serializer.py`

Expected: FAIL，原因是 PC 注册、NodeParams 和专用校验尚不存在。

- [ ] **Step 3: 注册采集树与实现 PCNodeParams**

```python
class PCNodeParams(BaseNodeParams):
    supported_model_id = "pc"
    supported_driver_type = CollectDriverTypes.JOB
    plugin_name = "pc_info"
    host_field = "ip_addr"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "job"

    def set_credential(self):
        return self._build_credential(self.credential)

    def build_credentials_pool(self):
        return [self._build_credential(item, index) for index, item in enumerate(self.credential_pool)]
```

`_build_credential()` 只输出当前 OS 所需字段；所有秘密值使用 `${ENV_NAME}`，`env_config()` 分别注入 `password/private_key/passphrase`。采集树条目设置：

```python
{
    "id": "pc", "model_id": "pc", "name": "PC发现",
    "task_type": CollectPluginTypes.HOST, "type": CollectDriverTypes.JOB,
    "tag": ["JOB", "Windows", "macOS"],
    "encrypted_fields": ["password", "private_key", "passphrase"],
}
```

- [ ] **Step 4: 在 CollectModelSerializer 增加 PC 专用校验**

```python
if model_id == "pc":
    attrs = validate_pc_collect_task(attrs, instance=self.instance)
```

`validate_pc_collect_task()` 归一化 OS、固定任务/驱动类型、校验凭据互斥、默认端口和 WinRM 固定认证；编辑时拒绝改变 `os_type`。前端 scheme 字段提交为 `winrm_scheme`，固定 NTLM 提交为 `winrm_transport="ntlm"`。HTTP/5985 合法但在 `params["security_warning"]` 写固定提示码，不把提示文本当业务状态。

- [ ] **Step 5: 运行 Server 定向回归**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_node_params.py apps/cmdb/tests/test_pc_task_serializer.py apps/cmdb/tests/test_collect_object_tree.py apps/cmdb/tests/test_enterprise_extensions.py`

Expected: PASS。

- [ ] **Step 6: 提交任务契约**

```bash
git add server/apps/cmdb_enterprise/collect/tree.py server/apps/cmdb_enterprise/collect/pc.py server/apps/cmdb/serializers/collect_serializer.py server/apps/cmdb/tests/test_pc_node_params.py server/apps/cmdb/tests/test_pc_task_serializer.py
git commit -m "feat: 注册PC发现任务契约"
```

### Task 3: 实现 Windows 只读发现脚本

**Files:**
- Create: `agents/stargazer/enterprise/plugins/inputs/pc/pc_windows_discover.ps1`
- Create: `agents/stargazer/tests/test_pc_scripts_contract.py`
- Create: `agents/stargazer/tests/fixtures/pc/windows_complete.json`
- Create: `agents/stargazer/tests/fixtures/pc/windows_empty.json`

**Interfaces:**
- Produces: 单个 UTF-8 JSON 对象 `{snapshot_status, pc, software, software_expected_count, software_error_count}`。
- Consumes: PowerShell/CIM 与 HKLM Uninstall 注册表；不依赖额外安装包。

- [ ] **Step 1: 写脚本静态安全合同测试**

```python
def test_windows_script_is_read_only():
    source = WINDOWS_SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "win32_product" not in lowered
    for forbidden in ("set-itemproperty", "remove-item", "start-process", "msiexec", "winget install"):
        assert forbidden not in lowered
    assert "Win32_ComputerSystemProduct" in source
    assert "WOW6432Node" in source
    assert "ConvertTo-Json" in source
```

再锁定 `SystemComponent=1`、KB/Update、驱动、AppX 排除条件和两个 HKLM 路径。

- [ ] **Step 2: 运行测试确认脚本缺失**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_scripts_contract.py -k windows`

Expected: FAIL，脚本文件不存在。

- [ ] **Step 3: 写最小只读 PowerShell 脚本**

脚本必须设置 `$ErrorActionPreference = "Stop"`，单条软件解析失败只增加 `software_error_count` 并令状态为 `partial`；输出前按规范化 `name|publisher` 去重。最终只执行：

```powershell
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$result = [ordered]@{
  snapshot_status = $snapshotStatus
  pc = $pc
  software = @($software)
  software_expected_count = @($software).Count
  software_error_count = $softwareErrorCount
}
$result | ConvertTo-Json -Depth 8 -Compress
```

- [ ] **Step 4: 运行静态合同与 fixture 解析测试**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_scripts_contract.py -k windows`

Expected: PASS。

- [ ] **Step 5: 提交 Windows 脚本**

```bash
git add agents/stargazer/enterprise/plugins/inputs/pc/pc_windows_discover.ps1 agents/stargazer/tests/test_pc_scripts_contract.py agents/stargazer/tests/fixtures/pc/windows_complete.json agents/stargazer/tests/fixtures/pc/windows_empty.json
git commit -m "feat: 增加Windows PC只读发现脚本"
```

### Task 4: 实现 macOS 只读发现脚本

**Files:**
- Create: `agents/stargazer/enterprise/plugins/inputs/pc/pc_macos_discover.sh`
- Modify: `agents/stargazer/tests/test_pc_scripts_contract.py`
- Create: `agents/stargazer/tests/fixtures/pc/macos_complete.json`
- Create: `agents/stargazer/tests/fixtures/pc/macos_partial.json`

**Interfaces:**
- Produces: 与 Task 3 完全相同的 JSON 结构。
- Consumes: macOS 内置的 `ioreg`, `system_profiler`, `sw_vers`, `defaults`, `plutil`, `find`, `osascript`；只扫描 `/Applications/*.app` 与 `/Applications/Utilities/*.app`，不依赖目标机额外安装 Python、Homebrew 或 jq。

- [ ] **Step 1: 增加 macOS 脚本失败合同**

```python
def test_macos_script_scope_and_safety():
    source = MACOS_SCRIPT.read_text(encoding="utf-8")
    assert "/Applications" in source
    assert "/Applications/Utilities" in source
    assert "/System/Applications" not in source
    assert "pkgutil --pkgs" not in source
    assert "/Users/" not in source
    for forbidden in ("rm ", "sudo ", "installer ", "brew install"):
        assert forbidden not in source
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_scripts_contract.py -k macos`

Expected: FAIL，macOS 脚本不存在。

- [ ] **Step 3: 实现只读 Shell 脚本**

使用 `set -u`，但单应用解析失败不终止整批；通过 macOS 内置 `/usr/bin/osascript -l JavaScript` 的 `JSON.stringify` 完成最终 JSON 编码，数据通过参数或标准输入传入，不创建临时文件、不拼接不安全 JSON，也不依赖 Python。Bundle ID 缺失时保留名称和发布者，稳定键由 Collector 统一生成。

- [ ] **Step 4: 运行全部脚本合同**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_scripts_contract.py`

Expected: PASS。

- [ ] **Step 5: 提交 macOS 脚本**

```bash
git add agents/stargazer/enterprise/plugins/inputs/pc/pc_macos_discover.sh agents/stargazer/tests/test_pc_scripts_contract.py agents/stargazer/tests/fixtures/pc/macos_complete.json agents/stargazer/tests/fixtures/pc/macos_partial.json
git commit -m "feat: 增加macOS PC只读发现脚本"
```

### Task 5: 实现 PCInventoryCollector、固定协议路由和资源边界

**Files:**
- Create: `agents/stargazer/enterprise/plugins/inputs/pc/__init__.py`
- Create: `agents/stargazer/enterprise/plugins/inputs/pc/plugin.yml`
- Create: `agents/stargazer/enterprise/plugins/inputs/pc/pc_inventory.py`
- Modify: `agents/stargazer/plugins/script_executor.py`
- Create: `agents/stargazer/tests/test_pc_inventory.py`

**Interfaces:**
- Produces: `PCInventoryCollector.list_all_resources() -> {"success": bool, "result": {"pc": list, "pc_software": list}}`。
- Consumes: Windows `ansible_adhoc(... module="win_shell", connection="winrm")`；macOS `SSHPlugin.list_all_resources(need_raw=True)`。

- [ ] **Step 1: 写路由、身份和边界失败测试**

```python
@pytest.mark.asyncio
async def test_windows_routes_to_winrm(mock_ansible, windows_payload):
    mock_ansible.return_value = {"success": True, "result": [{"host": "10.0.0.8", "stdout": json.dumps(windows_payload)}]}
    result = await PCInventoryCollector(_windows_params()).list_all_resources()
    kwargs = mock_ansible.await_args.kwargs
    assert kwargs["module"] == "win_shell"
    assert kwargs["host_credentials"][0]["connection"] == "winrm"
    assert result["result"]["pc"][0]["inst_name"].startswith("WIN-")

@pytest.mark.asyncio
async def test_macos_routes_to_existing_ssh(mock_ssh, macos_payload):
    mock_ssh.return_value = {"success": True, "result": json.dumps(macos_payload)}
    result = await PCInventoryCollector(_macos_params()).list_all_resources()
    assert result["result"]["pc"][0]["inst_name"].startswith("MAC-")
```

补充测试：UUID 占位值回退序列号；双身份无效失败；同软件升级摘要不变；超过 10 MB、5000 条、1024 字符降级且不可删除；`expected_count=0` 以字符串标签保留；Windows/macOS 与错误协议组合拒绝。参数化锁定连接与脚本异常到稳定错误码的映射：`TARGET_UNREACHABLE`、`WINRM_AUTH_FAILED`、`WINRM_TLS_FAILED`、`SSH_AUTH_FAILED`、`SSH_KEY_INVALID`、`SCRIPT_TIMEOUT`、`SCRIPT_OUTPUT_INVALID`。

- [ ] **Step 2: 运行定向测试确认失败**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_inventory.py`

Expected: FAIL，Collector 与插件配置不存在。

- [ ] **Step 3: 实现规范化纯函数**

```python
def build_pc_inst_name(os_type: str, hardware_uuid: str, serial_number: str) -> str:
    prefix = {"windows": "WIN", "macos": "MAC"}[os_type]
    normalized_uuid = normalize_hardware_uuid(hardware_uuid)
    if normalized_uuid and normalized_uuid not in INVALID_HARDWARE_IDS:
        return f"{prefix}-{normalized_uuid}"
    normalized_serial = normalize_serial(serial_number)
    if normalized_serial and normalized_serial not in INVALID_SERIALS:
        return f"{prefix}-SN-{normalized_serial}"
    raise PCInventoryError("PC_IDENTITY_INVALID")

def build_software_inst_name(pc_inst_name: str, stable_key: str) -> str:
    canonical = f"{pc_inst_name}\n{stable_key}".encode("utf-8")
    return "SW-" + hashlib.sha256(canonical).hexdigest()[:32].upper()
```

稳定键 Windows 为规范化名称+发布者；macOS 优先 Bundle ID。版本不进入输入。

- [ ] **Step 4: 实现执行分支与统一输出**

`plugin.yml` 只声明 `job`，scripts 键为 `windows`、`macos`，collector 指向 `enterprise.plugins.inputs.pc.pc_inventory.PCInventoryCollector`。Collector 为每次目标生成 UUID4 `snapshot_id`，向 PC/软件行写相同 ID、`pc_inst_name`、字符串型 count/error 元数据。

在 `pc_inventory.py` 集中定义异常分类函数，先按执行器的结构化返回码分类，再对经过脱敏的异常类型分类，不通过任意语言文本猜测认证失败。采集与 Server 对外只使用以下稳定集合：

```python
PC_ERROR_CODES = frozenset({
    "TARGET_UNREACHABLE", "WINRM_AUTH_FAILED", "WINRM_TLS_FAILED",
    "SSH_AUTH_FAILED", "SSH_KEY_INVALID", "SCRIPT_TIMEOUT",
    "PC_IDENTITY_INVALID", "SCRIPT_OUTPUT_INVALID", "SOFTWARE_PARTIAL",
    "SNAPSHOT_COUNT_MISMATCH", "SOURCE_TASK_CONFLICT", "STALE_SNAPSHOT",
    "CMDB_WRITE_PARTIAL",
})
```

`SOFTWARE_PARTIAL` 由脚本记录级失败产生；`SNAPSHOT_COUNT_MISMATCH`、`SOURCE_TASK_CONFLICT`、`STALE_SNAPSHOT`、`CMDB_WRITE_PARTIAL` 在 Server 对账阶段产生。Task 14 的跨模块合同锁定两端集合与前端文案键一致。

- [ ] **Step 5: 最小扩展 SSHPlugin 的密钥初始化与透传**

在 `SSHPlugin.__init__()` 增加：

```python
self.private_key = params.get("private_key")
self.passphrase = params.get("passphrase")
```

并在 `_build_exec_params()` 非本地分支只增加：

```python
if self.private_key:
    exec_params["private_key"] = self.private_key
if self.passphrase:
    exec_params["passphrase"] = self.passphrase
```

不得改变 `ssh.execute.{node_id}`、密码路径或本地执行路径；日志不得输出两个字段值。

- [ ] **Step 6: 运行 Collector 与既有脚本执行器回归**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_inventory.py tests/test_collect_multicred.py`

Expected: PASS。

- [ ] **Step 7: 提交采集器**

```bash
git add agents/stargazer/enterprise/plugins/inputs/pc agents/stargazer/plugins/script_executor.py agents/stargazer/tests/test_pc_inventory.py
git commit -m "feat: 接入PC双系统采集执行器"
```

### Task 6: 建立 Server 快照解析器与 PC collection plugin

**Files:**
- Modify: `server/apps/cmdb_enterprise/collect/pc.py`
- Create: `server/apps/cmdb/services/pc_discovery.py`
- Create: `server/apps/cmdb/tests/test_pc_snapshot_parser.py`
- Modify: `server/apps/cmdb_enterprise/tests/test_new_collect_objects_enterprise_boundary.py`

**Interfaces:**
- Produces: `PCSnapshot`、`parse_pc_vm_rows(rows) -> list[PCSnapshot]`、`PCCollectionPlugin`。
- Consumes: VM 指标 `pc_info`、`pc_software_info`；`snapshot_id` 与所有计数都是 label 字符串。

- [ ] **Step 1: 写完整、空、部分、计数不匹配和多 PC 解析测试**

```python
def test_complete_empty_snapshot_is_preserved():
    snapshots = parse_pc_vm_rows([pc_metric(status="complete", expected="0", errors="0")])
    assert len(snapshots) == 1
    assert snapshots[0].status == "complete"
    assert snapshots[0].software == ()
    assert snapshots[0].can_delete is True

def test_count_mismatch_downgrades_partial():
    rows = [pc_metric(status="complete", expected="2", errors="0"), software_metric("Chrome")]
    snapshot = parse_pc_vm_rows(rows)[0]
    assert snapshot.status == "partial"
    assert snapshot.error_code == "SNAPSHOT_COUNT_MISMATCH"
    assert snapshot.can_delete is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_snapshot_parser.py`

Expected: FAIL，解析器不存在。

- [ ] **Step 3: 定义不可变快照类型和安全门**

```python
@dataclass(frozen=True)
class PCSnapshot:
    pc: dict
    software: tuple[dict, ...]
    status: str
    snapshot_id: str
    expected_count: int
    error_count: int
    collected_at: datetime
    error_code: str = ""

    @property
    def can_delete(self) -> bool:
        return self.status == "complete" and self.error_count == 0 and len(self.software) == self.expected_count
```

解析器按 `(pc_inst_name, snapshot_id)` 分组，验证软件归属、重复 `inst_name`、合法来源和最新指标时间；任一条件失败降级 `partial`。

- [ ] **Step 4: 实现 PCCollectionPlugin**

继承 `AutoRegisterCollectionPluginMixin, CollectBase`，注册 `(task_type=CollectPluginTypes.HOST, model_id="pc")`，`_metrics=("pc_info", "pc_software_info")`。`format_metrics()` 调用 `apply_pc_snapshots(task, snapshots)`；像 IPAM 插件一样返回 `{pc: []}` 并把摘要放入 `__task_format_data__`，从而绕开通用任务级删除。

- [ ] **Step 5: 运行解析与企业边界测试**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_snapshot_parser.py apps/cmdb_enterprise/tests/test_new_collect_objects_enterprise_boundary.py`

Expected: PASS。

- [ ] **Step 6: 提交 Server 插件骨架**

```bash
git add server/apps/cmdb_enterprise/collect/pc.py server/apps/cmdb/services/pc_discovery.py server/apps/cmdb/tests/test_pc_snapshot_parser.py server/apps/cmdb_enterprise/tests/test_new_collect_objects_enterprise_boundary.py
git commit -m "feat: 增加PC快照解析插件"
```

### Task 7: 持久化权威任务和显式移交状态

**Files:**
- Create: `server/apps/cmdb/models/pc_discovery.py`
- Modify: `server/apps/cmdb/models/__init__.py`
- Create: `server/apps/cmdb/migrations/0043_pcdiscoveryauthority.py`
- Modify: `server/apps/cmdb/services/pc_discovery.py`
- Create: `server/apps/cmdb/tests/test_pc_authority.py`

**Interfaces:**
- Produces: `PCDiscoveryAuthority`、`PCAuthorityService.authorize()`、`request_handover()`、`complete_handover()`。
- Consumes: `pc_inst_name`, 当前 `CollectModels`, `snapshot_id`, `collected_at`。

- [ ] **Step 1: 写首次绑定、冲突、旧快照和移交失败测试**

```python
def test_first_task_binds_and_second_task_conflicts(task_a, task_b):
    assert PCAuthorityService.authorize(task_a, "WIN-ABC", "s1", T1).mode == "owner"
    decision = PCAuthorityService.authorize(task_b, "WIN-ABC", "s2", T2)
    assert decision.mode == "conflict"
    assert decision.error_code == "SOURCE_TASK_CONFLICT"

def test_partial_snapshot_cannot_complete_handover(authority, task_b):
    PCAuthorityService.request_handover(authority.pc_inst_name, task_b)
    assert PCAuthorityService.complete_handover(authority, task_b, snapshot_status="partial") is False
```

- [ ] **Step 2: 运行测试确认模型缺失**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_authority.py`

Expected: FAIL。

- [ ] **Step 3: 创建权威来源模型与迁移**

```python
class PCDiscoveryAuthority(TimeInfo):
    pc_inst_name = models.CharField(max_length=128, unique=True)
    authoritative_task = models.ForeignKey(CollectModels, on_delete=models.PROTECT, related_name="owned_pcs")
    pending_task = models.ForeignKey(CollectModels, null=True, blank=True, on_delete=models.SET_NULL, related_name="pending_pc_handovers")
    last_snapshot_id = models.CharField(max_length=64, blank=True, default="")
    last_snapshot_time = models.DateTimeField(null=True, blank=True)
```

不存凭据、不复制 PC 资产字段。所有修改使用 `transaction.atomic()` + `select_for_update()`，由唯一约束解决首次并发绑定。

- [ ] **Step 4: 实现授权状态机**

`authorize()` 返回 `owner/conflict/pending_handover/stale`。待移交任务可以执行 PC/软件新增更新但 `allow_delete=False`；只有完整快照全部写入成功后 `complete_handover()` 才切换 owner 并清空 pending。旧任务后续立即冲突。

- [ ] **Step 5: 运行迁移检查和权威测试**

Run: `cd server && uv run python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`。

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_authority.py`

Expected: PASS。

- [ ] **Step 6: 提交权威状态**

```bash
git add server/apps/cmdb/models/pc_discovery.py server/apps/cmdb/models/__init__.py server/apps/cmdb/migrations/0043_pcdiscoveryauthority.py server/apps/cmdb/services/pc_discovery.py server/apps/cmdb/tests/test_pc_authority.py
git commit -m "feat: 增加PC采集权威来源控制"
```

### Task 8: 实现 PC 白名单写入和多目标隔离

**Files:**
- Modify: `server/apps/cmdb/services/pc_discovery.py`
- Create: `server/apps/cmdb/tests/test_pc_reconcile.py`

**Interfaces:**
- Produces: `PCSnapshotReconciler.apply_pc(snapshot) -> OperationResult`。
- Consumes: `Management(... model_id="pc", data_cleanup_strategy="no_cleanup")`。

- [ ] **Step 1: 写人工字段保护、幂等、身份和多目标隔离测试**

```python
def test_pc_update_only_writes_collected_whitelist(existing_pc, complete_snapshot):
    existing_pc.update(asset_code="A-001", user="alice", location="Shanghai")
    result = reconciler.apply(task, complete_snapshot)
    saved = graph_pc("WIN-ABC")
    assert saved["asset_code"] == "A-001"
    assert saved["user"] == "alice"
    assert saved["location"] == "Shanghai"
    assert saved["logged_in_user"] == "ACME\\bob"
    assert result.pc_failed == 0
```

补充测试：IP/主机名变化不新建 PC；无效身份不写；同任务两台 PC 一台失败不回滚另一台；来源冲突零写入。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_reconcile.py -k 'pc_ or multi_target'`

Expected: FAIL。

- [ ] **Step 3: 实现严格白名单**

```python
PC_COLLECTED_FIELDS = frozenset({
    "inst_name", "host_name", "ip_addr", "os_type", "os_name", "os_version",
    "os_build", "architecture", "hardware_uuid", "serial_number", "brand",
    "device_model", "cpu", "men", "disk", "logged_in_user", "last_collect_time",
})

def filter_pc_payload(raw: dict) -> dict:
    return {key: value for key, value in raw.items() if key in PC_COLLECTED_FIELDS}
```

组织只作为 `Management.organization` 创建必填值，不出现在更新 payload 中；禁止把原始 PC dict 全量传给 GraphClient。

- [ ] **Step 4: 独立循环应用每台 PC**

`apply_pc_snapshots()` 捕获单 PC 异常并生成 `_status=failed/_error=<稳定错误码>`，继续下一台；错误详情脱敏且截断到 500 字符。

- [ ] **Step 5: 运行 PC 写入测试**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_reconcile.py -k 'pc_ or multi_target'`

Expected: PASS。

- [ ] **Step 6: 提交 PC 写入阶段**

```bash
git add server/apps/cmdb/services/pc_discovery.py server/apps/cmdb/tests/test_pc_reconcile.py
git commit -m "feat: 实现PC白名单快照写入"
```

### Task 9: 实现软件 upsert 与 PC 关联

**Files:**
- Modify: `server/apps/cmdb/services/pc_discovery.py`
- Modify: `server/apps/cmdb/tests/test_pc_reconcile.py`

**Interfaces:**
- Produces: `upsert_software(snapshot, pc_entity) -> OperationResult`。
- Consumes: 软件 `assos=[{"model_id":"pc", "inst_name":..., "asst_id":"install_on", "model_asst_id":"pc_software_install_on_pc"}]`。

- [ ] **Step 1: 写软件升级、跨 PC 隔离和关联失败测试**

```python
def test_software_upgrade_updates_same_instance(reconciler, chrome_v1, chrome_v2):
    reconciler.apply(task, snapshot(software=[chrome_v1]))
    first = graph_software_for("WIN-ABC")
    reconciler.apply(task, snapshot(software=[chrome_v2]))
    second = graph_software_for("WIN-ABC")
    assert second["_id"] == first["_id"]
    assert second["version"] == chrome_v2["version"]

def test_association_failure_blocks_delete(...):
    result = reconciler.apply(task, complete_snapshot, fail_association=True)
    assert result.allow_delete is False
    assert old_software_still_exists()
```

- [ ] **Step 2: 运行软件用例确认失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_reconcile.py -k software`

Expected: FAIL。

- [ ] **Step 3: 实现软件白名单与无删除 upsert**

`Management` 的 `data_cleanup_strategy` 固定传 `NO_CLEANUP`；先 upsert 全部软件，再检查每个 `assos_result.failed`。任何新增、更新或关联失败都把该 PC 结果降级为部分成功。

- [ ] **Step 4: 运行软件与关联测试**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_reconcile.py -k software`

Expected: PASS。

- [ ] **Step 5: 提交软件写入阶段**

```bash
git add server/apps/cmdb/services/pc_discovery.py server/apps/cmdb/tests/test_pc_reconcile.py
git commit -m "feat: 写入PC软件与安装关系"
```

### Task 10: 实现安全差集删除、删除审计与过期清理

**Files:**
- Modify: `server/apps/cmdb/services/pc_discovery.py`
- Modify: `server/apps/cmdb/collection/change_records.py`
- Modify: `server/apps/cmdb/services/data_cleanup_service.py`
- Modify: `server/apps/cmdb/tests/test_pc_reconcile.py`
- Modify: `server/apps/cmdb/tests/test_collect_change_records.py`
- Create: `server/apps/cmdb/tests/test_pc_expiration_cleanup.py`

**Interfaces:**
- Produces: `delete_missing_software()`、`cleanup_expired_pc_software()`、自动采集 `DELETE_INST` 变更记录。
- Consumes: 当前 PC 的 `install_on` 关联集合，绝不查询整个 `pc_software` 模型作为差集。

- [ ] **Step 1: 写删除安全门与审计失败测试**

覆盖：完整删除、完整空清空、partial/failed/计数不匹配不删、upsert/关联失败不删、删除失败保留并可重试、只删当前 PC、旧快照不删、`no_cleanup` 不删、`after_expiration` 当次不删。

```python
def test_complete_empty_snapshot_deletes_only_current_pc_and_audits(...):
    result = reconciler.apply(task, complete_empty("WIN-ABC"))
    assert software_names("WIN-ABC") == []
    assert software_names("WIN-XYZ") == ["Chrome"]
    record = ChangeRecord.objects.get(type=DELETE_INST, inst_id=old_id)
    assert record.before_data["inst_name"].startswith("SW-")
    assert record.scenario == COLLECT_AUTOMATION_CHANGE
```

- [ ] **Step 2: 运行删除用例确认失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_reconcile.py -k delete apps/cmdb/tests/test_collect_change_records.py`

Expected: FAIL。

- [ ] **Step 3: 把通用自动采集审计补齐 DELETE_INST**

```python
delete_records = _build_delete_records(result.get("delete", {}).get("success", []))
if delete_records:
    batch_create_change_record(
        INSTANCE, DELETE_INST, delete_records,
        operator="system", scenario=COLLECT_AUTOMATION_CHANGE,
    )
```

`before_data` 保存删除前实体；消息包含模型、实例、任务和快照 ID。只有图删除成功项进入 success 审计。

- [ ] **Step 4: 按安全顺序实现当前 PC 差集删除**

先确认 `snapshot.can_delete`、owner、非旧快照、所有写入/关联成功和策略 `immediately`；再从 PC 关联集合计算差集。删除失败进入 format_data.delete failed，不更新 authority 的最近成功快照；下一轮重试。

- [ ] **Step 5: 分流 after_expiration**

`DataCleanupService.cleanup_expired_instances()` 遇 `task.model_id == "pc"` 时调用 `cleanup_expired_pc_software(task)`：只处理该权威任务拥有 PC 下、`collect_time` 早于阈值的软件；删除仍写审计。严禁通用分支按 `model_id=pc` 删除 PC。

- [ ] **Step 6: 运行删除、审计和过期清理测试**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_reconcile.py apps/cmdb/tests/test_collect_change_records.py apps/cmdb/tests/test_pc_expiration_cleanup.py`

Expected: PASS。

- [ ] **Step 7: 提交安全清理阶段**

```bash
git add server/apps/cmdb/services/pc_discovery.py server/apps/cmdb/collection/change_records.py server/apps/cmdb/services/data_cleanup_service.py server/apps/cmdb/tests/test_pc_reconcile.py server/apps/cmdb/tests/test_collect_change_records.py server/apps/cmdb/tests/test_pc_expiration_cleanup.py
git commit -m "feat: 安全清理已卸载PC软件"
```

### Task 11: 暴露移交 API 并完成任务状态聚合

**Files:**
- Modify: `server/apps/cmdb/views/collect.py`
- Modify: `server/apps/cmdb/services/collect_service.py`
- Modify: `server/apps/cmdb/services/pc_discovery.py`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`
- Create: `server/apps/cmdb/tests/test_pc_handover_views.py`
- Create: `server/apps/cmdb/tests/test_pc_task_status.py`

**Interfaces:**
- Produces: `POST /cmdb/api/collect/{task_id}/pc_handover/`，任务摘要 `pc_complete/pc_partial/pc_failed/source_conflict/software_added/software_updated/software_deleted`。
- Consumes: `pc_inst_names: list[str]`；执行权限与任务组织权限。

- [ ] **Step 1: 写权限、合法性和摘要状态失败测试**

测试非 PC 任务 400、无权限 403、不存在 PC 400、当前 owner 无需移交幂等成功、待移交写入成功；全部失败任务为 ERROR，混合结果为 PARTIAL_SUCCESS，全部完整为 SUCCESS。补充权威任务仍拥有 PC 时删除任务返回明确业务错误；完成移交后才允许删除旧任务，pending 任务删除时由 `SET_NULL` 自动取消待移交。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_handover_views.py apps/cmdb/tests/test_pc_task_status.py`

Expected: FAIL。

- [ ] **Step 3: 实现 pc_handover action**

```python
@action(methods=["POST"], detail=True, url_path="pc_handover")
@HasPermission("auto_collection-Execute")
def pc_handover(self, request, *args, **kwargs):
    task = self.get_object()
    result = PCAuthorityService.request_handovers(task, request.data.get("pc_inst_names", []))
    return WebUtils.response_success(result)
```

复用 `exec_task` 同级对象权限检查；不接受任意 task_id 覆盖 URL 目标。

- [ ] **Step 4: 把 PC 摘要合并进 collect_digest**

PC plugin 通过 `__task_format_data__` 产出通用 add/update/delete/association 以及 `pc_summary`；Celery 保存时复制 `pc_summary`，并按失败目标数决定 ERROR/PARTIAL_SUCCESS，不以完整空软件快照的 raw_data 为空误判失败。

- [ ] **Step 5: 保护权威任务删除边界**

在 CollectModelService 的任务删除入口检查 `PCDiscoveryAuthority.authoritative_task`；仍拥有 PC 时拒绝并返回“请先移交 PC 权威来源”，不得级联删除权威记录或 PC 实例。完成移交后旧任务按现有流程删除；若任务仅为 `pending_task`，删除后自动取消待移交。

- [ ] **Step 6: 运行视图与状态测试**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_handover_views.py apps/cmdb/tests/test_pc_task_status.py apps/cmdb/tests/test_collect_views_actions.py`

Expected: PASS。

- [ ] **Step 7: 提交移交和状态**

```bash
git add server/apps/cmdb/views/collect.py server/apps/cmdb/services/collect_service.py server/apps/cmdb/services/pc_discovery.py server/apps/cmdb/tasks/celery_tasks.py server/apps/cmdb/tests/test_pc_handover_views.py server/apps/cmdb/tests/test_pc_task_status.py
git commit -m "feat: 增加PC采集移交与状态摘要"
```

### Task 12: 实现真实链路的最小连接测试

**Files:**
- Create: `agents/stargazer/service/debug/pc_debug.py`
- Modify: `agents/stargazer/service/nats_server.py`
- Create: `agents/stargazer/tests/test_pc_debug.py`
- Modify: `server/apps/rpc/stargazer.py`
- Create: `server/apps/cmdb/services/pc_connection_test.py`
- Modify: `server/apps/cmdb/views/collect.py`
- Create: `server/apps/cmdb/tests/test_pc_connection_test.py`

**Interfaces:**
- Produces: `POST /cmdb/api/collect/pc_test_connection/`；RPC `debug_pc`。
- Consumes: 未落库表单 payload；只返回 `{success, os_type, inst_name, hardware_uuid|serial_number, error_code, message}`。

- [ ] **Step 1: 写“无 CMDB 写入、15 秒、真实路由”失败测试**

```python
def test_pc_connection_test_does_not_create_task_or_graph_instance(api_client, mock_rpc):
    before = CollectModels.objects.count()
    response = api_client.post("/cmdb/api/collect/pc_test_connection/", WINDOWS_REQUEST)
    assert response.status_code == 200
    assert CollectModels.objects.count() == before
    assert response.data["data"]["inst_name"].startswith("WIN-")
    assert mock_rpc.call_args.kwargs["timeout"] == 15
```

Stargazer 测试断言 Windows 只执行 CIM 身份命令、macOS 只执行 `ioreg`/`system_profiler` 身份命令，均不包含 Uninstall、`/Applications` 扫描或 CMDB callback。

- [ ] **Step 2: 运行两端测试确认失败**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_debug.py`

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_connection_test.py`

Expected: 均 FAIL。

- [ ] **Step 3: 实现 debug_pc RPC**

`run_pc_test_connection(params)` 复用 `PCInventoryCollector` 的连接构造与身份规范化函数，但使用固定最小脚本；对外错误只给稳定码，内部异常先脱敏。NATS handler 不记录原始 data。

- [ ] **Step 4: 实现 Server action 和权限/接入点路由**

复用 `CollectToolService.resolve_access_point()` 的授权逻辑；凭据只在内存传给 RPC，不创建 CollectModels。编辑任务传 `task_id` 与掩码时，按有权访问任务解密对应秘密字段。

- [ ] **Step 5: 运行连接测试回归**

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_debug.py tests/test_pc_inventory.py`

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/test_pc_connection_test.py apps/cmdb/tests/test_collect_views_actions.py`

Expected: PASS。

- [ ] **Step 6: 提交连接测试**

```bash
git add agents/stargazer/service/debug/pc_debug.py agents/stargazer/service/nats_server.py agents/stargazer/tests/test_pc_debug.py server/apps/rpc/stargazer.py server/apps/cmdb/services/pc_connection_test.py server/apps/cmdb/views/collect.py server/apps/cmdb/tests/test_pc_connection_test.py
git commit -m "feat: 增加PC发现连接测试"
```

### Task 13: 实现与现有 BaseTaskForm 一致的 PC 表单

**Files:**
- Create: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/utils/pcTask.ts`
- Create: `web/scripts/cmdb-pc-discovery-form-test.ts`
- Modify: `web/package.json`
- Create: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/pcTask.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`
- Modify: `web/src/app/cmdb/api/collect.ts`
- Modify: `web/src/app/cmdb/types/autoDiscovery.ts`
- Modify: `web/src/app/cmdb/constants/professCollection.ts`
- Modify: `web/src/app/cmdb/locales/zh.json`
- Modify: `web/src/app/cmdb/locales/en.json`

**Interfaces:**
- Produces: `PCTask`、`buildPCSubmitPayload()`、`buildPCFormValues()`、`getPCCredentialShape()`。
- Consumes: `BaseTaskForm`、`CredentialPoolEditor`、`useTaskForm`、Task 12 连接测试 API。

- [ ] **Step 1: 写纯函数与接线失败测试**

```typescript
assert.equal(getPCCredentialShape('windows'), 'winrm');
assert.equal(getPCCredentialShape('macos'), 'macos_ssh');
assert.deepEqual(getPCDefaults('windows'), {
  osType: 'windows', timeout: 120, cleanupStrategy: 'immediately',
  credentialPool: [{ port: 5986, scheme: 'https', transport: 'ntlm', certValidation: false }],
});
assert.equal(buildPCSubmitPayload(windowsValues).params.os_type, 'windows');
assert.equal(buildPCSubmitPayload(windowsValues).params.winrm_scheme, 'https');
assert.equal(buildPCSubmitPayload(windowsValues).params.winrm_transport, 'ntlm');
assert.equal(buildPCSubmitPayload(macosKeyValues).credential[0].private_key.includes('BEGIN'), true);
```

静态接线断言 `page.tsx` 导入 `PCTask`，并在通用 `taskMap` 前以 `currentPlugin.model_id === 'pc'` 返回该组件；`PCTask` 包含且只包含一个 `BaseTaskForm`，没有新抽屉/摘要侧栏。

- [ ] **Step 2: 运行脚本确认失败**

Run: `cd web && pnpm exec tsx scripts/cmdb-pc-discovery-form-test.ts`

Expected: FAIL，纯函数与 PCTask 尚不存在。

- [ ] **Step 3: 实现纯函数与类型**

```typescript
export type PCOSType = 'windows' | 'macos';
export const getPCCredentialShape = (os: PCOSType) => os === 'windows' ? 'winrm' : 'macos_ssh';
export const getPCDefaults = (os: PCOSType) => os === 'windows'
  ? { osType: os, timeout: 120, cleanupStrategy: 'immediately', credentialPool: [WINDOWS_DEFAULT] }
  : { osType: os, timeout: 120, cleanupStrategy: 'immediately', credentialPool: [MACOS_DEFAULT] };
```

提交函数把 OS 放入 `params.os_type`，把表单 `scheme` 映射到 `params.winrm_scheme`，把固定认证写成 `params.winrm_transport="ntlm"`，证书开关写入 `params.winrm_cert_validation`；编辑回填保持 OS 不可编辑；复制任务允许重新选择 OS，但清空所有秘密值。在 `web/package.json` 增加 `"test:cmdb-pc-discovery-form": "pnpm exec tsx scripts/cmdb-pc-discovery-form-test.ts"`。

- [ ] **Step 4: 扩展 CredentialPoolEditor**

`winrm` 展示用户名、密码、端口、HTTPS/HTTP、固定 NTLM、证书校验；HTTP 或证书校验关闭显示 Alert。`macos_ssh` 展示用户名、端口、认证方式、密码或 PEM 私钥、可选密码短语。切换认证方式时清除另一种秘密，避免同时提交。

- [ ] **Step 5: 实现 PCTask 并复用 BaseTaskForm 顺序**

OS 选择放在任务名称之后、扫描周期之前；其余基础设置、IP/资产选择、高级设置和页脚全部由 `BaseTaskForm` 提供。`onTest` 调 Task 12 API，成功展示 OS 与 inst_name，失败按稳定错误码显示中文。

- [ ] **Step 6: 运行前端合同、lint 和类型检查**

Run: `cd web && pnpm exec tsx scripts/cmdb-pc-discovery-form-test.ts`

Expected: `cmdb-pc-discovery-form-test passed`。

Run: `cd web && pnpm lint`

Expected: PASS。

Run: `cd web && pnpm type-check`

Expected: PASS。

- [ ] **Step 7: 提交前端表单**

```bash
git add web/package.json web/scripts/cmdb-pc-discovery-form-test.ts web/src/app/cmdb/\(pages\)/assetManage/autoDiscovery/collection/profess/utils/pcTask.ts web/src/app/cmdb/\(pages\)/assetManage/autoDiscovery/collection/profess/components/pcTask.tsx web/src/app/cmdb/\(pages\)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx web/src/app/cmdb/\(pages\)/assetManage/autoDiscovery/collection/profess/page.tsx web/src/app/cmdb/api/collect.ts web/src/app/cmdb/types/autoDiscovery.ts web/src/app/cmdb/constants/professCollection.ts web/src/app/cmdb/locales/zh.json web/src/app/cmdb/locales/en.json
git commit -m "feat: 增加PC发现配置采集表单"
```

### Task 14: 增加端到端合同与错误/秘密保护回归

**Files:**
- Create: `server/apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py`
- Create: `agents/stargazer/tests/test_pc_discovery_contract.py`
- Modify: `server/apps/cmdb/tests/test_collect_model_credential_pool.py`
- Modify: `server/apps/rpc/tests/test_sensitive_pure.py`

**Interfaces:**
- Produces: 从 NodeParams header 到 Stargazer Prometheus labels，再到 PCSnapshotReconciler 的离线可重复合同。
- Consumes: Task 1～13 的稳定接口。

- [ ] **Step 1: 写 Windows/macOS 端到端失败合同**

每个 OS 固定一份输入：任务+凭据、executor stdout、Prometheus/VM rows、期望 PC/软件/关联/摘要。断言：

```python
assert final_pc["inst_name"] == expected_pc_inst_name
assert final_software["inst_name"] == expected_software_inst_name
assert final_software["version"] == expected_version
assert result["format_data"]["delete"] == []
```

第二轮使用升级版本，第三轮完整空快照验证删除；另一路 partial 验证保留。

- [ ] **Step 2: 写秘密不落盘/日志合同**

递归扫描 NodeParams 公开 headers、任务 serializer 输出、VM labels、collect_data、format_data、ChangeRecord 和 RPC 安全过滤结果，断言不出现 password、PEM 正文和 passphrase 原值。

- [ ] **Step 3: 运行合同并确认断言真实覆盖跨模块边界**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py apps/cmdb/tests/test_collect_model_credential_pool.py apps/rpc/tests/test_sensitive_pure.py`

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_discovery_contract.py`

Expected: 若前序任务完整则 PASS；合同自身必须包含受控的失败/部分/完整空快照输入，并分别断言禁止删除、允许删除和秘密过滤，不能用只有成功路径的测试冒充端到端覆盖。若 FAIL，失败点必须明确落到参数接线、注册、状态转换或脱敏集合之一。

- [ ] **Step 4: 仅修复合同暴露的接线和脱敏缺口**

不得在此任务加入新功能；只允许补齐参数名不一致、漏注册、错误状态转换或安全过滤字段。所有秘密字段加入既有集中式过滤集合，不散落正则。

- [ ] **Step 5: 运行端到端合同**

Run: `cd server && uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py apps/cmdb/tests/test_collect_model_credential_pool.py apps/rpc/tests/test_sensitive_pure.py`

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_discovery_contract.py tests/test_pc_inventory.py tests/test_pc_debug.py`

Expected: PASS。

- [ ] **Step 6: 提交端到端合同**

```bash
git add server/apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py server/apps/cmdb/tests/test_collect_model_credential_pool.py server/apps/rpc/tests/test_sensitive_pure.py agents/stargazer/tests/test_pc_discovery_contract.py
git commit -m "test: 锁定PC发现端到端合同"
```

### Task 15: 完成全量门禁、真实环境验收与发布回滚记录

**Files:**
- Create: `docs/reviews/cmdb-pc-discovery-2026-07-22/01-test-evidence.md`
- Create: `docs/reviews/cmdb-pc-discovery-2026-07-22/02-windows-acceptance.md`
- Create: `docs/reviews/cmdb-pc-discovery-2026-07-22/03-macos-acceptance.md`
- Create: `docs/reviews/cmdb-pc-discovery-2026-07-22/04-release-recommendation.md`

**Interfaces:**
- Produces: 可审计的测试、真实主机验证、秘密扫描、风险与回滚证据。
- Consumes: Windows 10/11 WinRM 环境；至少一台 Intel 或 Apple Silicon macOS SSH 环境。

- [ ] **Step 1: 运行 Server 门禁**

Run: `cd server && make test`

Expected: PASS；记录总用例数、耗时和覆盖率。若全量被既有无关故障阻断，必须同时记录失败测试、基线复现和本功能定向门禁，不得写成全量通过。

- [ ] **Step 2: 运行 Stargazer 门禁**

Run: `cd agents/stargazer && make lint`

Expected: PASS。

Run: `cd agents/stargazer && uv run pytest -q tests/test_pc_inventory.py tests/test_pc_scripts_contract.py tests/test_pc_debug.py tests/test_pc_discovery_contract.py`

Expected: PASS，触及代码覆盖率 ≥75%。

- [ ] **Step 3: 运行 Web 门禁**

Run: `cd web && pnpm exec tsx scripts/cmdb-pc-discovery-form-test.ts`

Run: `cd web && pnpm lint && pnpm type-check`

Expected: 全部 PASS。

- [ ] **Step 4: Windows 真实环境验收**

依次验证 WinRM HTTPS/5986+NTLM、身份、硬件、HKLM 32/64 位软件、安装、升级、卸载、完整空快照、错误密码、端口阻断和 WinRM 关闭。若发布 HTTP/5985，再单独验证并截图安全警告。每次记录 task ID、snapshot ID、PC inst_name、前后软件实例 ID 和 ChangeRecord ID；文档不得记录凭据。

- [ ] **Step 5: macOS 真实环境验收**

依次验证 SSH 密码、PEM 私钥、带密码短语私钥、身份、`/Applications` 软件安装/升级/卸载、错误凭据、SSH 关闭和超时。记录实际 Intel/Apple Silicon 架构；未覆盖的另一架构明确标记“未验证”，不能用 fixture 代替。

- [ ] **Step 6: 执行安全与只读复核**

检查日志、API、VM、任务结果和审计中没有密码/私钥/密码短语；检查 Windows 注册表与 macOS 文件系统在采集前后无写入变化；以超时、10 MB 和 5000 软件边界验证目标机不崩溃、不修改配置、不丢数据。

- [ ] **Step 7: 写发布建议和回滚步骤**

发布建议只能为 `通过`、`有条件通过` 或 `不通过`，逐项引用前三份证据。回滚顺序：关闭企业版 PC 采集入口 → 停止 PC 任务 → 将清理策略置 `no_cleanup` → 回滚 Web/Server/Stargazer；不自动删除已发现 PC、软件或关联。

- [ ] **Step 8: 提交验收证据**

```bash
git add docs/reviews/cmdb-pc-discovery-2026-07-22
git commit -m "docs: 记录PC发现验收证据"
```

---

## 实施顺序与检查点

1. Task 1～2 完成模型与任务契约；此时不下发真实采集。
2. Task 3～5 完成远端只读脚本与执行路由；评审重点是目标机安全和秘密透传。
3. Task 6～10 完成 Server 快照、权威来源、白名单写入和安全删除；在 Task 10 通过前禁止开启 `immediately`。
4. Task 11～13 完成状态、连接测试和前端表单；此时形成可操作 MVP。
5. Task 14 完成离线端到端合同，Task 15 才允许连接真实 PC 并给出发布结论。

每个检查点都必须满足：定向测试通过、`git diff --check` 通过、提交只包含当前任务文件、没有跳过测试或以 mock 冒充真实环境。
