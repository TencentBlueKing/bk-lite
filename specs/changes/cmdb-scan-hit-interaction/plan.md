# CMDB 扫描命中详情交互 Implementation Plan

> **For agentic workers:** 按任务顺序 TDD 实现；规格见 `specs/changes/cmdb-scan-hit-interaction/spec.md`。

**Goal:** 扫描命中详情改为加宽抽屉 + 表格 + 已匹配/未匹配 tab，并支持写指纹认领与手选类型推监控/采集两条独立路径。

**Architecture:** 命中 `unmatch_reason` 由序列化计算。认领 / 手选分类是扫描执行上的两个新动作，复用现有 `write_refined_metrics` 写 CI，不重打枪、不改收口主路径。前端一次按页拉取全部命中后本地分页与跨页勾选。

**Tech Stack:** Django ORM、DRF、现有 CMDB mapping / MetricsCannula、Next.js、Ant Design。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/services/scan_identity.py` | `unmatch_reason_for_hit` |
| `server/apps/cmdb/services/scan_classify_service.py` | 手选类型建 CI、按 SOID 认领 |
| `server/apps/cmdb/views/scan.py` | `classify_hits` / `rematch_soid` |
| `server/apps/cmdb/serializers/scan_serializer.py` | 暴露 `unmatch_reason` |
| `web/src/app/cmdb/api/scan.ts` | 新动作客户端 |
| `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/ScanHitsDrawer.tsx` | 命中详情抽屉 |
| `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/page.tsx` | 列表调用抽屉 |
| `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/soid/page.tsx` | 读取 `?oid=` |
| `web/src/app/cmdb/locales/{zh,en}.json` | 文案 |

---

### Task 1: unmatch_reason

- Modify: `server/apps/cmdb/services/scan_identity.py`
- Modify: `server/apps/cmdb/serializers/scan_serializer.py`
- Test: `server/apps/cmdb/tests/test_scan_identity.py`、`server/apps/cmdb/tests/test_scan_views.py`

- [ ] 纯函数：网络空模型 + 有 SOID → `unknown_soid`；无 SOID → `empty_soid`；已有 `cmdb_model_id` 或非网络 → `""`
- [ ] 命中 API 项带 `unmatch_reason`

### Task 2: 手选类型 / 认领服务

- Create: `server/apps/cmdb/services/scan_classify_service.py`
- Test: `server/apps/cmdb/tests/test_scan_classify_service.py`

- [ ] `classify_hits`：终态执行、四类网络、只处理未匹配网络行、mock cannula 写 CI、回填 `cmdb_model_id`/`inst_uuid`、不创建 `OidMapping`
- [ ] `rematch_soid`：特征库已有映射时认领该 SOID 全部未匹配行；传入 `hit_ids` 时可把空 SOID 命中回写后再认领；映射不存在则失败；已分类行跳过
- [ ] 非终态拒绝

### Task 3: API

- Modify: `server/apps/cmdb/views/scan.py`
- Test: `server/apps/cmdb/tests/test_scan_views.py`

- [ ] `POST executions/{eid}/classify_hits` 权限 `auto_collection-Execute`
- [ ] `POST executions/{eid}/rematch_soid` 权限 `auto_collection-Execute`

### Task 4: 命中抽屉 UI

- Create: `ScanHitsDrawer.tsx`（及指纹 Modal）
- Modify: `page.tsx`、`scan.ts`、locales、特征库 `soid/page.tsx`

- [ ] 抽屉 80vw / max 1440；顶层 tab；已匹配按族表；未匹配按 SOID 分组
- [ ] 循环拉取 hits（page_size 200）后前端分页 + 跨页勾选
- [ ] 未收口不拆未匹配；Path 1 Modal；Path 2 类型弹窗后 classify 再 push/collect
- [ ] 新标签 `?oid=`；特征库检索该 OID

### Task 5: 验证

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_scan_identity.py apps/cmdb/tests/test_scan_classify_service.py apps/cmdb/tests/test_scan_views.py apps/cmdb/tests/test_scan_finalize_service.py apps/cmdb/tests/test_scan_push_monitor.py --no-cov
cd web && pnpm type-check
```
