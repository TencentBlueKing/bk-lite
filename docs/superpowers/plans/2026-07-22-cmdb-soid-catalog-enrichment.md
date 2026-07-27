# CMDB SOID 权威目录丰富与安全同步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立来源可追溯的主流网络设备 SOID 权威目录，并让新装与存量环境以非破坏、幂等方式同步内置映射。

**Architecture:** `systemoid.json` 保留现有运行数据结构并增加来源与验证状态，`systemoid.meta.json` 维护版本、品牌规范和官方来源。新的 `oid_catalog` 服务先离线加载和完整校验目录，再在单个数据库事务中计算并应用新增、内置更新、用户覆盖和目录外遗留差异；`init_oid` 仅负责参数和输出，采集侧继续精确匹配。

**Tech Stack:** Python 3.12、Django 4.2 ORM、pytest、标准库 `json/dataclasses/pathlib/re`；不新增依赖，不使用原生 SQL，不在运行时访问网络。

## Global Constraints

- 仅支持 `switch`、`router`、`firewall`、`loadbalance` 四类现有 CMDB 模型。
- 中国政企厂商优先，同时覆盖国际主流厂商。
- `CollectNetworkMetrics` 的精确 OID 匹配和未知设备回退合同保持不变。
- 只依据厂商官方产品 MIB/文档建立 `verified` 数据；IANA PEN 仅验证企业号根。
- 公开来源不足的历史记录保留为 `legacy-compatible`，不得静默删除。
- `built_in=False` 的用户自定义映射始终优先，任何同步模式均不得覆盖或删除。
- 目录外 `built_in=True` 记录只报告、不删除。
- `--force` 保留兼容但不得删除重建；`--dry-run` 必须零写入。
- 同步和测试完全离线，不提交厂商原始 MIB，不记录凭据、客户地址或设备原始返回。
- 新功能严格 TDD，触及代码行为覆盖率不低于 75%，只格式化触及文件。

---

## 文件结构

| 路径 | 动作 | 单一职责 |
|---|---|---|
| `server/apps/cmdb/services/oid_catalog.py` | 新建 | 目录数据类型、加载、校验、差异计算和事务同步 |
| `server/apps/cmdb/support-files/systemoid.meta.json` | 新建 | schema/catalog 版本、允许类型、品牌别名、官方来源索引 |
| `server/apps/cmdb/support-files/systemoid.json` | 修改 | 规范化并丰富 SOID 权威数据 |
| `server/apps/cmdb/management/commands/init_oid.py` | 修改 | `--dry-run`/`--force` 参数、调用同步服务、稳定输出统计 |
| `server/apps/cmdb/tests/test_oid_catalog.py` | 新建 | 目录纯校验、差异与同步服务合同 |
| `server/apps/cmdb/tests/test_init_oid_command.py` | 新建 | 管理命令参数、输出、幂等和兼容合同 |
| `server/apps/cmdb/tests/test_network_device_field_mapping_pure.py` | 修改 | 四类设备及重点厂商代表 SOID 防回退样本 |
| `server/apps/cmdb/support-files/plugins_doc/network.md` | 修改 | 说明 SOID 精确匹配、用户覆盖和安全同步方式 |

## 固定接口

后续任务统一使用以下接口，不得自行改名：

```python
@dataclass(frozen=True)
class OidCatalogEntry:
    oid: str
    model: str
    brand: str
    device_type: str
    source_id: str
    verification: str


@dataclass(frozen=True)
class OidSyncResult:
    created: int
    updated: int
    unchanged: int
    custom_override_oids: tuple[str, ...]
    stale_builtin_oids: tuple[str, ...]


def load_oid_catalog(
    catalog_path: Path = SYSTEMOID_PATH,
    metadata_path: Path = SYSTEMOID_METADATA_PATH,
) -> dict[str, OidCatalogEntry]: ...


def sync_oid_catalog(
    entries: Mapping[str, OidCatalogEntry],
    *,
    dry_run: bool = False,
) -> OidSyncResult: ...
```

`load_oid_catalog` 的所有输入错误统一转换为 `OidCatalogError`；`sync_oid_catalog` 不捕获数据库异常，让 `transaction.atomic` 回滚并由命令转换为稳定 `CommandError("OID_SYNC_FAILED")`。

---

### Task 1: 建立 SOID 目录加载与严格校验边界

**Files:**
- Create: `server/apps/cmdb/services/oid_catalog.py`
- Create: `server/apps/cmdb/tests/test_oid_catalog.py`
- Create: `server/apps/cmdb/support-files/systemoid.meta.json`

**Interfaces:**
- Consumes: `systemoid.json` 的现有七个字段。
- Produces: `OidCatalogError`、`OidCatalogEntry`、`load_oid_catalog(...) -> dict[str, OidCatalogEntry]`、`SYSTEMOID_PATH`、`SYSTEMOID_METADATA_PATH`。

- [ ] **Step 1: 写最小合法目录和格式错误的 RED 测试**

在 `test_oid_catalog.py` 使用 `tmp_path` 写入两个小型 JSON，不读取生产目录：

