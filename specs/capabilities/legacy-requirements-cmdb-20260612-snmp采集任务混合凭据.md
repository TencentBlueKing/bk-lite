# SNMP 采集任务支持混合凭据（V2/V2c/V3 混用）

> Migrated from `spec/requirements/CMDB/20260612.SNMP采集任务混合凭据.md` as legacy capability evidence.

> 评估与改动方案（最小化版本）。结论：底层链路早已支持混合版本，只需放开 Server 端一处入库校验。

## 1. 背景与问题

CMDB 采集任务已具备"任务内多凭据池"能力（见 [20260602.CMDB采集任务多凭据.md](20260602.CMDB采集任务多凭据.md)）。但其第 4 条约束"同一任务内的多凭据必须保证协议一致、鉴权方式一致、字段结构一致"，落到代码即 `validate_pool_shape()` 要求池内所有凭据字段集合完全相同。这导致 SNMP 场景下 **v2c（字段 `community`）与 v3（字段 `username/authkey/privkey/...`）无法放进同一任务**，用户被迫按版本拆任务。

本需求在**仅 SNMP 采集任务**范围内放开该约束，允许一个任务的凭据池混合 v2/v2c/v3；**其他采集类型（SSH/数据库/云等）维持原约束不变**。

## 2. 现状评估：底层已就绪，只差一道入库校验

逐层走查，混合凭据能力**已经具备**，无需改动：

| 层 | 位置 | 现状 |
|---|---|---|
| 存储 | [collect_model.py:91](../../../server/apps/cmdb/models/collect_model.py) `credential = JSONField(default=list)` | 有序列表，每条凭据**自带 `version`** |
| 下发 | [node_configs/network/network.py:77](../../../server/apps/cmdb/node_configs/network/network.py)、[base.py:133](../../../server/apps/cmdb/node_configs/base.py) | 每条凭据输出**全字段同构**配置（v2c+v3 并集，按 index 占位密钥），随 `cmdbcredential_N_*` 平铺下发 |
| agent 轮询 | [stargazer/api/collect.py:159](../../../agents/stargazer/api/collect.py) `_build_collect_task_candidates` | `{**base, **credential, ...}` 每条凭据整体展开成独立候选任务，带各自 `version` |
| SNMP 认证 | [snmp_topo.py:80](../../../agents/stargazer/plugins/inputs/network_topo/snmp_topo.py) `SnmpAuth`、[snmp_facts.py:84](../../../agents/stargazer/plugins/inputs/network/snmp_facts.py) `_validate_params` | 认证构建与校验均包在 `if version=="v3"` 分支内，v2c 候选不触碰 authkey，无崩溃风险 |
| 前端 | [credentialPoolEditor.tsx:267](../../../web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx) | 每条凭据**已是独立 version 下拉**，无跨行"必须一致"约束 |

**整条链路无任何"任务级统一 version"假设。** 唯一拦路点是 Server 端 [collect_credential_pool_service.py:35-51](../../../server/apps/cmdb/services/collect_credential_pool_service.py) `validate_pool_shape()` 的字段集合相等检查（create/update 时调用），它把 v2c 与 v3 判为"字段不一致"而打回。

## 3. 需求项

1. SNMP 凭据池（**判别依据：池内每条凭据都带非空 `version` 字段**）放开字段一致约束，允许混合 v2/v2c/v3。
2. SNMP 凭据池改用 **version 感知的必填字段校验**（与 agent 侧 `SnmpAuth.validate` 对齐）：
   - `v2`/`v2c`：必须有 `community`。
   - `v3`：必须有 `username`；`authNoPriv`/`authPriv` 另需 `integrity`+`authkey`；`authPriv` 再需 `privacy`+`privkey`。
   - 不满足 → 拒绝保存，报错指明第几组缺什么。
3. **非 SNMP 采集类型（SSH/数据库/云等，凭据不带 version）维持原"字段结构一致"约束，零改动。**

## 4. 改动清单（最小化）

> 范围备注：本次改动**只作用于 SNMP 网络采集任务**。判别完全依赖"凭据是否带 `version` 字段"——经核查，全仓非 SNMP 凭据（SSH `port/username/password`、数据库 `port/user/password`、云 `accessKey/accessSecret`）均不含 `version`，因此其他任务自然落入原校验分支、行为不变。无需改动函数签名或调用点。

**唯一代码改动**：[collect_credential_pool_service.py](../../../server/apps/cmdb/services/collect_credential_pool_service.py) 重写 `validate_pool_shape` 函数体 + 新增私有 helper `_validate_snmp_credential`：

