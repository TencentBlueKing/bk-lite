## 1. 领域模型与 Generation 集成

- [x] 1.1 定义逐页面 Generation Index Entry、确定性 Overview 和语义 Overview 派生缓存模型
- [x] 1.2 将 Index/确定性 Overview 完整性加入 Generation consistency report 和 CAS 激活门禁
- [x] 1.3 在 A/B 模型冻结后与目录治理模型一起重建 0066 之后的连续 migration

## 2. Index 与 Overview 构建

- [x] 2.1 实现活动页面 Index Entry 的批量确定性生成、稳定排序与指纹
- [x] 2.2 复用页面生成输出中的有界 summary/keywords/entities，并实现确定性降级
- [x] 2.3 实现根与目录确定性 Overview
- [x] 2.4 实现最多一次语义 Overview 增强、同代引用校验、stale 丢弃和 degraded 状态
- [x] 2.5 实现 index.md、overview.md 和目录 Overview 的稳定渲染

## 3. 查询级联

- [x] 3.1 实现标题/别名精确匹配和数据库侧 Index 评分
- [x] 3.2 实现高置信度直达证据与低置信度单次 Overview 路由
- [x] 3.3 实现命中位置动态 snippet、目录 breadcrumb 与 heading path 分离
- [x] 3.4 让问答引用只指向同代 PageVersion/Evidence
- [x] 3.5 为路由和证据装配增加 Generation scoped cache 与 stale 防护

## 4. 新知识冲突候选

- [x] 4.1 将 Stage2 全库页面上下文替换为 Index Top-20 紧凑候选
- [x] 4.2 仅实现硬身份无关、完全相同和可证明结构化等价/包含的确定性预过滤；不确定 supplement/conflict 必须进入证据比较
- [x] 4.3 实现最多 5 页/8,000 token 证据的一次批量冲突判断
- [x] 4.4 记录候选评分、过滤、溢出、证据引用和 base Generation
- [ ] 4.5 验证候选路由不改变现有冲突决策与回放语义

## 5. 导出、性能与质量验证

- [x] 5.1 扩展原生导出 manifest 和导航 Markdown，并验证同代 round-trip
- [ ] 5.2 增加 Index/Overview 确定性、语义降级和跨 Generation 隔离测试
- [ ] 5.3 增加 1,000 页面 P95 性能测试和调用量不随旧页面线性增长测试
- [ ] 5.4 建立 Recall@5、冲突 Recall@20 和引用正确率评测数据集
- [x] 5.5 验证现有向量代码与行为未被本变更修改
