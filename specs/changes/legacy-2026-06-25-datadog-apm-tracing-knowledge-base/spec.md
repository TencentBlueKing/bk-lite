# Historical Superpowers change: 2026-06-25-datadog-apm-tracing-knowledge-base

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-25-datadog-apm-tracing-knowledge-base.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `docs/ai-product-capabilities/` 下创建一套可持续扩写的 Datadog APM Tracing 知识库资料，并下载关键图片到本地。

**Architecture:** 使用一个总览页作为入口，专题页按能力域拆分，页面间使用 `[[wikilink]]` 互链。本地 `images/` 目录保存关键截图，避免仅依赖外链。

**Tech Stack:** Markdown, wikilink, curl, local filesystem

---

### Task 1: 搭建知识库骨架

**Files:**
- Create: `docs/ai-product-capabilities/datadog-apm-tracing/index.md`
- Create: `docs/ai-product-capabilities/datadog-apm-tracing/topics/*.md`
- Create: `docs/ai-product-capabilities/datadog-apm-tracing/images/*`

- [ ] Step 1: 创建知识库目录骨架
- [ ] Step 2: 定义首页导航与页面互链关系
- [ ] Step 3: 约定每页固定结构，便于后续持续补充

### Task 2: 提炼 Datadog APM Tracing 主干能力

**Files:**
- Modify: `docs/ai-product-capabilities/datadog-apm-tracing/index.md`
- Modify: `docs/ai-product-capabilities/datadog-apm-tracing/topics/*.md`

- [ ] Step 1: 基于 Datadog `tracing.md` 与 `apm/llms.txt` 提取主干栏目
- [ ] Step 2: 将术语、接入、分析、服务观测、链路管道、跨产品联动分拆为独立页面
- [ ] Step 3: 每页补足“BK-Lite 可借鉴点”

### Task 3: 下载关键图片资料

**Files:**
- Create: `docs/ai-product-capabilities/datadog-apm-tracing/images/*.png`

- [ ] Step 1: 选择 Trace Explorer、Service Page、Resource Page、Deployment Tracking、Error Tracking、Telemetry correlation、Trace Pipeline 等关键图片
- [ ] Step 2: 下载到本地并采用稳定文件名
- [ ] Step 3: 在相关页面改为引用本地图片

### Task 4: 自检

**Files:**
- Modify: `docs/ai-product-capabilities/datadog-apm-tracing/index.md`
- Modify: `docs/ai-product-capabilities/datadog-apm-tracing/topics/*.md`

- [ ] Step 1: 检查 `[[wikilink]]` 是否闭环
- [ ] Step 2: 检查图片路径是否可用
- [ ] Step 3: 检查是否遗漏 Datadog Tracing 主干栏目

## specs: 2026-06-25-datadog-apm-tracing-knowledge-base-design.md

- 日期：2026-06-25
- 状态：已确认并执行
- 目标：在 `docs/ai-product-capabilities/` 下沉淀一套供 BK-Lite 学习 Datadog APM Tracing 产品能力的本地知识库资料，采用 `wikilink` 组织，并保留关键图片资料。

## 设计结论

- 目录采用 `总览页 + 专题子页 + images/`。
- 内容语言采用中文为主，保留英文术语。
- 页面之间优先使用 `[[wikilink]]` 互链，外部官方链接集中放在每页“参考链接”部分。
- 不追求镜像 Datadog 全站，而是围绕 `Tracing` 文档主干做知识库型拆页。
- 保留关键产品界面图、流程图、依赖图与策略页截图，图片落本地 `images/`，避免知识材料后续失联。

## 目录结构

- `docs/ai-product-capabilities/datadog-apm-tracing/index.md`
- `docs/ai-product-capabilities/datadog-apm-tracing/topics/*.md`
- `docs/ai-product-capabilities/datadog-apm-tracing/images/*`

## 页面组织原则

每个专题页保持统一结构：

1. 这是什么
2. Datadog 怎么做
3. 对 BK-Lite 可借鉴什么
4. 相关页面
5. 参考链接

## 首版范围

- APM 与核心术语
- 接入与 Instrumentation
- Trace Explorer
- Service / Resource / Deployment observability
- Trace metrics 与 runtime metrics
- Error Tracking
- Logs / RUM / DBM / Profiler / Synthetics 关联
- Trace Pipeline：ingestion、processing、retention、usage
- SDK、OpenTelemetry 与生态入口
- 面向 BK-Lite 的产品启发总结

## 非目标

- 不做官方全文逐段翻译。
- 不抓取所有装饰性图片与视频。
- 不对 Datadog 站点结构做一比一目录映射。
