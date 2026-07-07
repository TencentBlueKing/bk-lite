# Datadog APM Tracing Knowledge Base Implementation Plan

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