```python
import json

import pytest

from apps.cmdb.services.oid_catalog import OidCatalogError, load_oid_catalog


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _metadata():
    return {
        "schema_version": 1,
        "catalog_version": "2026.07.22",
        "allowed_device_types": ["switch", "router", "firewall", "loadbalance"],
        "brand_aliases": {"华为": "Huawei"},
        "sources": {
            "huawei-product-mib": {
                "vendor": "Huawei",
                "url": "https://info.support.huawei.com/info-finder/tool/zh/enterprise/mib",
                "document": "Huawei MIB Query",
                "version": "2026-07",
                "verified_at": "2026-07-22",
                "official": True,
                "scope": "product-identity",
            }
        },
    }


def _entry(oid="1.3.6.1.4.1.2011.2.23.968"):
    return {
        "OID": oid,
        "FirstTypeId": "Switch",
        "FirstTypeName": "交换机",
        "SecondTypeId": "HuaweiSwitch",
        "SecondTypeName": "Huawei交换机",
        "model": "S5735S-L8T4S-QA2",
        "brand": "Huawei",
        "source_id": "huawei-product-mib",
        "verification": "verified",
    }


def test_load_oid_catalog_returns_normalized_entry(tmp_path):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    oid = "1.3.6.1.4.1.2011.2.23.968"
    _write_json(catalog, {oid: _entry(oid)})
    _write_json(metadata, _metadata())

    entries = load_oid_catalog(catalog, metadata)

    assert entries[oid].brand == "Huawei"
    assert entries[oid].device_type == "switch"
    assert entries[oid].source_id == "huawei-product-mib"


@pytest.mark.parametrize(
    ("key", "stored_oid"),
    [
        (".1.3.6.1.4.1.2011.1", ".1.3.6.1.4.1.2011.1"),
        ("1.3.6.1.4.1.2011.1 ", "1.3.6.1.4.1.2011.1 "),
        ("1.3.6.1.4.1.2011.1", "1.3.6.1.4.1.2011.2"),
    ],
)
def test_load_oid_catalog_rejects_noncanonical_oid(tmp_path, key, stored_oid):
    catalog = tmp_path / "systemoid.json"
    metadata = tmp_path / "systemoid.meta.json"
    _write_json(catalog, {key: _entry(stored_oid)})
    _write_json(metadata, _metadata())

    with pytest.raises(OidCatalogError, match="OID"):
        load_oid_catalog(catalog, metadata)
```

- [ ] **Step 2: 运行 RED 测试，确认服务模块尚不存在**

Run:

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_oid_catalog.py
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'apps.cmdb.services.oid_catalog'`。

- [ ] **Step 3: 实现数据类型、路径常量和基础加载器**

创建 `oid_catalog.py`，先完成不触库的最小实现：

```python
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

SUPPORT_FILES = Path(__file__).resolve().parents[1] / "support-files"
SYSTEMOID_PATH = SUPPORT_FILES / "systemoid.json"
SYSTEMOID_METADATA_PATH = SUPPORT_FILES / "systemoid.meta.json"
OID_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+$")
VERIFICATION_STATES = {"verified", "legacy-compatible"}


class OidCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class OidCatalogEntry:
    oid: str
    model: str
    brand: str
    device_type: str
    source_id: str
    verification: str


@dataclass(frozen=True)
class OidSyncResult:
    created: int
    updated: int
    unchanged: int
    custom_override_oids: tuple[str, ...]
    stale_builtin_oids: tuple[str, ...]


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OidCatalogError(f"OID_CATALOG_INVALID: {path.name}") from exc


def load_oid_catalog(
    catalog_path: Path = SYSTEMOID_PATH,
    metadata_path: Path = SYSTEMOID_METADATA_PATH,
) -> dict[str, OidCatalogEntry]:
    raw_catalog = _read_json(Path(catalog_path))
    metadata = _read_json(Path(metadata_path))
    allowed_types = set(metadata.get("allowed_device_types", []))
    aliases = metadata.get("brand_aliases", {})
    sources = metadata.get("sources", {})
    entries: dict[str, OidCatalogEntry] = {}

    if metadata.get("schema_version") != 1 or not metadata.get("catalog_version"):
        raise OidCatalogError("OID_CATALOG_INVALID: metadata version")
    if not isinstance(raw_catalog, dict) or not raw_catalog:
        raise OidCatalogError("OID_CATALOG_INVALID: catalog must be a non-empty object")

    for key, raw in raw_catalog.items():
        oid = raw.get("OID") if isinstance(raw, dict) else None
        if key != oid or not isinstance(oid, str) or not OID_PATTERN.fullmatch(oid):
            raise OidCatalogError(f"OID_CATALOG_INVALID: OID {key!r}")
        required = {"FirstTypeId", "FirstTypeName", "SecondTypeId", "SecondTypeName", "model", "brand", "source_id", "verification"}
        if any(not isinstance(raw.get(field), str) or not raw[field].strip() for field in required):
            raise OidCatalogError(f"OID_CATALOG_INVALID: required fields for {oid}")
        device_type = raw["FirstTypeId"].lower()
        if device_type not in allowed_types:
            raise OidCatalogError(f"OID_CATALOG_INVALID: device type for {oid}")
        if raw["brand"] in aliases:
            raise OidCatalogError(f"OID_CATALOG_INVALID: noncanonical brand for {oid}")
        source_id = raw["source_id"]
        verification = raw["verification"]
        if source_id not in sources or verification not in VERIFICATION_STATES:
            raise OidCatalogError(f"OID_CATALOG_INVALID: source for {oid}")
        if verification == "verified":
            source = sources[source_id]
            required_source = {"vendor", "url", "document", "version", "verified_at", "official", "scope"}
            if (
                not required_source.issubset(source)
                or source["official"] is not True
                or source["scope"] != "product-identity"
            ):
                raise OidCatalogError(f"OID_CATALOG_INVALID: verified source for {oid}")
            if raw["model"].strip() == oid:
                raise OidCatalogError(f"OID_CATALOG_INVALID: verified model for {oid}")
        entries[oid] = OidCatalogEntry(
            oid=oid,
            model=raw["model"].strip(),
            brand=raw["brand"].strip(),
            device_type=device_type,
            source_id=source_id,
            verification=verification,
        )
    return entries