```python
@classmethod
def validate_pool_shape(cls, pool):
    if not pool:
        raise BaseAppException("采集凭据不能为空！")
    if len(pool) > cls.MAX_POOL_SIZE:
        raise BaseAppException("采集凭据最多支持3组！")
    for item in pool:
        if not isinstance(item, dict):
            raise BaseAppException("采集凭据格式错误！")

    # 仅 SNMP：凭据自带 version → 按各自版本校验必填项，允许 v2/v2c/v3 混用
    if all(item.get("version") for item in pool):
        for index, item in enumerate(pool):
            cls._validate_snmp_credential(item, index)
        return

    # 其他采集类型（SSH/数据库/云，无 version）：维持原"字段结构一致"约束
    expected_keys = None
    for item in pool:
        item_keys = set(item.keys()) - {"credential_id"}
        if expected_keys is None:
            expected_keys = item_keys
        elif item_keys != expected_keys:
            raise BaseAppException("同一任务的采集凭据字段必须保持一致！")

@classmethod
def _validate_snmp_credential(cls, cred, index):
    label = f"第 {index + 1} 组凭据"
    version = str(cred.get("version", "")).lower()
    if version in ("v2", "v2c"):
        if not cred.get("community"):
            raise BaseAppException(f"{label}（{version}）缺少团体字！")
    elif version == "v3":
        if not cred.get("username"):
            raise BaseAppException(f"{label}（v3）缺少用户名！")
        level = str(cred.get("level", "")).lower()
        if level in ("authnopriv", "authpriv") and (not cred.get("integrity") or not cred.get("authkey")):
            raise BaseAppException(f"{label}（v3/{level}）缺少 integrity 或 authkey！")
        if level == "authpriv" and (not cred.get("privacy") or not cred.get("privkey")):
            raise BaseAppException(f"{label}（v3/authPriv）缺少 privacy 或 privkey！")
    else:
        raise BaseAppException(f"{label} 的 SNMP 版本 {version} 不支持！")
```

**不改动**：函数签名、两处调用点（[collect_service.py:400](../../../server/apps/cmdb/services/collect_service.py)、[:461](../../../server/apps/cmdb/services/collect_service.py)）、前端、agent、下发层、数据模型。

**Spec**：[20260602.CMDB采集任务多凭据.md:51](20260602.CMDB采集任务多凭据.md) 第 4 条追加一行备注——SNMP 例外（混合 version 允许，但每条仍需满足该 version 的字段完整性），互链本文。

## 5. 验收口径

1. SNMP 任务可保存**同时含 v2c 与 v3** 的凭据池并正常执行；agent 按池内顺序逐条尝试、命中后缓存 `credential_id`。
2. 混合池中 v3 凭据缺 `authkey`（authPriv）时，保存被拒，报错指明第几组缺什么。
3. **非 SNMP** 任务混合不同结构凭据时，仍按原约束被拒（回归保护）。
4. 老的单凭据 / 同 version 多凭据任务行为不变（向后兼容）。
5. 既有多凭据测试（[server test_collect_multicred.py](../../../server/apps/cmdb/tests/test_collect_multicred.py)、[test_collect_model_credential_pool.py](../../../server/apps/cmdb/tests/test_collect_model_credential_pool.py)、[test_node_params_multicred.py](../../../server/apps/cmdb/tests/test_node_params_multicred.py)）全部不回归；新增校验用例覆盖需求项 1/2/3。

## 6. 约束与边界

**In Scope**：仅 `validate_pool_shape` 一处函数（+ helper + 测试）、spec 一行备注。

**Out of Scope**：
- 其他采集类型（SSH/数据库/云）凭据约束——维持现状。
- 前端校验补强——后端已给清晰报错，本次不做（可作为后续体验优化）。
- agent 轮询/命中缓存/认证层、数据模型、下发层——不动。
- 函数签名与调用点——不改（靠 `version` 判别符自然分流）。

## 7. 风险与备注

- 判别符为隐式约定（"凭据带 version 即 SNMP"）。已核查全仓非 SNMP 凭据均不含 `version`；若未来新增带 `version` 的非 SNMP 凭据类型，需回看此处。`all(...)` 取"全部带 version 才算 SNMP 池"，单条缺失会安全落入旧校验分支。
- `_validate_snmp_credential` 的 v3 必填规则与 agent `SnmpAuth.validate` 对齐，避免入库放行、运行时才崩。
- 工作量：单文件单函数 + helper + 测试 + spec 一行。**agent、下发、前端、调用点零改动。**
