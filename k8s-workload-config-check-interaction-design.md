# OpsPilot K8s Workload 配置检查 — 交互方案设计

## 一、设计目标

让用户用自然语言问 K8s 配置问题，系统自动判断意图和范围，按流程给出结果。

**核心能力**：意图识别 → 范围确定 → 执行检查 → 展示结果 → 修复引导

---

## 二、主流程

### 完整流程图

```
用户提问
  │
  ▼
┌─────────────────────────────────────────────────┐
│  Step 1：意图识别                                │
│                                                 │
│  从用户问法中判断两件事：                         │
│  ① 想干什么（意图）  ② 查什么范围（范围）          │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     意图不明确     范围不明确     都明确
          │            │            │
          ▼            ▼            ▼
┌──────────────┐ ┌──────────┐     │
│ Step 2a      │ │ Step 2b  │     │
│ 引导选意图    │ │ 引导定范围│     │
│ (只问这一个)  │ │ (只问这个)│     │
└──────┬───────┘ └────┬─────┘     │
       │              │           │
       └──────────────┴───────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Step 3：执行检查                                │
│                                                 │
│  按 意图×范围 组合，调用对应检查逻辑              │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Step 4：展示结果                                │
│                                                 │
│  范围越大展示越聚合，范围越小展示越详细            │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Step 5：追问引导                                │
│                                                 │
│  给出 2-3 个可追问方向（下钻 / 修复 / 导出）      │
│  用户追问后回到 Step 1 重新识别                   │
└─────────────────────────────────────────────────┘
```

---

## 三、Step 1 — 意图识别（核心）

### 3.1 用户问法 → 意图 × 范围 矩阵

| 用户怎么问 | 识别的意图 | 识别的范围 | 缺什么 | 系统动作 |
|-----------|-----------|-----------|--------|---------|
| "帮我检查下集群配置" | 模糊 | 全集群 | 缺意图 | 引导选场景 |
| "集群有没有安全风险" | 安全审计 | 全集群 | 都有 | 直接执行 |
| "检查 production 的配置" | 日常巡检 | namespace | 都有 | 直接执行 |
| "default 空间安全配置怎么样" | 安全审计 | namespace | 都有 | 直接执行 |
| "order-api 能不能上线" | 上线审查 | 单应用 | 都有 | 直接执行 |
| "检查下 order-api" | 日常巡检 | 单应用 | 都有 | 直接执行 |
| "帮我修复 order-api 的配置" | 修复 | 单应用 | 都有 | 直接执行 |
| "怎么批量修 limits 问题" | 批量修复 | 上次结果 | 都有 | 直接执行 |
| "导出报告" | 全量报告 | 全集群 | 都有 | 直接执行 |

**关键规则：缺什么问什么，一次只问一个。**

### 3.2 意图模糊时 — 引导选场景

```
👤 用户：帮我检查下 K8s 集群的配置

🤖 OpsPilot：好的，你想做哪种检查？

1. 🔍 日常巡检 — 快速看哪些空间有配置问题
2. 🚀 上线审查 — 检查某个应用是否达到生产标准
3. 🔒 安全审计 — 专项检查安全相关配置
4. 📊 全量报告 — 生成完整的配置检查报告
```

### 3.3 范围模糊时 — 引导缩小范围

```
👤 用户：帮我做个上线审查

🤖 OpsPilot：请告诉我要审查的应用，比如 "production 下的 order-api"
```

```
👤 用户：帮我检查某个空间的配置

🤖 OpsPilot：请告诉我命名空间名称，比如 "production"
```

---

## 四、Step 3 — 执行检查（意图 × 范围 = 检查策略）

| 意图 ╲ 范围 | 全集群 | 命名空间 | 单应用 |
|------------|--------|---------|--------|
| **日常巡检** | 扫描全部，输出 Top 3 + 评分 | 该空间所有 workload，按问题聚合 | 25 项逐条检查 |
| **上线审查** | ❌ 不支持，引导指定应用 | ❌ 不支持，引导指定应用 | P0 全检 + 上线结论 |
| **安全审计** | 全部 workload，只查安全项 | 该空间 workload，只查安全项 | 该应用安全项逐条 |
| **全量报告** | 全部 workload，25 项全查 | 该空间全查 | 同日常巡检单应用 |

**检查项（25 项，按优先级分组）**：

| 优先级 | 检查项 |
|--------|--------|
| P0（10 项） | resources.requests、resources.limits、readinessProbe、livenessProbe、镜像固定版本、replicas≥2、privileged:false、hostNetwork/PID/IPC、updateStrategy、restartPolicy |
| P1（9 项） | runAsNonRoot、capabilities drop ALL、readOnlyRootFS、SA token、非 default SA、imagePullPolicy、requests/limits 比值、preStop hook、PDB |
| P2（6 项） | antiAffinity、ephemeral-storage、priorityClass、topologySpreadConstraints、terminationGracePeriod、env 敏感信息 |

---

## 五、Step 4 — 展示结果（三级粒度）

