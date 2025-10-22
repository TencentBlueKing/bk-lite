# K8S 工具扩展能力设计方案

## 一、现有能力审查 (Review)

### 1.1 已实现的工具分类

根据代码审查，现有工具分为以下模块：

#### **基础资源查询 (resources.py)** ✅
- `get_kubernetes_namespaces` - 命名空间列表
- `list_kubernetes_pods` - Pod列表
- `list_kubernetes_nodes` - 节点列表
- `list_kubernetes_deployments` - Deployment列表
- `list_kubernetes_services` - Service列表
- `list_kubernetes_events` - 事件列表
- `get_kubernetes_resource_yaml` - 获取资源YAML
- `get_kubernetes_pod_logs` - Pod日志（支持tail/head）

#### **故障诊断 (diagnostics.py)** ✅
- `get_failed_kubernetes_pods` - 失败Pod列表
- `get_pending_kubernetes_pods` - Pending Pod列表
- `get_high_restart_kubernetes_pods` - 高重启Pod
- `get_kubernetes_node_capacity` - 节点容量分析
- `get_kubernetes_orphaned_resources` - 孤立资源检查
- `diagnose_kubernetes_pod_issues` - Pod综合诊断

#### **配置分析 (analysis.py)** ✅
- `check_kubernetes_resource_quotas` - 资源配额检查
- `check_kubernetes_network_policies` - 网络策略检查
- `check_kubernetes_persistent_volumes` - PV/PVC检查
- `check_kubernetes_ingress` - Ingress配置检查
- `check_kubernetes_daemonsets/statefulsets/jobs` - 工作负载检查
- `check_kubernetes_endpoints` - Endpoints检查
- `analyze_deployment_configurations` - Deployment配置分析
- `check_kubernetes_hpa_status` - HPA状态检查

#### **集群管理 (cluster.py)** ✅
- `verify_kubernetes_connection` - 连接验证
- `get_kubernetes_contexts` - 上下文管理
- `list_kubernetes_api_resources` - API资源列表
- `explain_kubernetes_resource` - 资源类型说明
- `describe_kubernetes_resource` - 资源详情描述
- `kubernetes_troubleshooting_guide` - 故障排查指导

#### **高级查询 (query.py)** ✅
- `kubectl_get_resources` - 灵活资源查询（支持标签/字段选择器）
- `kubectl_get_all_resources` - 批量资源查询

### 1.2 现有能力的优势
- ✅ 覆盖了基础的CRUD操作
- ✅ 提供了基本的故障诊断能力
- ✅ 支持多种资源类型
- ✅ 具备一定的配置分析能力

### 1.3 现有能力的不足 (Gap Analysis)

#### 🚨 **故障诊断维度**
- ❌ **缺乏时序性分析**: 无法分析资源状态的历史变化趋势
- ❌ **缺乏关联性分析**: 不能跨资源关联诊断（Pod→Service→Ingress链路）
- ❌ **缺乏根因分析**: 只能查看现象，无法推断根本原因
- ❌ **缺乏性能诊断**: 没有CPU/内存压力、网络延迟、I/O等性能指标
- ❌ **缺乏安全检查**: 没有权限、安全策略、镜像漏洞等安全诊断

#### 🔧 **故障自愈维度**
- ❌ **完全缺失操作能力**: 无法执行任何修复操作（重启、扩容、更新配置）
- ❌ **无回滚机制**: 不支持Deployment/StatefulSet的版本回滚
- ❌ **无自动修复**: 无法执行常见问题的自动化修复流程

#### 💡 **配置优化维度**
- ❌ **缺乏成本优化**: 没有资源浪费分析（over-provisioned、idle资源）
- ❌ **缺乏安全加固**: 没有安全最佳实践检查和建议
- ❌ **缺乏性能优化**: 缺少性能调优建议（亲和性、拓扑分布）
- ❌ **缺乏可靠性建议**: 没有高可用性、容灾等架构建议

---

## 二、场景驱动的能力建设 (Scenario-Driven Design)

### 2.1 故障诊断场景

#### **场景 1: 应用无法访问**
**用户输入**: "我的应用无法访问了，帮我排查一下"

**LLM需要的工具链**:
1. 识别应用（通过名称/标签找到相关Pod、Service、Ingress）
2. 检查访问链路健康（Ingress→Service→Endpoints→Pod）
3. 分析网络策略是否阻断
4. 检查Pod健康状态和就绪探针
5. 分析最近的事件和日志
6. 关联分析：节点故障、存储问题等

