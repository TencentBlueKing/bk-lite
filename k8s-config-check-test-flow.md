# K8s Workload 配置检查 — 测试问答流程

> 配合 `k8s-config-check-prompt.txt` v5（状态机版）使用

## 〇、测试话术库（直接复制去问）

### A. 模糊问法 — 触发引导（缺集群+空间+应用）
1. `帮我检查下 K8s 的 workload 配置`
2. `看看集群里的工作负载配置有没有问题`
3. `我想做一次配置检查`

### B. 指定空间 — 跳过集群（缺应用）
4. `帮我检查 production 空间的 workload 配置`
5. `dev 命名空间下有配置风险吗`
6. `staging 的部署配置怎么样`

### C. 指定应用 — 最精确（可能缺空间/集群）
7. `检查 production 下 order-api 的配置`
8. `帮我看看 dev 空间 frontend 的配置合不合理`
9. `production 的 log-collector 有什么安全风险`

### D. 只说应用名 — 触发追问（多空间存在同名应用）
10. `检查 order-api 的配置`
11. `frontend 的 workload 配置怎么样`
12. `scheduler 配置有没有问题`

### E. 专业话术（运维视角）
13. `帮我审一下 production namespace 下各 Deployment 的 resource quota 和探针配置`
14. `线上 user-service 镜像还在用 latest tag，帮我全面检查下这个 workload`
15. `payment-gateway 只有单副本，帮我看看还有哪些配置不合理`
16. `我们的 log-collector 开了 privileged 和 hostNetwork，帮我出个检查报告`
17. `staging 环境即将升级到 production，帮我检查下这个空间所有 workload 的配置合规性`

### F. 追问修复
18. `帮我生成修复方案`
19. `这些问题怎么修`
20. `给我完整的修复 YAML`

---

## 一、核心流程测试：完整漏斗（集群→空间→应用→修复）

验证点：每步只问一个问题，已回答的不重复问，每步都往前推进。

```
👤 第1轮：帮我检查下 K8s 的 workload 配置
   ✅ 预期：调 get_kubernetes_contexts → 发现 2 个集群 → 列出集群名让用户选
   ❌ 失败：不列集群直接问模糊问题 / 不调工具

👤 第2轮：minikube
   ✅ 预期：立刻调 get_kubernetes_namespaces → 列出空间 + workload 数量 → 问选哪个空间
   ❌ 失败：又调 get_kubernetes_contexts / 重复问集群 / 不往下走

👤 第3轮：production
   ✅ 预期：立刻调 analyze_deployment_configurations(namespace=production) →
          展示空间概览（问题统计）+ 列出所有 workload 名称 → 引导用户选一个
   ❌ 失败：又问空间 / 概览后不列 workload 不引导

👤 第4轮：frontend
   ✅ 预期：输出 frontend 详细检查表（几乎全 🔴，评分约 10-20）→ 问是否看修复建议
   ❌ 失败：又回到空间概览 / 不输出检查表

👤 第5轮：帮我修一下
   ✅ 预期：调 get_kubernetes_resource_yaml → Diff 格式逐项修复建议
          +resources, +readinessProbe, +livenessProbe, 镜像固定版本, replicas→2
   ❌ 失败：给笼统建议不给 Diff
```

---

## 二、跳步测试：直接指定范围能否跳过引导

### 测试 1：直接 空间+应用 → 应该零提问直接出检查表
```
👤 检查 production 的 order-api
✅ 预期：直接输出 order-api 检查表
        requests ✅ | limits ✅ | probes ✅ | 镜像 ✅ | replicas ✅ | runAsNonRoot 🟡
        评分约 75
❌ 失败：还在问集群 / 问空间 / 问确认
```

### 测试 2：只给空间 → 出概览 + 引导选 workload
```
👤 检查 dev 的配置
✅ 预期：确定集群后直接出 dev 概览 → 列出 workload 引导选择
        问题应该很多（全 latest、无 limits、无探针）
❌ 失败：概览后停住不引导
```

### 测试 3：只给应用名，多空间存在 → 追问空间
```
👤 检查 order-api
✅ 预期：发现 production/staging/dev 都有 → 追问哪个空间的
❌ 失败：随便选一个不问 / 报错
```

### 测试 4：只给应用名，仅一个空间有 → 直接查
```
👤 检查 scheduler
✅ 预期：只有 production 有 scheduler → 直接输出检查表
        Recreate 策略标 🟡，单副本标 🔴
❌ 失败：还问空间
```

