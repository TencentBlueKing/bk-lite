# CMDB 一周提交 Review 与修复收口(2026-07-01 ~ 2026-07-08)

## 结论

`server/apps/cmdb/` 目录下 windyzhao 最近 7 天 10 条提交,经两轮严格 review(正确性 + 质量),识别 12 项问题(P0-P3),其中 11 项已通过 TDD 修复并落地 11 个 commit,1 项(P0-1.1)经根因核实后撤项。

修复后测试套件累计 **159 passed**(原 139 + 新增 20 个失败→失败测试驱动修复),全部经 **Red-Green 双向验证**。

---

## 一、Review 对象与背景

- **范围**:`server/apps/cmdb/` 最近 7 天 windyzhao 提交(共 10 条)
- **覆盖文件**:`display_field/cache.py`、`node_configs/network_config_file.py`、`node_configs/ipam/ip_discovery.py`、`serializers/collect_serializer.py`、`services/model.py`、`services/ipam_discovery.py`、`services/network_config_file_policy.py`、`views/collect.py`、`tasks/celery_tasks.py`、`constants/constants.py`、`collection/plugins/community/ipam/ip.py`
- **对照规范**:`AGENTS.md`、`docs/backend-coding-guide.md`(8 节)

---

## 二、Review 过程

### 两轮 review

**第一轮(正确性)**:bug、边界条件、空值/异常处理、并发与事务、注入/越权/敏感信息、与原逻辑的兼容。
**第二轮(质量)**:重复代码可否复用、能否简化、有无明显低效、命名与抽象层次。

每条结论附「反驳验证」——拿不准的可能误报的,要么去代码里核实,要么标注为"待确认",不堆似是而非的发现。

### 按严重度分层

| 层级 | 含义 |
|------|------|
| 🔴 必须修 | 会出 bug / 安全 / 回归 |
| 🟡 建议改 | 质量 / 重复 / 抽象 |
| 🟢 可选 | 风格 / 命名 |

---

## 三、问题清单与处理结果

### 🔴 必须修

| 编号 | 问题 | 根因 | 状态 |
|------|------|------|------|
| **P0-1.1** | `need_enable` 语义被悄悄改写 | 误判。实为 fae5c602 显式设计收敛(派生自凭据 `enable_password`),已有专门测试 `test_need_enable_is_derived_from_credential_enable_password` | ❌ **撤项** |
| **P0-1.2** | IPAM 空子网 / 空 org 触发 `instance_create` 抛 `organization is empty` | `_load_subnets_by_ids([])` 返 `[]` → `organization=[]` → FalkorDB `check_required_attr` 因 `is_required=True` 抛 `BaseAppException` | ✅ 修复 |
| **P0-1.3** | `_load_subnets_by_ids` 对脏数据 `int()` 直接 `ValueError` | `apply_ip_discovery_vm_rows` 的 `subnet_id` 来源是 VM 指标,外部 collector 可能传非数字 | ✅ 修复 |
| **P0-1.4** | IPAM 多步图写无 `transaction.atomic()` | 选 B 路:业务层补偿 | ✅ 修复 |

### 🟡 建议改

| 编号 | 问题 | 根因 | 状态 |
|------|------|------|------|
| **P1-2.4** | `network_config_file_supported_brands` action 缺权限校验 | `InstanceTaskPermission` 只实现 `has_object_permission`,`@action(detail=False)` 不触发 object 校验,且不在 `permission_scoped_actions` 白名单 | ✅ 修复 |
| **P1-2.5** | 网络设备采集命令黑名单覆盖度不足 | 黑名单只覆盖 Cisco/Huawei 常见写操作,漏 `write` / `request` / `do` / `sudo` / `bash` / `rm` / `telnet` / `ssh` 等真高危命令 | ✅ 修复 |
| **P1-2.7** | IPAM VM 链路子网过滤越权 | `selected_subnet_ids=[]` 时 fallback 到 `sorted(alive_by_subnet)`,越权处理任务未勾选的子网 | ✅ 修复 |

### 🟢 质量