**需要新增的工具**:
- ✨ `trace_service_chain` - 追踪服务完整调用链
- ✨ `analyze_network_path` - 网络路径分析
- ✨ `get_resource_events_timeline` - 资源事件时间线
- ✨ `correlate_pod_issues` - 跨资源关联分析

#### **场景 2: Pod频繁重启**
**用户输入**: "我的Pod一直在重启，帮我找出原因"

**LLM需要的工具链**:
1. 识别高重启Pod（已有）
2. 分析重启历史趋势
3. 检查OOM、退出码、崩溃日志
4. 分析资源限制是否合理
5. 检查存储/配置/Secret是否异常
6. 推荐修复方案

**需要新增的工具**:
- ✨ `analyze_pod_restart_pattern` - Pod重启模式分析
- ✨ `check_oom_events` - OOM事件检测
- ✨ `recommend_resource_limits` - 资源配额建议
- ✨ `get_pod_crash_report` - Pod崩溃报告

#### **场景 3: 集群性能下降**
**用户输入**: "集群最近很慢，帮我分析性能瓶颈"

**LLM需要的工具链**:
1. 分析集群整体资源使用趋势
2. 识别资源热点（CPU/内存/网络高的节点和Pod）
3. 检查调度压力和驱逐事件
4. 分析I/O瓶颈和存储性能
5. 检查HPA是否正常工作
6. 提供优化建议

**需要新增的工具**:
- ✨ `analyze_cluster_performance` - 集群性能分析
- ✨ `identify_resource_hotspots` - 资源热点识别
- ✨ `check_pod_eviction_pressure` - 驱逐压力检查
- ✨ `analyze_scheduling_latency` - 调度延迟分析

### 2.2 故障自愈场景

#### **场景 4: 自动重启失败的Pod**
**用户输入**: "这个Pod失败了，帮我重启一下"

**LLM需要的工具链**:
1. 确认Pod状态和失败原因
2. 创建备份/快照（如有必要）
3. 执行删除操作触发重建
4. 监控新Pod启动状态
5. 验证恢复成功

**需要新增的工具**:
- ✨ `restart_pod` - 安全重启Pod（with validation）
- ✨ `delete_kubernetes_resource` - 删除资源（支持优雅删除）
- ✨ `wait_for_pod_ready` - 等待Pod就绪

#### **场景 5: 快速扩容应对流量激增**
**用户输入**: "流量突然增大，帮我扩容到10个副本"

**LLM需要的工具链**:
1. 检查当前Deployment副本数
2. 验证集群是否有足够资源
3. 执行扩容操作
4. 监控新Pod启动进度
5. 验证扩容后的健康状态

**需要新增的工具**:
- ✨ `scale_deployment` - 扩缩容Deployment/StatefulSet
- ✨ `check_scaling_capacity` - 检查扩容可行性
- ✨ `monitor_scaling_progress` - 监控扩缩容进度

#### **场景 6: 回滚到上一个稳定版本**
**用户输入**: "新版本有问题，回滚到上一个版本"

**LLM需要的工具链**:
1. 查看Deployment发布历史
2. 识别上一个稳定版本
3. 执行回滚操作
4. 监控回滚进度和健康状态
5. 验证回滚成功

**需要新增的工具**:
- ✨ `get_deployment_revision_history` - 获取发布历史
- ✨ `rollback_deployment` - 回滚Deployment
- ✨ `compare_deployment_revisions` - 对比发布版本差异

### 2.3 配置优化场景

#### **场景 7: 成本优化分析**
**用户输入**: "帮我分析一下集群的资源浪费情况，如何降低成本"

**LLM需要的工具链**:
1. 分析资源请求vs实际使用
2. 识别过度分配的Pod
3. 发现闲置资源（空节点、未使用的PV）
4. 计算潜在节省成本
5. 提供优化建议

**需要新增的工具**:
- ✨ `analyze_resource_waste` - 资源浪费分析
- ✨ `recommend_resource_right_sizing` - 资源容量优化建议
- ✨ `identify_idle_resources` - 闲置资源识别
- ✨ `calculate_cost_savings` - 成本节省估算

#### **场景 8: 安全加固检查**
**用户输入**: "帮我检查集群的安全配置，给出加固建议"