```

- [ ] **Step 4: 增加全部字段、品牌别名、来源完整性和非法型号测试**

增加参数化测试，明确拒绝以下输入：空型号、verified 型号等于完整 OID、`FirstTypeId=AP`、规范品牌仍写成“华为”、不存在的 `source_id`、`verified` 指向 `official=false`、来源 `scope` 不是 `product-identity`、元数据 schema 版本不是 1。每个断言匹配 `OID_CATALOG_INVALID`，不匹配底层 JSON 异常文本。

- [ ] **Step 5: 创建最小元数据并跑 GREEN**

`systemoid.meta.json` 首先包含固定顶层结构和 `legacy-catalog-v1` 来源；该来源设置 `official: false`，仅允许 `legacy-compatible` 使用：

```json
{
  "schema_version": 1,
  "catalog_version": "2026.07.22",
  "allowed_device_types": ["switch", "router", "firewall", "loadbalance"],
  "brand_aliases": {
    "华为": "Huawei",
    "HuaWei": "Huawei",
    "Hewlett-Packard": "HPE",
    "PaloAlto": "Palo Alto Networks"
  },
  "sources": {
    "legacy-catalog-v1": {
      "vendor": "Multiple",
      "url": "",
      "document": "BK-Lite legacy systemoid.json",
      "version": "pre-2026",
      "verified_at": "2026-07-22",
      "official": false,
      "scope": "legacy-catalog"
    }
  }
}
```

Run Task 1 test command again. Expected: all `test_oid_catalog.py` tests introduced in this task PASS。

- [ ] **Step 6: 提交目录校验边界**

```bash
git add server/apps/cmdb/services/oid_catalog.py server/apps/cmdb/tests/test_oid_catalog.py server/apps/cmdb/support-files/systemoid.meta.json
git commit -m "feat(cmdb): 建立 SOID 目录校验边界"
```

---

### Task 2: 规范化现有 1,966 条历史 SOID

**Files:**
- Modify: `server/apps/cmdb/support-files/systemoid.json`
- Modify: `server/apps/cmdb/support-files/systemoid.meta.json`
- Modify: `server/apps/cmdb/tests/test_oid_catalog.py`

**Interfaces:**
- Consumes: Task 1 的 `load_oid_catalog` 和 `legacy-catalog-v1`。
- Produces: 可被严格加载的完整历史目录；所有旧 OID 均有 `verification` 和 `source_id`。

- [ ] **Step 1: 写生产目录必须完整通过校验的 RED 测试**

```python
from apps.cmdb.services.oid_catalog import SYSTEMOID_METADATA_PATH, SYSTEMOID_PATH, load_oid_catalog


def test_production_catalog_is_valid_and_preserves_legacy_oid_set():
    raw = json.loads(SYSTEMOID_PATH.read_text(encoding="utf-8"))
    entries = load_oid_catalog(SYSTEMOID_PATH, SYSTEMOID_METADATA_PATH)

    assert len(raw) >= 1966
    assert len(entries) == len(raw)
    assert "1.3.6.1.4.1.9.1.1208" in entries
    assert "1.3.6.1.4.1.2011.2.23.968" in entries
    assert "1.3.6.1.4.1.25506.1.2609" in entries
```

- [ ] **Step 2: 运行单测确认生产目录因缺追溯字段而 RED**

Run Task 1 test command。Expected: FAIL，首个失败明确指出 `required fields`。

- [ ] **Step 3: 为所有历史记录添加兼容追溯字段并稳定排序**

对每条现有记录执行以下机械规则：

```json
"source_id": "legacy-catalog-v1",
"verification": "legacy-compatible"
```

使用项目 Python 读取后按 `tuple(int(part) for part in oid.split('.'))` 排序，并以 `ensure_ascii=False, indent=2` 输出；这是一次纯数据机械重排，不改变 OID、型号和类型。输出后立刻运行 `git diff --check` 和 Task 1 测试。

- [ ] **Step 4: 规范品牌但暂不改设备类型**

先在元数据 `brand_aliases` 中完整列出当前目录实际存在的非规范值，再对生产 JSON 执行一一替换。至少固定：

| 旧值 | 规范值 |
|---|---|
| `华为`、`HuaWei` | `Huawei` |
| `Hewlett-Packard` | `HPE` |
| `Netscreen` | `Juniper` |
| `Force10` | `Dell` |
| `NortelAlteon` | `Alteon` |
| `Venus` | `Venustech` |

不要合并 OID，不根据收购关系修改型号或类型。为每组替换补一个参数化断言，确保生产目录不再出现 alias key。

- [ ] **Step 5: 为危险历史形态增加显式合同**

增加测试统计并锁定：

- JSON key 必须等于 `OID`。
- 型号等于完整 OID 的记录不得标记为 `verified`。
- `.0` 结尾记录若为 `legacy-compatible` 可以保留；若提升为 `verified`，其来源必须是该产品身份定义。
- 四类以外的 `FirstTypeId` 立即失败。

Run Task 1 test command。Expected: PASS，生产目录条数不少于 1,966。

- [ ] **Step 6: 提交历史目录规范化**

```bash
git add server/apps/cmdb/support-files/systemoid.json server/apps/cmdb/support-files/systemoid.meta.json server/apps/cmdb/tests/test_oid_catalog.py
git commit -m "data(cmdb): 规范历史 SOID 目录"
```

---

### Task 3: 补充并纠正中国政企主流厂商 SOID

**Files:**
- Modify: `server/apps/cmdb/support-files/systemoid.json`
- Modify: `server/apps/cmdb/support-files/systemoid.meta.json`
- Modify: `server/apps/cmdb/tests/test_oid_catalog.py`
- Modify: `server/apps/cmdb/tests/test_network_device_field_mapping_pure.py`

**Interfaces:**
- Consumes: Task 2 的规范目录和品牌名。
- Produces: 国内第一优先级厂商的 `verified` 产品映射和代表型号回归集合 `DOMESTIC_REPRESENTATIVE_OIDS`。

- [ ] **Step 1: 写国内厂商来源与代表产品族 RED 合同**

在纯测试中定义明确的覆盖矩阵。合同按“该品牌/类型至少一条 verified 精确 OID，或元数据中存在同品牌/类型的公开来源缺口”判断，不允许用企业号前缀命中冒充产品覆盖：

```python
DOMESTIC_REQUIRED_FAMILIES = {
    "Huawei": {"switch", "router", "firewall"},
    "H3C": {"switch", "router", "firewall"},
    "Ruijie": {"switch", "router", "firewall"},
    "ZTE": {"switch", "router"},
    "Sangfor": {"firewall", "loadbalance"},
    "Hillstone": {"firewall"},
    "DPtech": {"firewall"},
    "Topsec": {"firewall"},
    "Venustech": {"firewall"},
}