---

## 三、禁止回退测试（重点验证本次修复）

### 测试 1：选了集群后不许再问集群
```
👤 第1轮：帮我检查配置
   → Agent 列出 minikube / orbstack
👤 第2轮：minikube
   ✅ 预期：直接列空间，不再调 get_kubernetes_contexts
   ❌ 失败：又调 get_kubernetes_contexts 又问集群（截图中的 bug）
```

### 测试 2：选了空间后不许再问空间
```
（接上面）
👤 第3轮：production
   ✅ 预期：直接出概览 + 引导选 workload
   ❌ 失败：又调 get_kubernetes_namespaces 又问空间
```

### 测试 3：概览后不许停，必须引导选 workload
```
（接上面第3轮的概览输出）
   ✅ 预期：概览最后有 "请选择要详细检查的应用👇 order-api | user-service | ..."
   ❌ 失败：只出概览就结束，不引导下一步
```

---

## 四、意图识别测试（验证意图分类节点）

| # | 用户输入 | 预期意图 | 验证点 |
|---|---------|---------|--------|
| 1 | "帮我检查下 K8s 配置" | 配置检查 ✅ | K8s + 检查 |
| 2 | "production 有什么配置问题" | 配置检查 ✅ | 空间 + 配置 |
| 3 | "order-api 配置合理吗" | 配置检查 ✅ | 应用 + 配置 |
| 4 | "审一下 Deployment 的 resource quota" | 配置检查 ✅ | 专业术语 |
| 5 | "线上 workload 探针配了吗" | 配置检查 ✅ | 探针关键词 |
| 6 | "今天天气怎么样" | 默认意图 ✅ | 无关 |
| 7 | "帮我写个 Python 脚本" | 默认意图 ✅ | 无关 |

---

## 五、修复建议测试

```
👤 步骤 1：检查 production 的 frontend
   预期：检查表，大量 🔴，评分很低（10-20）

👤 步骤 2：帮我修一下
   预期：Diff 格式逐项修复
   - +resources (requests + limits)
   - +readinessProbe
   - +livenessProbe
   - image: nginx:latest → nginx:1.25.3
   - replicas: 1 → 2

👤 步骤 3：给我完整的修复 YAML
   预期：完整前后对比 / 修复后的完整 YAML
```

---

## 六、多集群测试

```
👤 第1轮：检查 order-api
   预期：两个集群都有 order-api → 追问哪个集群

👤 第2轮：orbstack 的
   预期：orbstack 中 order-api 检查结果
        (3副本, nginx:1.25.3, 有 limits, 有 probes)
```

---

## 七、边界测试

### 测试 1：查不存在的应用
```
👤 检查 production 的 xxx-service
✅ 预期：告知不存在 + 列出 production 可用 workload
```

### 测试 2：查系统空间
```
👤 检查 kube-system 的配置
✅ 预期：正常输出 kube-system 检查结果（coredns 等）
```

### 测试 3：查不存在的空间
```
👤 检查 abc 空间的配置
✅ 预期：告知不存在 + 列出可用命名空间
```

---

## 八、预期结果参考

### production 空间（minikube）— 12 个 workload

| 应用 | 类型 | 预期主要问题 | 预期评分 |
|------|------|------------|---------|
| order-api | Deploy | runAsNonRoot 🟡 | ~75 |
| user-service | Deploy | 缺 limits、latest | ~30 |
| payment-gateway | Deploy | 单副本、缺探针 | ~50 |
| log-collector | Deploy | privileged、hostNetwork、缺 limits/探针、单副本 | ~10 |
| notification-svc | Deploy | 缺 limits、缺 readiness | ~40 |
| frontend | Deploy | 全缺 | ~10 |
| redis-cluster | SS | 缺探针 | ~60 |
| postgres-primary | SS | 较好 | ~85 |
| node-exporter | DS | hostPID、缺探针 | ~50 |
| admin-panel | Deploy | 单副本、缺探针、latest | ~40 |
| scheduler | Deploy | 单副本、Recreate、缺探针 | ~45 |
| api-gateway | Deploy | sidecar 缺 limits/探针、latest | ~55 |

### dev 空间（minikube）— 12 个 workload
几乎全低分（10-20），全 latest、无 limits、无探针、单副本。
backend-api 有 privileged，file-uploader 有 hostNetwork+hostPID，mysql 有明文密码 env。