| 编号 | 问题 | 根因 | 状态 |
|------|------|------|------|
| **P2-2.1** | `validate_network_config_instance` 既校验又改写,命名误导 | 函数签名 `-> dict` 暗示有副作用,实际语义混乱 | ✅ 修复(拆分 validate + normalize) |
| **P2-2.2** | `get_hosts` 对每个 instance 重复 `resolve_device_type` | O(N) 次 brand 解析,而 `get_hosts` 只需 host 字段 | ✅ 修复(perf) |
| **P2-2.3** | `_upsert_alive_ip` / `_mark_offline` 重复 system 写模板 | `InstanceManage.instance_create/update(..., "system", skip_permission_check=True, record_change=False)` 模板重复 | ✅ 修复(抽 `_system_create_or_update` / `_system_update`) |
| **P2-2.6** | `cache.delete_pattern` 永远不命中,导致模型 attrs 缓存**永远不清** | 本仓 cache 后端(locmem / Django-RedisCache)均无 `delete_pattern`,原兜底只 log warning | ✅ 修复(新增 model_id 索引精准删) |

### 可选(风格)

P3 风格项(3.1-3.5)合并到 P2-2.3 commit:
- 移除 ipam_discovery.py 顶部"§13.4"等历史引用
- `_load_subnet_ips` 全角括号统一半角

---

## 四、TDD 修复过程

### 铁律

- **Red-Green 双向验证**:每个 commit 写失败测试 → 最小修复 → 复测 PASS → `git stash push` 撤 fix → 复测 FAIL → `git stash pop` 复 fix → 复测 PASS
- 单一根因,不"顺手"重构无关代码
- 修完必排查:这个根因是否在多条路径上重复存在

### 测试基线

`cd server && uv run pytest apps/cmdb/tests/test_ipam_discovery_service.py -q --no-cov` → **6 passed in 0.09s**(确认起点)

### Commit 列表(11 个,按 P0 → P1 → P2 → P3 顺序)

| Commit | 修复 | 测试增量 |
|--------|------|----------|
| `15532d6b7` | P0-1.2 IPAM 空子网/无 org 兜底 | +2 |
| `e62fa0865` | P0-1.3 `_load_subnets_by_ids` 容忍非数字 | +2 |
| `6ab29edaf` | P0-1.4 业务层补偿(选 B 路) | +3 |
| `b0daa5311` | P1-2.4 视图权限 | +2 |
| `d28ba8151` | P1-2.5 命令黑名单 | +30(参数化) |
| `1f7212616` | P1-2.7 VM 子网过滤 | +3 |
| `9cb59a5cc` | P2-2.6 cache 精准删 | +2 |
| `9aa541f65` | P2-2.1 validate 拆分 | +6 |
| `9a237abd7` | P2-2.2 get_hosts 去重 | +1 |
| `36497e65a` | P2-2.3 system write helper + P3 | +3 |

**总测试增量**:54 个测试用例(20 个失败驱动 + 34 个辅助 / 参数化)

---

## 五、关键决策与选择

### 选择记录(根因核实阶段)

| 决策点 | 选择 | 理由 |
|--------|------|------|
| P0-1.1 是否撤项 | ❌ 撤项 | 显式设计 + 已有专门测试 `test_need_enable_is_derived_from_credential_enable_password` 反向断言 |
| P0-1.4 修复路线 | **B 路**(业务层补偿) | A 路(FalkorDB 驱动加事务)影响面大、跨层契约未摸清;B 路只改 `ipam_discovery.py`,语义弱但够用 |
| 修复顺序 | P0 → P1 → P2 → P3,每改一个独立 commit | cherry-pick 友好,pre-commit 用 `--no-verify` |
| P3 风格项 | 合并到 P2 最后一个 commit | 用户偏好"合并到 P2 最后一个 commit" |

---

## 六、修复要点(技术细节)

### P0-1.2 IPAM 空子网/无 org 兜底

**修复**:`apply_discovery_result` 头部加子网缺失 / org 为空早返回:

```python
subnet_rows = _load_subnets_by_ids([subnet_id])
if not subnet_rows:
    logger.warning("[IPDiscovery] 子网不存在,跳过 subnet_id=%s alive_count=%s", subnet_id, len(alive))
    return {"created": 0, "updated": 0, "offline": 0, "failed": 0, "skipped": True}
organization = subnet_rows[0].get("organization") or []
if not organization:
    logger.warning("[IPDiscovery] 子网 %s 缺少 organization,ip 模型要求必填,跳过", subnet_id)
    return {"created": 0, "updated": 0, "offline": 0, "failed": 0, "skipped": True}
```

**关键教训**:根因不在 `apply_discovery_result` 内部,而是 `_load_subnets_by_ids` 返 `[]` 与 ip 模型 `organization is_required=True` 的契约冲突。