def test_domestic_catalog_covers_or_declares_required_families():
    entries = load_oid_catalog()
    metadata = json.loads(SYSTEMOID_METADATA_PATH.read_text(encoding="utf-8"))
    actual = {}
    for entry in entries.values():
        if entry.verification == "verified":
            actual.setdefault(entry.brand, set()).add(entry.device_type)
    gaps = {
        brand: set(types)
        for brand, types in metadata.get("coverage_gaps", {}).items()
    }
    for brand, types in DOMESTIC_REQUIRED_FAMILIES.items():
        missing = types - actual.get(brand, set()) - gaps.get(brand, set())
        assert not missing, f"{brand} 缺少 verified 数据或显式缺口: {sorted(missing)}"
```

NSFOCUS 与 Qi-Anxin 不进入硬性类型矩阵。`coverage_gaps` 的值只保存未覆盖类型列表；对应原因、官方入口和核验日期放入 `coverage_gap_details`，两者的品牌 key 必须一致。目录测试断言 gap detail 非空且 URL 为 HTTPS。

- [ ] **Step 2: 建立国内官方来源索引**

在 `sources` 中分别建立来源项，不允许多个厂商共用一个模糊来源。至少使用：

- Huawei MIB Query：`https://info.support.huawei.com/info-finder/tool/zh/enterprise/mib`
- H3C MIB Search/产品 MIB Companion：`https://www.h3c.com/en/home/qr/default.htm?id=213`
- Ruijie RG-WALL sysObjectID 官方说明：`https://image.ruijie.com.cn/Upload/Article/fc9f828b-ac09-483b-90f9-1a8ad5e57c62/RG-WALL%E7%B3%BB%E5%88%97VPN%E5%AE%89%E5%85%A8%E7%BD%91%E5%85%B3%E4%BA%A7%E5%93%81%E4%B8%80%E6%9C%AC%E9%80%9A/RG-WALL%E7%B3%BB%E5%88%97VPN%E5%AE%89%E5%85%A8%E7%BD%91%E5%85%B3%E4%BA%A7%E5%93%81%E4%B8%80%E6%9C%AC%E9%80%9A/e500bfde-4e54-4b55-8f9f-344f8e20b0fe.htm`
- ZTE 官方 ZXR10/ZXCTN 产品 MIB 文档入口：`https://support.zte.com.cn/`
- Sangfor AF SNMP：`https://support.sangfor.com.cn/productDocument/read?category_id=179538&product_id=13&type=1&version_id=677`
- Sangfor AD 7.0.29 SNMP：`https://support.sangfor.com.cn/productDocument/read?category_id=358575&product_id=31&version_id=1155`
- Hillstone 官方镜像/MIB 下载入口：`https://images.hillstonenet.com/index/user/login.html`
- DPtech 官方支持入口：`https://www.dptech.com/`
- Topsec 下一代防火墙官方白皮书：`https://www.topsec.com.cn/uploads/2022-01-18/0e5c988b-b02d-4a36-8460-04451ea9cdb61642487890475.pdf`
- Venustech 官方产品入口：`https://www.venustech.com.cn/`

只有正文或附件实际包含产品身份 OID 的来源才写入 `sources`，并填写资料名称、版本/发布日期、`verified_at=2026-07-22` 和 `scope=product-identity`。登录受限、只说明支持 SNMP、只列监控指标或无法复核正文的入口写入 `coverage_gap_details`，不能被 `verified` 记录引用。

- [ ] **Step 3: 按产品身份节点提取交换机和路由器**

逐厂商只提取产品 MIB 中作为 sysObjectID 的 `OBJECT IDENTIFIER` 定义：

- Huawei：CloudEngine S/CE、NetEngine AR/NE。
- H3C：S5/S6/S9、MSR/SR/CR。
- Ruijie：RG-S、RG-RSR。
- ZTE：ZXR10 59/89/99、ZXR10 M6000、ZXCTN。

每次新增前检查完整 OID 是否已存在；已存在则依据新版官方资料原地纠正 `brand/model/FirstTypeId/source_id/verification`，不得创建 `.0` 别名。完成后运行国内覆盖测试，预期交换机/路由器部分从 FAIL 变 PASS。

- [ ] **Step 4: 按产品身份节点提取防火墙和负载均衡**

