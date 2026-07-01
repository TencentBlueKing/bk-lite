import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

const POD_PHASE_ENUM = {
  0: { label: '未运行', color: '#faad14' },
  1: { label: '运行中', color: '#27c274' }
};

export const POD_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'k8s-pod',
  pageTitle: 'K8s Pod 监控仪表盘',
  objectFallbackName: 'Pod',
  instanceType: 'k8s',
  clusterFilter: true,
  collectionStatusQuery:
    "count(prometheus_remote_write_kube_pod_info{instance_type='k8s', __$labels__}) by (instance_id)",
  metaItems: ['cAdvisor', 'k8s'],
  metrics: [
    {
      name: 'pod_status_phase',
      display_name: 'Pod 状态',
      description: 'Pod 当前生命周期阶段(0 未运行 / 1 运行中),用于快速判断 Pod 健康。',
      unit: 'none',
      query: 'prometheus_remote_write_kube_pod_status_phase{instance_type="k8s",__$labels__}',
      color: '#27c274'
    },
    {
      name: 'pod_container_restarts_total',
      display_name: '容器重启数',
      description: 'Pod 内容器自启动以来的累计重启次数,抖动上升常表示崩溃循环。',
      unit: 'counts',
      query: 'prometheus_remote_write_kube_pod_container_status_restarts_total{instance_type="k8s",__$labels__}',
      color: '#ff4d4f',
      dimensions: [{ name: 'container' }]
    },
    {
      name: 'pod_cpu_utilization',
      display_name: 'CPU 使用率',
      description: 'Pod 实际 CPU 使用量占其 CPU limit 的比例(5 分钟均值)。',
      unit: 'percent',
      query:
        '100 * ( sum(irate(prometheus_remote_write_container_cpu_usage_seconds_total{instance_type="k8s",__$labels__}[5m])) by (instance_id,pod) / on(instance_id,pod) sum(prometheus_remote_write_kube_pod_container_resource_limits{instance_type="k8s", resource="cpu",__$labels__}) by (instance_id,pod) )',
      color: '#2f6bff'
    },
    {
      name: 'pod_memory_utilization',
      display_name: '内存使用率',
      description: 'Pod 工作集内存(实际占用、不可被回收的内存)占 memory limit 的比例,越低越好。',
      unit: 'percent',
      query:
        '100 * ( sum(prometheus_remote_write_container_memory_working_set_bytes{instance_type="k8s",__$labels__}) by (instance_id,pod) / on(instance_id,pod) sum(prometheus_remote_write_kube_pod_container_resource_limits{instance_type="k8s", resource="memory",__$labels__}) by (instance_id,pod) )',
      color: '#27c274'
    },
    {
      name: 'pod_network_in_rate',
      display_name: '入站吞吐',
      description: 'Pod 网络入站流量速率。',
      unit: 'byteps',
      query:
        'sum by (instance_id,pod) ( rate(prometheus_remote_write_container_network_receive_bytes_total{instance_type="k8s",__$labels__}[5m]) )',
      color: '#13c2c2'
    },
    {
      name: 'pod_network_out_rate',
      display_name: '出站吞吐',
      description: 'Pod 网络出站流量速率。',
      unit: 'byteps',
      query:
        'sum by (instance_id,pod) ( rate(prometheus_remote_write_container_network_transmit_bytes_total{instance_type="k8s",__$labels__}[5m]) )',
      color: '#597ef7'
    },
    {
      name: 'pod_io_reads_rate',
      display_name: '磁盘读 IOPS',
      description: 'Pod 每秒磁盘读操作次数。',
      unit: 'counts',
      query:
        'sum by (instance_id,pod,device) ( rate(prometheus_remote_write_container_fs_reads_total{instance_type="k8s",__$labels__}[5m]) )',
      color: '#9254de',
      dimensions: [{ name: 'device' }]
    },
    {
      name: 'pod_io_writes_rate',
      display_name: '磁盘写 IOPS',
      description: 'Pod 每秒磁盘写操作次数。',
      unit: 'counts',
      query:
        'sum by (instance_id,pod,device) ( rate(prometheus_remote_write_container_fs_writes_total{instance_type="k8s",__$labels__}[5m]) )',
      color: '#f5a623',
      dimensions: [{ name: 'device' }]
    }
  ],
  summaryCards: [
    {
      title: 'Pod 状态',
      guide: [{ label: 'Pod 状态', detail: 'Pod 当前生命周期阶段(运行中 / 未运行)。' }],
      metric: 'pod_status_phase',
      unit: 'none',
      color: '#27c274',
      icon: 'health',
      enumMap: POD_PHASE_ENUM
    },
    {
      title: 'CPU 使用率',
      guide: [{ label: 'CPU 使用率', detail: 'Pod CPU 使用占 limit 的比例,越低越好。' }],
      metric: 'pod_cpu_utilization',
      unit: 'percent',
      color: '#2f6bff',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down'
    },
    {
      title: '内存使用率',
      guide: [{ label: '内存使用率', detail: 'Pod 工作集内存(实际占用、不可被回收的内存)占 memory limit 的比例,越低越好。' }],
      metric: 'pod_memory_utilization',
      unit: 'percent',
      color: '#27c274',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down'
    },
    {
      title: '容器重启数',
      guide: [{ label: '容器重启数', detail: 'Pod 内各容器自启动以来的累计重启次数(计数,非当前状态)。数字持续上升时,查看该 Pod 容器日志与上次退出原因。' }],
      metric: 'pod_container_restarts_total',
      unit: 'counts',
      color: '#ff4d4f',
      icon: 'unacked'
    }
  ],
  charts: [
    {
      title: '资源使用趋势',
      subtitle: 'CPU 与内存使用率',
      guide: [{ label: '资源使用', detail: 'Pod CPU 与内存使用率随时间变化。' }],
      metric: 'pod_cpu_utilization',
      series: [
        { metric: 'pod_cpu_utilization', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'pod_memory_utilization', label: '内存使用率', color: '#27c274', unit: 'percent' }
      ]
    },
    {
      title: '网络吞吐趋势',
      subtitle: '入站与出站',
      guide: [{ label: '网络吞吐', detail: 'Pod 入站与出站网络流量速率。' }],
      metric: 'pod_network_in_rate',
      series: [
        { metric: 'pod_network_in_rate', label: '入站', color: '#13c2c2', unit: 'byteps' },
        { metric: 'pod_network_out_rate', label: '出站', color: '#597ef7', unit: 'byteps' }
      ]
    }
  ],
  details: [
    {
      title: '磁盘 I/O',
      subtitle: '读 · 写 IOPS',
      rows: [
        { label: '读 IOPS', metric: 'pod_io_reads_rate', unit: 'counts' },
        { label: '写 IOPS', metric: 'pod_io_writes_rate', unit: 'counts' }
      ]
    }
  ]
};