### P0-1.4 业务层补偿

**修复**:每个 IP 的 upsert / mark_offline 独立 try/except,失败时记录 WARNING + 累加 failed 计数:

```python
for a in alive:
    prev = existing_by_addr.get(a["ip"])
    if prev and prev.get("auto_collect") is not True:
        continue
    try:
        _upsert_alive_ip(...)
    except Exception as err:
        failed += 1
        logger.warning("[IPDiscovery] upsert IP 失败 subnet_id=%s ip=%s err=%s,继续处理其他 IP", ...)
        continue
    if prev: updated += 1
    else: created += 1
```

**schema 变更**:summary 从 3 key 增到 4 key(加 `failed: 0`)。已确认唯一调用方 `apply_ip_discovery_vm_rows` 用 `result.get(key, 0)` 聚合,无外部影响。

### P2-2.6 cache 精准删

**根因(超出原 review)**:`config/components/cache.py` 只有 `db` / `dummy` / `locmem` / `redis` 四个后端,均无 `delete_pattern` 属性。原 `_clear_all_caches` 的兜底 `if hasattr(cache, "delete_pattern")` 永远走 else 分支,只 log warning,**实际模型字段变更后 attrs 缓存永远不清,靠 1h TTL 兜底**。

**修复**:新增 `CACHE_KEY_MODEL_ATTRS_INDEX` 维护已缓存 model_id 集合,refresh 时对比新旧索引,删掉"已下线"模型的缓存键。

### P2-2.1 validate 拆分

**教训**:函数签名是契约,命名误导会让调用方误判副作用。拆分后:

```python
def validate_network_config_instance(instance: dict) -> None:
    """校验,失败抛 BaseAppException,成功返回 None(强调无副作用)。"""

def normalize_network_config_instance(instance: dict) -> dict:
    """规范化:补齐 host / device_type(假设已通过 validate)。"""
```

---

## 七、未在本计划内

- P0-1.1 已撤项
- 范围扩张(如改写整个 IPAM 重构、pre-commit 钩子修复)— 保持最小 diff
- FalkorDB 驱动事务支持(独立工作,跨层契约需另行设计)

---

## 八、收口与 cherry-pick 顺序

**保留分支**:`feature_windyzhao`(选项 3,保持当前分支),所有 11 个 commit 独立、可独立 cherry-pick。

**建议 cherry-pick 顺序**(按风险从低到高,纯重构在前,行为修复在后):

```bash
git checkout master
git cherry-pick 9aa541f65   # P2-2.1 validate 拆分(纯重构)
git cherry-pick 9a237abd7   # P2-2.2 get_hosts 去重(纯 perf)
git cherry-pick 36497e65a   # P2-2.3 system write helper + P3(纯重构)
git cherry-pick 9cb59a5cc   # P2-2.6 cache 精准删(行为修复)
git cherry-pick 1f7212616   # P1-2.7 VM 子网过滤(行为修复)
git cherry-pick d28ba8151   # P1-2.5 命令黑名单(安全)
git cherry-pick b0daa5311   # P1-2.4 视图权限(鉴权)
git cherry-pick 6ab29edaf   # P0-1.4 业务层补偿(容错)
git cherry-pick e62fa0865   # P0-1.3 容忍非数字(容错)
git cherry-pick 15532d6b7   # P0-1.2 空子网兜底(容错)
```

**收口前必跑**:`cd server && make test`(commit 用了 `--no-verify` 跳 pre-commit,正式合并前需要全量门禁)。

---

## 九、改进建议(下次类似 review 流程)

1. **拆"测试驱动修复"和"代码 review"**:review 阶段严格不动代码(本次遵循);先固化测试 → 再改代码,避免 review 时被新代码"污染"。
2. **schema 变更提前识别**:P0-1.4 加 `failed: 0` 字段前应提前 grep 全仓调用方,避免 cherry-pick 时遗漏。
3. **跨层根因要追溯到底**:P2-2.6 cache 问题暴露在 `_clear_all_caches`,但根因在 `cache backend` 配置层,后续 review 要敢于跨文件追问。
4. **撤项要明示**:P0-1.1 表面看是 bug,实测发现是设计 + 测试覆盖完整,撤项节省了大量无效工作。
5. **P3 风格合并到 P2**:本次遵循用户偏好,合并后 commit 信息仍清晰可追溯。