覆盖：Huawei USG/HiSecEngine、H3C F1000/M9000、Ruijie RG-WALL、Sangfor AF/AD、Hillstone SG/E/X/T、DPtech FW、Topsec NGFW、Venustech USG。只有官方资料将产品身份 OID 明确归入对应系列时才标记 `verified`。

对产品同时具备路由/安全能力的融合网关，以厂商产品分类和 SOID 产品节点为准；若资料无法确定四类之一，保留候选于研究记录但不写目录。

- [ ] **Step 5: 增加国内代表 OID 精确回归**

修改 `test_network_device_field_mapping_pure.py`：将原有三个确认 OID 保留，并扩充为每个具备公开来源的国内品牌至少一条。测试必须逐条断言完整 OID、规范品牌、型号、`FirstTypeId` 和 `verification == "verified"`，不使用条数或前缀代替精确证据。

- [ ] **Step 6: 运行目录和字段映射 GREEN**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_oid_catalog.py apps/cmdb/tests/test_network_device_field_mapping_pure.py
```

Expected: PASS；目录条数大于 Task 2 基线，每个国内必需品牌/类型均由 verified 精确 OID 或带官方入口和原因的显式缺口满足。

- [ ] **Step 7: 提交国内厂商目录**

```bash
git add server/apps/cmdb/support-files/systemoid.json server/apps/cmdb/support-files/systemoid.meta.json server/apps/cmdb/tests/test_oid_catalog.py server/apps/cmdb/tests/test_network_device_field_mapping_pure.py
git commit -m "data(cmdb): 丰富国内主流设备 SOID"
```

---

### Task 4: 补充国际主流厂商并完成有证据纠错

**Files:**
- Modify: `server/apps/cmdb/support-files/systemoid.json`
- Modify: `server/apps/cmdb/support-files/systemoid.meta.json`
- Modify: `server/apps/cmdb/tests/test_oid_catalog.py`
- Modify: `server/apps/cmdb/tests/test_network_device_field_mapping_pure.py`

**Interfaces:**
- Consumes: Task 3 的覆盖测试模式。
- Produces: 国际第二优先级厂商的 verified 产品映射和 `INTERNATIONAL_REQUIRED_FAMILIES` 合同。

- [ ] **Step 1: 写国际厂商 RED 覆盖矩阵**

```python
INTERNATIONAL_REQUIRED_FAMILIES = {
    "Cisco": {"switch", "router", "firewall"},
    "Juniper": {"switch", "router", "firewall"},
    "HPE": {"switch"},
    "Aruba": {"switch"},
    "Arista": {"switch"},
    "Fortinet": {"firewall"},
    "Palo Alto Networks": {"firewall"},
    "F5": {"loadbalance"},
    "Extreme": {"switch"},
    "Nokia": {"router"},
}
```

复用国内测试的精确聚合逻辑。Run Task 3 test command。Expected: FAIL，至少 Arista 和 Palo Alto Networks 当前无覆盖。

- [ ] **Step 2: 建立国际官方来源索引**

使用以下官方入口并记录实际产品 MIB 版本：

- Cisco：`https://github.com/cisco/cisco-mibs` 的 `CISCO-PRODUCTS-MIB`
- Juniper：产品 MIB 下载/`JUNIPER-CHASSIS-DEFINES-MIB`
- Aruba/HPE：Aruba Service Portal 对应 AOS-CX/AOS-S 产品 MIB
- Arista：`https://www.arista.com/en/support/product-documentation/arista-snmp-mibs` 的 `ARISTA-PRODUCTS-MIB`
- Fortinet：FortiOS `FORTINET-FORTIGATE-MIB`
- Palo Alto Networks：`PAN-PRODUCT-MIB`
- F5：官方 `F5-BIGIP-SYSTEM-MIB`
- Extreme 官方支持入口：`https://extreme-networks.my.site.com/ExtrSupportHome`
- Nokia 产品文档入口：`https://documentation.nokia.com/`

厂商页面仅证明“支持 MIB”但未给产品身份定义时，继续打开其产品 MIB 文件核对，不能直接把监控节点写成 SOID。

- [ ] **Step 3: 提取并纠正交换机/路由器产品 OID**

覆盖 Cisco Catalyst/Nexus/ISR/ASR、Juniper EX/QFX/MX/PTX、Aruba CX/ProCurve、Arista 7000/7200/7300、Extreme、Nokia SR。对目录中已有但使用旧品牌或 MIB symbol 拼写错误的同一 OID原地纠正；保留数据库识别所需的完整 OID，不增加企业号前缀规则。

- [ ] **Step 4: 提取并纠正安全/负载均衡产品 OID**

覆盖 Cisco Firepower/ASA、Juniper SRX、FortiGate、Palo Alto PA/VM-Series、F5 BIG-IP。F5 产品身份若按平台而非业务模块定义，统一映射到现有 `loadbalance`，不得把 F5 普通指标树根当产品型号。

- [ ] **Step 5: 增加国际代表 OID 精确回归并跑 GREEN**

对每条已经取得产品身份来源的品牌/类型，选择至少一条目录内的完整数字 OID，逐条断言品牌、型号、类型、`source_id` 和 `verified`；没有可复核产品身份来源的类型必须进入 `coverage_gaps` 与 `coverage_gap_details`。运行 Task 3 联合测试命令，Expected: PASS。

- [ ] **Step 6: 提交国际厂商目录**

```bash
git add server/apps/cmdb/support-files/systemoid.json server/apps/cmdb/support-files/systemoid.meta.json server/apps/cmdb/tests/test_oid_catalog.py server/apps/cmdb/tests/test_network_device_field_mapping_pure.py
git commit -m "data(cmdb): 丰富国际主流设备 SOID"
```