### 5.1 集群级展示（聚合概览）

**适用于**：日常巡检-全集群、安全审计-全集群

```
👤 用户：帮我巡检一下集群配置

🤖 OpsPilot：

📊 集群配置巡检  评分：68/100 ⚠️
扫描：15 个命名空间 · 328 个工作负载

🔴 Top 3 高风险：
1. 89 个容器未设置 limits — production(45) staging(30) default(14)
2. 23 个 Deployment 无就绪探针 — production(15) staging(8)
3. 12 个 Deployment 单副本 — production(8) staging(4)

🟡 其他：67 个容器 root 运行 | 15 个无 PDB
✅ 健康探针 85% | 镜像规范 92%

💡 可继续：
  · "production 有哪些问题" — 下钻某空间
  · "怎么修 limits" — 批量修复建议
  · "导出报告" — 完整报告
```

**设计要点**：
- 只展示 Top 3 高风险 + 一行注意项 + 一行健康项
- 总量控制在一屏以内
- 结尾给 2-3 个追问方向

### 5.2 命名空间级展示（问题聚合表）

**适用于**：追问某空间 / 日常巡检-命名空间

```
👤 用户：production 有哪些问题

🤖 OpsPilot：

📋 production  评分：58/100
52 个工作负载，26 个有配置问题：

┌──────────────────┬────────────────────────┬──────┐
│ 问题              │ 涉及工作负载            │ 数量 │
├──────────────────┼────────────────────────┼──────┤
│ 未设置 limits     │ order-api, user-svc …  │ 15   │
│ 无就绪探针        │ payment-gw, notify …   │ 6    │
│ 使用 :latest      │ frontend, admin-ui …   │ 5    │
│ 单副本部署        │ scheduler, cron-worker │ 2    │
└──────────────────┴────────────────────────┴──────┘

💡 输入应用名查看详情，如 "order-api"
```

### 5.3 单应用级展示（逐项检查表）

**适用于**：上线审查 / 追问某应用 / 安全审计-单应用

```
👤 用户：order-api 能不能上线

🤖 OpsPilot：

🔍 order-api 上线审查  ❌ 不建议上线
副本: 1 | 镜像: order-api:latest | 容器: 2

┌───────────────┬─────────────┬──────┬───────────────────┐
│ 检查项         │ 当前值       │ 结果 │ 说明              │
├───────────────┼─────────────┼──────┼───────────────────┤
│ requests      │ 未设置       │ 🔴   │ 影响调度和资源分配 │
│ limits        │ 未设置       │ 🔴   │ 可能耗尽节点资源   │
│ readinessProbe│ 未配置       │ 🔴   │ 未就绪也会接流量   │
│ livenessProbe │ httpGet /hz  │ ✅   │ —                 │
│ 镜像标签       │ :latest     │ 🔴   │ 版本不可控         │
│ replicas      │ 1           │ 🔴   │ 单点故障           │
│ runAsNonRoot  │ 未设置       │ 🟡   │ 建议配置           │
│ privileged    │ false       │ ✅   │ —                 │
│ antiAffinity  │ 未配置       │ 🟡   │ 副本可能集中一节点  │
│ PDB           │ 未关联       │ 🟡   │ 驱逐时无保护       │
└───────────────┴─────────────┴──────┴───────────────────┘

结论：5 项 🔴 未通过，3 项 🟡 建议改进

💡 输入 "帮我生成修复方案" 查看具体怎么改
```

---

## 六、Step 5 — 修复引导（三种 Diff 粒度）

用户在任意结果页追问"怎么修"、"帮我改"时进入修复流程。

### 6.1 逐项 Diff（单应用修复）

```
👤 用户：帮我生成 order-api 的修复方案

🤖 OpsPilot：

📝 order-api 修复方案（5 项）

━━━ 修复 1/5：添加 resources ━━━

  containers:
  - name: order-api
+   resources:
+     requests:
+       cpu: "100m"
+       memory: "128Mi"
+     limits:
+       cpu: "500m"
+       memory: "512Mi"

💡 建议值基于同类服务常见配置，请根据实际负载调整

━━━ 修复 2/5：添加 readinessProbe ━━━

  containers:
  - name: order-api
    livenessProbe:
      httpGet:
        path: /healthz
        port: 8080
+   readinessProbe:
+     httpGet:
+       path: /ready
+       port: 8080
+     initialDelaySeconds: 5
+     periodSeconds: 10

💡 path 请改为应用实际的就绪检查端点

━━━ 修复 3/5：固定镜像版本 ━━━

  containers:
  - name: order-api
-   image: order-api:latest
+   image: order-api:v1.2.3

💡 请替换为实际版本号

━━━ 修复 4/5：增加副本数 ━━━

  spec:
-   replicas: 1
+   replicas: 2

━━━ 修复 5/5：配置安全上下文 ━━━

  containers:
  - name: order-api
+   securityContext:
+     runAsNonRoot: true
+     readOnlyRootFilesystem: true
+     allowPrivilegeEscalation: false

💡 可继续：
  · "合并成完整 YAML" — 看前后完整对比
  · "只改前 3 项" — 先改最关键的
```

