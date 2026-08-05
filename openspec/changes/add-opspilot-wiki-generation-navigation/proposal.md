## Why

目录治理已经提供真实目录和 Generation 发布边界，但当前查询与新知识冲突候选仍可能扫描活动页面正文或携带过多旧知识。需要引入 Generation 原生的 Index/Overview 导航层，使查询和构建成本不随旧页面数量线性增长，并保证最终判断始终回读真实证据。

## What Changes

- 为每个 Generation 构建逐页面结构化 Index Entry，不使用单个大 JSON，也不把 Markdown 文件作为运行时真相。
- 为根目录和每个活动目录生成确定性 Overview，并允许最多一次受控 LLM 语义增强；语义增强不阻止 Generation 激活。
- 问答使用精确标题/别名、Index 评分、可选 Overview 路由、真实证据和有界图谱扩展的级联流程。
- 新文件构建复用 Index 做旧知识 Top-N 候选召回，不再注入全库页面清单或逐页调用 LLM。
- 冲突比较最多装配 5 个旧页面、8,000 token 旧证据，并在一次 LLM 请求中批量判断。
- 原生导出渲染 `index.md`、根 `overview.md` 和目录 Overview；运行时查询不读取磁盘文件。
- 缓存、Index、Overview、页面、关系和引用均绑定同一个 Generation。
- 本变更不修改向量、embedding、RRF 或现有冲突审批语义。

## Capabilities

### New Capabilities

- `wiki-generation-navigation`: 定义 Generation 级 Index/Overview、查询级联、动态证据片段、缓存一致性和 Markdown 渲染。
- `wiki-conflict-candidate-routing`: 定义新知识对旧知识的低成本候选召回、确定性过滤和单次批量证据比较。

### Modified Capabilities

- 无。

## Impact

- 后端：新增 Generation Index/Overview 领域模型与服务，调整查询、上下文、构建、导出和缓存链路。
- 数据：导航产物绑定 Generation；现有本地测试数据不回填。
- API：查询结果增加路由、预算、Generation 和动态 snippet 信息。
- 构建：Stage2 旧知识候选由全库上下文改为 Index Top-N。
- 测试：增加性能、召回、证据正确性和跨 Generation 混读门禁。