---

### Task 5: 实现非破坏、幂等的目录同步服务

**Files:**
- Modify: `server/apps/cmdb/services/oid_catalog.py`
- Modify: `server/apps/cmdb/tests/test_oid_catalog.py`

**Interfaces:**
- Consumes: `Mapping[str, OidCatalogEntry]`、`OidMapping` ORM。
- Produces: `sync_oid_catalog(entries, dry_run=False) -> OidSyncResult`。

- [ ] **Step 1: 写存量新增、内置更新与用户覆盖 RED 测试**

```python
from dataclasses import replace

import pytest

from apps.cmdb.models import OidMapping
from apps.cmdb.services.oid_catalog import OidCatalogEntry, sync_oid_catalog

pytestmark = pytest.mark.django_db


def _catalog_entry(oid, *, model="S5735", brand="Huawei", device_type="switch"):
    return OidCatalogEntry(
        oid=oid,
        model=model,
        brand=brand,
        device_type=device_type,
        source_id="test-source",
        verification="verified",
    )


def test_sync_adds_missing_entry_when_builtin_rows_already_exist():
    OidMapping.objects.create(oid="1.3.6.1.4.1.9.1.1208", model="old", brand="Cisco", device_type="switch", built_in=True)
    new_oid = "1.3.6.1.4.1.2011.2.23.968"

    result = sync_oid_catalog({new_oid: _catalog_entry(new_oid)})

    assert result.created == 1
    assert OidMapping.objects.get(oid=new_oid).built_in is True


def test_sync_updates_builtin_in_place_but_preserves_custom_override():
    builtin = OidMapping.objects.create(oid="1.3.6.1.4.1.9.1.1", model="old", brand="old", device_type="router", built_in=True)
    custom = OidMapping.objects.create(oid="1.3.6.1.4.1.9.1.2", model="custom", brand="custom", device_type="router", built_in=False)
    entries = {
        builtin.oid: _catalog_entry(builtin.oid, model="new", brand="Cisco", device_type="switch"),
        custom.oid: _catalog_entry(custom.oid, model="catalog", brand="Cisco", device_type="switch"),
    }

    result = sync_oid_catalog(entries)

    builtin.refresh_from_db()
    custom.refresh_from_db()
    assert (builtin.model, builtin.brand, builtin.device_type, builtin.id) == ("new", "Cisco", "switch", builtin.id)
    assert (custom.model, custom.brand, custom.device_type) == ("custom", "custom", "router")
    assert result.custom_override_oids == (custom.oid,)
```

- [ ] **Step 2: 运行 RED，确认 `sync_oid_catalog` 尚不存在**

Run Task 1 test command。Expected: FAIL with `cannot import name 'sync_oid_catalog'`。

- [ ] **Step 3: 实现一次查询、稳定分类和事务批量写入**

在 `oid_catalog.py` 增加：

```python
from django.db import transaction
from django.utils import timezone

from apps.cmdb.models import OidMapping


def sync_oid_catalog(
    entries: Mapping[str, OidCatalogEntry],
    *,
    dry_run: bool = False,
) -> OidSyncResult:
    if dry_run:
        return _sync_oid_catalog(entries, write=False)
    with transaction.atomic():
        return _sync_oid_catalog(entries, write=True)


def _sync_oid_catalog(
    entries: Mapping[str, OidCatalogEntry],
    *,
    write: bool,
) -> OidSyncResult:
    queryset = OidMapping._default_manager.all()
    if write:
        queryset = queryset.select_for_update()
    existing = {row.oid: row for row in queryset}
    to_create = []
    to_update = []
    unchanged = 0
    custom_override_oids = []
    now = timezone.now()

    for oid in sorted(entries, key=lambda value: tuple(int(part) for part in value.split("."))):
        entry = entries[oid]
        row = existing.get(oid)
        if row is None:
            to_create.append(
                OidMapping(
                    oid=oid,
                    model=entry.model,
                    brand=entry.brand,
                    device_type=entry.device_type,
                    built_in=True,
                )
            )
            continue
        if not row.built_in:
            custom_override_oids.append(oid)
            continue
        values = (row.model, row.brand, row.device_type)
        desired = (entry.model, entry.brand, entry.device_type)
        if values == desired:
            unchanged += 1
            continue
        row.model, row.brand, row.device_type = desired
        row.updated_at = now
        to_update.append(row)

    stale_builtin_oids = tuple(
        sorted(
            (oid for oid, row in existing.items() if row.built_in and oid not in entries),
            key=lambda value: tuple(int(part) for part in value.split(".")),
        )
    )
    if write:
        OidMapping._default_manager.bulk_create(to_create, batch_size=500)
        OidMapping._default_manager.bulk_update(
            to_update,
            ["model", "brand", "device_type", "updated_at"],
            batch_size=500,
        )
    return OidSyncResult(
        created=len(to_create),
        updated=len(to_update),
        unchanged=unchanged,
        custom_override_oids=tuple(custom_override_oids),
        stale_builtin_oids=stale_builtin_oids,
    )
```

不要使用 `update_or_create` 循环，避免每个 OID 多次查询；不要使用 `ignore_conflicts=True` 吞掉计划与写入之间的异常。

- [ ] **Step 4: 增加 dry-run、幂等、时间戳、遗留与回滚合同**

新增以下独立测试：