### 6.2 合并 YAML（完整前后对比）

```
👤 用户：合并成完整 YAML

🤖 OpsPilot：

📄 order-api 修复前后对比：

  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: order-api
    namespace: production
  spec:
-   replicas: 1
+   replicas: 2
    template:
      spec:
        containers:
        - name: order-api
-         image: order-api:latest
+         image: order-api:v1.2.3
+         resources:
+           requests:
+             cpu: "100m"
+             memory: "128Mi"
+           limits:
+             cpu: "500m"
+             memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
+         readinessProbe:
+           httpGet:
+             path: /ready
+             port: 8080
+           initialDelaySeconds: 5
+           periodSeconds: 10
+         securityContext:
+           runAsNonRoot: true
+           readOnlyRootFilesystem: true
+           allowPrivilegeEscalation: false

变更：5 处修改 | +18 行 | ~2 行

💡 可继续：
  · "确认应用" — 需人工审批后执行
  · "下载 YAML" — 导出修复后完整文件
  · "我自己改" — 仅作参考
```

### 6.3 批量修复（按问题归组）

```
👤 用户：怎么批量修复 limits 问题

🤖 OpsPilot：

🔧 批量修复：89 个容器未设置 limits
分布：production(45) | staging(30) | default(14)

建议分批处理，先从 production 开始：

  受影响（前 10 个）：order-api, user-svc, payment-gw, notify-svc …

  推荐模板：
+   resources:
+     requests:
+       cpu: "100m"
+       memory: "128Mi"
+     limits:
+       cpu: "500m"
+       memory: "512Mi"

💡 注意：
  · 数据库类服务需更大 memory
  · 建议先在 staging 验证，再 apply 到 production
  · 输入具体应用名可查看针对性建议值
```

### 6.4 Diff 展示规范

```
规范：
  -  删除/修改前
  +  新增/修改后
     无标记 = 上下文（保留 2 行帮助定位）

每段 Diff 包含：
  1. 标题行：修复 N/M + 问题名称
  2. Diff 内容
  3. 💡 行：注意事项
```

### 6.5 建议值来源

| 配置项 | 建议值怎么来 |
|--------|------------|
| resources | 同空间同类应用中位数，无参考时用默认值 |
| probe path | 读取已有 livenessProbe 的 path |
| probe 参数 | 行业默认：delay=5s, period=10s, timeout=3s |
| replicas | 生产环境最低 2 |
| image tag | 读取当前运行版本替换 latest |
| securityContext | 安全基线模板 |

### 6.6 操作安全保障

| 环节 | 措施 |
|------|------|
| 生成建议 | 只读，不修改任何配置 |
| 确认应用 | 必须人工审批通过 |
| 执行变更 | 审计日志记录 |
| 出问题 | 变更前快照，支持回滚 |

---

## 七、技术实现要点

### 7.1 需要新增的工具

| 工具 | 说明 |
|------|------|
| `scan_workload_configs` | 3 次 API 拉全部 workload，内存批量检查，返回聚合统计 |
| `check_namespace_configs` | 指定空间，按问题聚合，列出受影响 workload |
| `check_workload_detail` | 单应用 25 项逐条检查 |
| `generate_fix_diff` | 读取当前配置 vs 目标配置，输出 +/- Diff |
| `generate_merged_yaml` | 多项修复合并到完整 YAML |

### 7.2 评分算法

```
单 workload = 100 - (P0 未通过 × 10) - (P1 未通过 × 5) - (P2 未通过 × 2)
命名空间 = 所有 workload 评分加权平均（按副本数）
集群 = 所有空间评分加权平均（按 workload 数）

90-100 ✅ 健康 | 70-89 ⚠️ 需关注 | 50-69 🟡 有风险 | 0-49 🔴 严重
```

### 7.3 性能设计

| 问题 | 方案 |
|------|------|
| workload 太多 | 3 次批量 API（Deployment + StatefulSet + DaemonSet），内存遍历（500 个 ≈ 2 秒） |
| 结果太多 LLM 放不下 | 工具内部聚合，只返回统计 + Top N |
| 追问不同空间 | 首次扫描缓存，下钻复用 |

---

## 八、方案收益

| 维度 | 改进前 | 改进后 |
|------|--------|--------|
| 用户上手 | 不知道该问什么 | 4 个场景直接选 |
| 首次响应 | 问 3 轮才看到问题 | 巡检 1 轮出 Top 3，审查 1 轮出完整表 |
| 修复体验 | 只告诉"有问题" | 逐项 Diff + 合并 YAML + 批量模板 |
| 操作闭环 | 用户自己写 YAML | 检查 → Diff → 确认 → 审批 → 应用 |
| 大集群 | 超时爆上下文 | 全量扫描 + 聚合输出 |

---

*文档生成时间：2026-05-13*
