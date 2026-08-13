# 02 — 实例选择器、记忆与空态

Status: done

Blocked by: 01 — 导航与路由壳

**What to build:** 专题工作台顶部提供紧凑实例选择器（可搜索 + 最近访问）；严格按主题门控过滤；各专题独立 localStorage 记忆；无 URL/无记忆时空态引导选实例；选中后 URL 写入 `model_id`/`inst_id`（机房机柜含 `mode`）。

- [x] 选择器只列出该 `viewType`（及 rack-room 的 mode）合法模型下的实例
- [x] 各专题记忆互不串扰；刷新后能恢复上次焦点（含 rack-room 的 mode）
- [x] 最近访问按专题维度记录，有上限
- [x] 无参数且无记忆：空态 + 同一套选择器，不自动选第一条
- [x] 资格、记忆、URL 构造有可注入 Storage 的纯函数测试

## Completion evidence

- Shell/Picker/CanvasHost 占位；I1/I2 质量修复（modelsReady 校验、URL↔focus 同步）
- `pnpm test:cmdb-views-hub-core` / `menu` PASS
- ViewsHub i18n zh/en

## Notes

- 记忆键控：用户 × 视图类型；仿现有 asset-model-tree preference 模式
- 实例列表走既有 `searchInstances`；主题门控对齐 `getTopoThemes` / 模型白名单
- 画布嵌入留给 tickets 03–07