- `dry_run=True` 返回新增/更新计数但数据库零变化。
- 连续同步两次，第二次 `created=updated=0`，`unchanged` 等于目录中未被用户覆盖的数量。
- 未变化记录的 `updated_at` 保持原值。
- 目录外内置记录出现在 `stale_builtin_oids` 且仍存在。
- monkeypatch `bulk_update` 抛出 `RuntimeError` 时，本事务内的 `bulk_create` 也回滚。
- 结果中的 OID 使用数字段排序。
- 真实写入路径对已有行使用 `select_for_update`；dry-run 不申请行锁。

- [ ] **Step 5: 跑服务测试和覆盖率门禁**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' --cov=apps.cmdb.services.oid_catalog --cov-report=term-missing --cov-fail-under=75 apps/cmdb/tests/test_oid_catalog.py
```

Expected: PASS，`oid_catalog.py` coverage ≥ 75%。

- [ ] **Step 6: 提交同步服务**

```bash
git add server/apps/cmdb/services/oid_catalog.py server/apps/cmdb/tests/test_oid_catalog.py
git commit -m "feat(cmdb): 安全同步内置 SOID 目录"
```

---

### Task 6: 将 `init_oid` 改为安全同步命令

**Files:**
- Modify: `server/apps/cmdb/management/commands/init_oid.py`
- Create: `server/apps/cmdb/tests/test_init_oid_command.py`

**Interfaces:**
- Consumes: `load_oid_catalog()`、`sync_oid_catalog(entries, dry_run=...)`。
- Produces: `manage.py init_oid [--dry-run] [--force]` 和稳定五类统计输出。

- [ ] **Step 1: 写默认存量同步、dry-run 和 force 非删除 RED 测试**

```python
from io import StringIO

import pytest
from django.core.management import call_command

from apps.cmdb.models import OidMapping

pytestmark = pytest.mark.django_db


def _run(*args):
    output = StringIO()
    call_command("init_oid", *args, stdout=output, stderr=output)
    return output.getvalue()


def test_default_command_syncs_catalog_into_nonempty_database():
    OidMapping.objects.create(oid="1.3.6.1.4.1.99999.1", model="legacy", brand="Legacy", device_type="switch", built_in=True)

    output = _run()

    assert OidMapping.objects.filter(built_in=True).count() > 1
    assert "新增=" in output
    assert OidMapping.objects.filter(oid="1.3.6.1.4.1.99999.1").exists()


def test_dry_run_reports_without_writes():
    before = OidMapping.objects.count()
    output = _run("--dry-run")
    assert OidMapping.objects.count() == before
    assert "DRY-RUN" in output


def test_force_never_deletes_stale_builtin():
    stale = OidMapping.objects.create(oid="1.3.6.1.4.1.99999.2", model="stale", brand="Legacy", device_type="switch", built_in=True)
    _run("--force")
    assert OidMapping.objects.filter(pk=stale.pk).exists()
```

- [ ] **Step 2: 运行 RED，确认旧命令仍整体跳过且 force 会删除**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_init_oid_command.py
```

Expected: 至少默认同步和 `--force` 保护测试 FAIL。

- [ ] **Step 3: 将命令缩减为参数、服务调用和输出适配**

`init_oid.py` 保留 `Command` 类，删除手工文件读取、存在即跳过、删除和直接 `bulk_create` 逻辑：

```python
from django.core.management import BaseCommand
from django.core.management.base import CommandError

from apps.cmdb.services.oid_catalog import OidCatalogError, load_oid_catalog, sync_oid_catalog
from apps.core.logger import cmdb_logger as logger


class Command(BaseCommand):
    help = "校验并同步网络设备 SOID 内置映射"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="仅输出差异，不写数据库")
        parser.add_argument("--force", action="store_true", help="兼容参数：重新比较完整目录，不删除数据")

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        if options["force"]:
            self.stdout.write(self.style.WARNING("--force 已改为安全全量比较，不会删除内置记录"))
        try:
            entries = load_oid_catalog()
            result = sync_oid_catalog(entries, dry_run=dry_run)
        except OidCatalogError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            logger.error("OID_SYNC_FAILED")
            raise CommandError("OID_SYNC_FAILED") from exc

        prefix = "DRY-RUN " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}SOID同步完成: 新增={result.created}, 更新={result.updated}, "
                f"未变化={result.unchanged}, 用户覆盖={len(result.custom_override_oids)}, "
                f"目录外遗留={len(result.stale_builtin_oids)}"
            )
        )
```

- [ ] **Step 4: 增加稳定错误、幂等与输出精确测试**

测试以下行为：

- monkeypatch `load_oid_catalog` 抛 `OidCatalogError("OID_CATALOG_INVALID")`，命令保留该稳定码。
- monkeypatch `sync_oid_catalog` 抛含 `credential=secret` 的异常，同时 mock `logger.error`；断言用户可见 `CommandError` 只含 `OID_SYNC_FAILED`，日志调用严格等于 `logger.error("OID_SYNC_FAILED")` 且不带 `exc_info`。
- 重复运行两次，第二次输出 `新增=0, 更新=0`。
- 创建 `built_in=False` 的生产目录同 OID 后，输出 `用户覆盖=1` 且记录不变。
- `--dry-run --force` 同时使用仍零写入并输出兼容提示。