**LLM需要的工具链**:
1. 检查Pod安全上下文（runAsNonRoot等）
2. 分析RBAC权限配置
3. 检查镜像安全（latest标签、私有镜像）
4. 验证网络策略覆盖
5. 检查Secret加密和使用
6. 生成安全报告

**需要新增的工具**:
- ✨ `audit_security_policies` - 安全策略审计
- ✨ `check_pod_security_standards` - Pod安全标准检查
- ✨ `analyze_rbac_permissions` - RBAC权限分析
- ✨ `scan_image_vulnerabilities` - 镜像漏洞扫描（集成）
- ✨ `generate_security_report` - 生成安全报告

#### **场景 9: 高可用架构建议**
**用户输入**: "帮我检查应用的高可用配置，给出改进建议"

**LLM需要的工具链**:
1. 检查副本数和分布策略
2. 分析Pod反亲和性配置
3. 检查PodDisruptionBudget
4. 验证健康检查配置
5. 分析资源限制设置
6. 生成高可用报告

**需要新增的工具**:
- ✨ `analyze_high_availability` - 高可用性分析
- ✨ `check_pod_distribution` - Pod分布检查
- ✨ `recommend_anti_affinity` - 反亲和性建议
- ✨ `validate_probe_configuration` - 探针配置验证

---

## 三、工具设计原则 (Design Principles)

### 3.1 安全原则
1. **只读优先**: 诊断工具只读，操作工具需要明确确认
2. **操作限制**: 危险操作（删除、扩容）需要验证和审计
3. **回滚保护**: 所有变更操作必须支持回滚
4. **权限检查**: 调用前验证RBAC权限

### 3.2 可观测性原则
1. **日志记录**: 所有工具调用统一记录日志（使用仓库日志接口）
2. **关键指标**: 重要操作记录耗时和结果
3. **错误处理**: 异常必须带上下文（namespace、资源名、操作类型）

### 3.3 Agent友好性原则
1. **结构化输出**: 返回JSON格式，便于LLM解析
2. **语义清晰**: 工具名称和参数说明要自解释
3. **上下文传递**: 支持RunnableConfig传递上下文
4. **分步执行**: 复杂流程拆分为可组合的原子操作

---

## 四、与Agent能力匹配 (Agent Capability Alignment)

### 4.1 ReAct Agent 适用场景
ReAct Agent适合**线性推理+工具调用**的场景：

**适用工具类型**:
- ✅ 单步诊断工具（查看状态、获取日志）
- ✅ 简单操作工具（重启Pod、扩容）
- ✅ 快速查询工具（资源列表、配置检查）

**示例场景**:
```
用户: "帮我重启default命名空间下的nginx-pod"

ReAct推理:
Thought: 我需要先确认Pod存在，再执行重启
Action: list_kubernetes_pods(namespace="default")
Observation: [找到nginx-pod，状态为CrashLoopBackOff]
Thought: Pod确实存在且有问题，可以重启
Action: restart_pod(namespace="default", pod_name="nginx-pod")
Observation: [Pod已删除，新Pod正在创建]
Thought: 需要等待新Pod就绪
Action: wait_for_pod_ready(namespace="default", pod_name="nginx-pod", timeout=60)
Observation: [Pod已就绪]
Answer: 已成功重启nginx-pod，当前状态为Running
```

### 4.2 Plan and Execute Agent 适用场景
Plan and Execute Agent适合**复杂任务规划+分步执行**的场景：

**适用工具类型**:
- ✅ 综合分析工具（性能分析、安全审计）
- ✅ 多步骤操作（发布回滚、故障恢复）
- ✅ 需要决策的场景（优化建议、容量规划）

**示例场景**:
```
用户: "我的应用无法访问，帮我排查并修复"

Plan阶段:
步骤1: 识别应用相关资源（Pod、Service、Ingress）
步骤2: 检查服务调用链健康状态
步骤3: 分析Pod日志和事件
步骤4: 根据诊断结果执行修复操作
步骤5: 验证修复效果

Execute阶段:
- 执行步骤1: kubectl_get_resources + trace_service_chain
- 执行步骤2: analyze_network_path + check_kubernetes_endpoints
- 执行步骤3: get_kubernetes_pod_logs + diagnose_kubernetes_pod_issues
- 执行步骤4: restart_pod (if needed) 或 scale_deployment
- 执行步骤5: 再次检查服务状态

Replan (if needed): 如果修复失败，重新规划诊断路径
```

