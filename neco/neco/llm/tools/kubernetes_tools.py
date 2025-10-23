"""
Kubernetes工具入口文件

为了保持向后兼容性，这个文件重新导出所有Kubernetes工具函数。
所有工具已按功能重新组织到kubernetes/子模块中：

- kubernetes/resources.py: 基础资源查询工具
- kubernetes/diagnostics.py: 故障诊断和监控工具
- kubernetes/analysis.py: 配置分析和策略检查工具
- kubernetes/cluster.py: 集群管理和连接工具
- kubernetes/query.py: 高级查询工具
- kubernetes/tracing.py: 链路追踪和关联分析工具 (NEW)
- kubernetes/remediation.py: 故障自愈工具 (NEW)
- kubernetes/optimization.py: 配置优化工具 (NEW)
- kubernetes/utils.py: 通用辅助函数
"""

# 简洁的导入方式 - 所有复杂性都隐藏在 kubernetes 模块内部
from .kubernetes import *