- [ ] **Step 5: 跑管理命令 GREEN 和 batch_init 回归**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_init_oid_command.py apps/core/tests/test_batch_init_command.py
```

Expected: PASS；`batch_init` 仍恰好调用一次 `init_oid`。

- [ ] **Step 6: 提交管理命令**

```bash
git add server/apps/cmdb/management/commands/init_oid.py server/apps/cmdb/tests/test_init_oid_command.py
git commit -m "feat(cmdb): 让 SOID 初始化支持安全增量同步"
```

---

### Task 7: 锁定采集兼容、更新文档并完成发布验证

**Files:**
- Modify: `server/apps/cmdb/tests/test_network_device_field_mapping_pure.py`
- Modify: `server/apps/cmdb/support-files/plugins_doc/network.md`
- Test: `server/apps/cmdb/tests/e2e/test_network_pipeline.py`

**Interfaces:**
- Consumes: 已同步的 `OidMapping` 与现有 `CollectNetworkMetrics.get_oid_map/format_data`。
- Produces: 四类映射、未知回退、自定义覆盖的回归证据和运维说明。

- [ ] **Step 1: 写四类设备与未知 OID 行为回归**

在纯测试中从生产目录精确选择四条 `verified` OID：交换机、路由器、防火墙、负载均衡各一条，并断言其 `FirstTypeId.lower()` 与预期模型完全一致。保留现有 Cisco `1.3.6.1.4.1.9.1.1208` E2E 样本，不修改采集实现。

为 `CollectNetworkMetrics.get_default_oid_map("1.3.6.1.4.1.99999.999")` 增加断言：

```python
assert CollectNetworkMetrics.get_default_oid_map("1.3.6.1.4.1.99999.999") == {
    "model": "未知",
    "oid": "1.3.6.1.4.1.99999.999",
    "brand": "未知",
    "device_type": "switch",
    "built_in": False,
}
```

- [ ] **Step 2: 运行定向采集回归**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_network_device_field_mapping_pure.py apps/cmdb/tests/e2e/test_network_pipeline.py
```

Expected: PASS；现有网络 E2E 不因目录与同步服务变化而修改预期。

- [ ] **Step 3: 更新网络插件文档**

在 `network.md` 的 SOID 说明后增加：

```markdown
### SOID 匹配与目录同步

- 设备品牌、型号和类型只按完整 `sysObjectID` 精确匹配，不按厂商前缀或 `sysDescr` 猜测。
- 内置目录来自厂商官方产品 MIB；缺少公开证据的历史记录仅作为兼容数据保留。
- 升级前可执行 `python manage.py init_oid --dry-run` 查看新增、更新、用户覆盖和目录外遗留。
- 正常 `batch_init` 会幂等同步内置目录；用户在 SOID 管理中维护的自定义记录始终优先。
- `--force` 为兼容参数，不会删除或重建内置记录。
```

- [ ] **Step 4: 运行目录、命令、采集组合回归与覆盖率**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' --cov=apps.cmdb.services.oid_catalog --cov=apps.cmdb.management.commands.init_oid --cov-report=term-missing --cov-fail-under=75 apps/cmdb/tests/test_oid_catalog.py apps/cmdb/tests/test_init_oid_command.py apps/cmdb/tests/test_network_device_field_mapping_pure.py apps/cmdb/tests/e2e/test_network_pipeline.py apps/core/tests/test_batch_init_command.py
```

Expected: PASS，触及代码 coverage ≥ 75%。

- [ ] **Step 5: 运行静态、迁移和数据完整性检查**

```bash
cd server
uv run black --check apps/cmdb/services/oid_catalog.py apps/cmdb/management/commands/init_oid.py apps/cmdb/tests/test_oid_catalog.py apps/cmdb/tests/test_init_oid_command.py apps/cmdb/tests/test_network_device_field_mapping_pure.py
uv run isort --check-only apps/cmdb/services/oid_catalog.py apps/cmdb/management/commands/init_oid.py apps/cmdb/tests/test_oid_catalog.py apps/cmdb/tests/test_init_oid_command.py apps/cmdb/tests/test_network_device_field_mapping_pure.py
uv run flake8 apps/cmdb/services/oid_catalog.py apps/cmdb/management/commands/init_oid.py apps/cmdb/tests/test_oid_catalog.py apps/cmdb/tests/test_init_oid_command.py apps/cmdb/tests/test_network_device_field_mapping_pure.py
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run python manage.py makemigrations --check --dry-run --skip-checks
jq empty apps/cmdb/support-files/systemoid.json
jq empty apps/cmdb/support-files/systemoid.meta.json
```

Expected: 所有命令退出码 0；`makemigrations` 输出 `No changes detected`。

- [ ] **Step 6: 执行发布前 dry-run 烟测**

在测试数据库运行：

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run python manage.py init_oid --dry-run --skip-checks
```

Expected: 输出五类计数；再次执行输出一致；数据库 `OidMapping` 数量不变。

- [ ] **Step 7: 提交文档与最终回归**

```bash
git add server/apps/cmdb/tests/test_network_device_field_mapping_pure.py server/apps/cmdb/support-files/plugins_doc/network.md
git commit -m "test(cmdb): 锁定 SOID 同步与采集兼容合同"
```

---

## 最终验收清单

- [ ] 生产目录不少于原 1,966 条，所有记录均能通过严格加载。
- [ ] 每条记录都有有效 `source_id` 和 `verification`。
- [ ] `verified` 记录只引用可复核的官方来源；受限来源进入 `coverage_gaps`。
- [ ] 国内与国际覆盖矩阵满足设计范围。
- [ ] 默认命令可向非空存量库新增和更新内置映射。
- [ ] 用户自定义记录、目录外内置记录和既有数据库主键保持不变。
- [ ] `--dry-run` 零写入，`--force` 不删除，重复执行幂等。
- [ ] 四类采集映射和未知 OID 回退均通过回归。
- [ ] 定向测试、覆盖率、静态检查、迁移检查和 JSON 解析全部通过。
- [ ] `git diff --check` 无空白错误，提交中不包含用户现有无关文件。