---

## 五、优先级排序 (Priority Ranking)

基于**场景频率**和**价值影响**，建议的实现优先级：

### P0 (立即实现) - 故障诊断增强
1. `trace_service_chain` - 服务链路追踪
2. `analyze_pod_restart_pattern` - Pod重启分析
3. `get_resource_events_timeline` - 事件时间线
4. `check_oom_events` - OOM检测

### P1 (近期实现) - 故障自愈基础
5. `restart_pod` - 重启Pod
6. `scale_deployment` - 扩缩容
7. `rollback_deployment` - 回滚
8. `get_deployment_revision_history` - 发布历史

### P2 (中期实现) - 配置优化
9. `analyze_resource_waste` - 资源浪费分析
10. `audit_security_policies` - 安全审计
11. `analyze_high_availability` - 高可用分析
12. `recommend_resource_right_sizing` - 容量建议

### P3 (长期实现) - 高级能力
13. `analyze_cluster_performance` - 集群性能分析
14. `scan_image_vulnerabilities` - 镜像扫描（需集成外部工具）
15. `calculate_cost_savings` - 成本分析

---

## 六、实现建议 (Implementation Recommendations)

### 6.1 文件组织
建议新增以下模块：
```
neco/llm/tools/kubernetes/
├── remediation.py      # 故障自愈工具（重启、扩容、回滚）
├── tracing.py          # 链路追踪和关联分析
├── optimization.py     # 配置优化建议
├── security.py         # 安全审计工具
└── performance.py      # 性能分析工具
```

### 6.2 安全约束
在操作类工具中增加：
```python
def _require_confirmation(operation: str, target: str) -> bool:
    """危险操作需要确认"""
    # 记录操作到审计日志
    logger.warning(f"危险操作: {operation} on {target}")
    # 返回是否允许操作（可集成审批流程）
    return True

def _validate_permissions(namespace: str, resource_type: str, verb: str):
    """验证RBAC权限"""
    # 通过SelfSubjectAccessReview检查权限
    pass
```

### 6.3 复用现有工具
新工具应最大化复用现有基础能力：
- 使用 `kubectl_get_resources` 作为查询基础
- 使用 `diagnose_kubernetes_pod_issues` 的诊断逻辑
- 使用 `analyze_deployment_configurations` 的分析框架

### 6.4 测试策略
- 单元测试：Mock K8S API响应
- 集成测试：使用kind/minikube搭建测试集群
- Agent测试：构造场景用例测试工具链

---

## 七、下一步行动 (Next Steps)

### Phase 1: 基础诊断增强 (本周)
- [ ] 实现 `trace_service_chain`
- [ ] 实现 `analyze_pod_restart_pattern`
- [ ] 实现 `get_resource_events_timeline`

### Phase 2: 自愈能力构建 (下周)
- [ ] 实现 `restart_pod` + 安全检查
- [ ] 实现 `scale_deployment` + 容量验证
- [ ] 实现 `rollback_deployment` + 版本管理

### Phase 3: 优化建议体系 (两周后)
- [ ] 实现 `analyze_resource_waste`
- [ ] 实现 `audit_security_policies`
- [ ] 构建优化建议生成器

---

## 八、风险和注意事项 (Risks & Considerations)

### 技术风险
- ⚠️ **权限问题**: 确保ServiceAccount有足够权限
- ⚠️ **API兼容性**: 不同K8S版本API可能不同（已处理v1/v1beta1）
- ⚠️ **性能影响**: 频繁调用API可能触发限流

### 业务风险
- ⚠️ **误操作风险**: 自愈工具可能误删资源，需要严格验证
- ⚠️ **安全风险**: LLM生成的操作命令需要沙箱隔离
- ⚠️ **审计合规**: 所有操作需要完整的审计日志

### 缓解措施
1. **操作前验证**: 所有变更操作需要pre-flight check
2. **只读模式**: 默认只提供诊断工具，操作工具需显式启用
3. **操作审批**: 关键操作集成审批流程
4. **回滚机制**: 所有操作记录变更前状态，支持一键回滚

---

**设计负责人**: GitHub Copilot  
**审核状态**: 待评审  
**更新时间**: 2025-10-21
