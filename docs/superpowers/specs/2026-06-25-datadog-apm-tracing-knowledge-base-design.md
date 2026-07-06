# Datadog APM Tracing 知识库设计

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
