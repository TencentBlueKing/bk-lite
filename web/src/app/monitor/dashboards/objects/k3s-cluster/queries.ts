import type { MetricUnit } from '../../shared/types';

// 健康色与阈值(命名常量)
export const HEALTH_GREEN = '#27c274';
export const HEALTH_AMBER = '#faad14';
export const HEALTH_RED = '#ff4d4f';
export const NEUTRAL_BLUE = '#2f6bff';
export const RING_REST = '#e8edf5';
export const RING_DONE = '#dfe5ef';    // 良性终态(Succeeded):更浅的中性
export const NEUTRAL_INK = '#1f2937';  // KPI 数值「健康/中性」深色
export const SATURATION_WARN = 70;
export const SATURATION_CRIT = 85;
// 排行榜统一展示条数:同时驱动 topk(N) 拉取与前端 buildTopBars 截断,
// 避免「后端取 8、前端只显示 5」式的取多丢少和散落的魔法数 5。
export const TOP_N = 5;

const L = '{instance_type="k3s",__$labels__}';

export interface ClusterQuery {
  query: string;
  unit: MetricUnit;
}

// 标量/聚合查询(取 latest);趋势查询(memPct/cpuPct/diskPct)同时用于 hero 饱和度 latest 与趋势图。
export const QUERIES: Record<string, ClusterQuery> = {
  collection: { query: `count(prometheus_remote_write_kube_node_info${L}) by (instance_id)`, unit: 'none' },

  nodesReady: { query: `sum(prometheus_remote_write_kube_node_status_condition{instance_type="k3s",condition="Ready",status="true",__$labels__})`, unit: 'none' },
  nodesTotal: { query: `count(prometheus_remote_write_kube_node_info${L})`, unit: 'none' },

  podPhase: { query: `sum(prometheus_remote_write_kube_pod_status_phase${L}) by (phase)`, unit: 'none' },
  podsTotal: { query: `count(prometheus_remote_write_kube_pod_info${L})`, unit: 'none' },
  namespaces: { query: `count(count(prometheus_remote_write_kube_pod_info${L}) by (namespace))`, unit: 'none' },

  deployTotal: { query: `count(prometheus_remote_write_kube_deployment_spec_replicas${L})`, unit: 'none' },
  deployDegraded: { query: `count(prometheus_remote_write_kube_deployment_status_replicas_unavailable${L} > 0)`, unit: 'none' },
  dsTotal: { query: `count(prometheus_remote_write_kube_daemonset_status_desired_number_scheduled${L})`, unit: 'none' },
  dsDegraded: { query: `count(prometheus_remote_write_kube_daemonset_status_number_unavailable${L} > 0)`, unit: 'none' },
  stsTotal: { query: `count(prometheus_remote_write_kube_statefulset_replicas${L})`, unit: 'none' },
  stsDegraded: { query: `count(prometheus_remote_write_kube_statefulset_status_replicas_ready${L} < prometheus_remote_write_kube_statefulset_replicas${L})`, unit: 'none' },

  crashloop: { query: `count(prometheus_remote_write_kube_pod_container_status_waiting_reason{instance_type="k3s",reason="CrashLoopBackOff",__$labels__} > 0)`, unit: 'none' },
  restarts1h: { query: `sum(increase(prometheus_remote_write_kube_pod_container_status_restarts_total${L}[1h]))`, unit: 'counts' },

  deployPct: { query: `100 * sum(prometheus_remote_write_kube_deployment_status_replicas_available${L}) / clamp_min(sum(prometheus_remote_write_kube_deployment_spec_replicas${L}),1)`, unit: 'percent' },
  stsPct: { query: `100 * sum(prometheus_remote_write_kube_statefulset_status_replicas_ready${L}) / clamp_min(sum(prometheus_remote_write_kube_statefulset_replicas${L}),1)`, unit: 'percent' },
  dsPct: { query: `100 * sum(prometheus_remote_write_kube_daemonset_status_number_available${L}) / clamp_min(sum(prometheus_remote_write_kube_daemonset_status_desired_number_scheduled${L}),1)`, unit: 'percent' },

  cpuAllocatable: { query: `sum(prometheus_remote_write_kube_node_status_allocatable{instance_type="k3s",resource="cpu", __$labels__})`, unit: 'none' },
  cpuRequests: { query: `sum(prometheus_remote_write_kube_pod_container_resource_requests{instance_type="k3s",resource="cpu", __$labels__})`, unit: 'none' },
  cpuUsedCores: { query: `sum(irate(prometheus_remote_write_container_cpu_usage_seconds_total{instance_type="k3s", __$labels__}[5m]))`, unit: 'none' },
  memAllocatable: { query: `sum(prometheus_remote_write_kube_node_status_allocatable{instance_type="k3s",resource="memory", __$labels__})`, unit: 'bytes' },
  memRequests: { query: `sum(prometheus_remote_write_kube_pod_container_resource_requests{instance_type="k3s",resource="memory", __$labels__})`, unit: 'bytes' },
  memUsedBytes: { query: `sum(prometheus_remote_write_container_memory_working_set_bytes{instance_type="k3s", __$labels__})`, unit: 'bytes' },

  nodeMemTop: { query: `topk(${TOP_N}, mem_used_percent${L})`, unit: 'percent' },
  restartTop: { query: `topk(${TOP_N}, sum by (pod) (increase(prometheus_remote_write_kube_pod_container_status_restarts_total${L}[1h])))`, unit: 'counts' },

  topPodCpu: { query: `topk(${TOP_N}, sum by (pod) (rate(prometheus_remote_write_container_cpu_usage_seconds_total${L}[5m])))`, unit: 'none' },
  topPodMem: { query: `topk(${TOP_N}, sum by (pod) (prometheus_remote_write_container_memory_working_set_bytes${L}))`, unit: 'bytes' },
  topNsMem: { query: `topk(${TOP_N}, sum by (namespace) (prometheus_remote_write_container_memory_working_set_bytes${L}))`, unit: 'bytes' },

  memPct: { query: `100 * sum(mem_used${L}) / sum(mem_total${L})`, unit: 'percent' },
  cpuPct: { query: `100 - avg(cpu_usage_idle{instance_type="k3s",cpu="cpu-total",__$labels__})`, unit: 'percent' },
  diskPct: { query: `100 * sum(any(disk_used${L}) by (instance_id, device)) / sum(any(disk_total${L}) by (instance_id, device))`, unit: 'percent' }
};

// 趋势图的三条线 metric 配置(用于 toMetricSeries / buildMetricItem)
export const TREND_METRICS = [
  { name: 'memPct', display_name: '内存使用率', description: '集群内存使用率。', unit: 'percent' as MetricUnit, query: QUERIES.memPct.query, color: HEALTH_GREEN },
  { name: 'cpuPct', display_name: 'CPU 使用率', description: '集群 CPU 使用率。', unit: 'percent' as MetricUnit, query: QUERIES.cpuPct.query, color: NEUTRAL_BLUE },
  { name: 'diskPct', display_name: '磁盘使用率', description: '集群磁盘使用率。', unit: 'percent' as MetricUnit, query: QUERIES.diskPct.query, color: '#ff8a1f' }
];

// 并发与分组(hero 先到,面板后到)
export const QUERY_CONCURRENCY = 6;
export const QUERY_GROUPS: Record<string, string[]> = {
  hero: ['collection', 'nodesReady', 'nodesTotal', 'podPhase', 'podsTotal', 'namespaces', 'deployTotal', 'deployDegraded', 'dsTotal', 'dsDegraded', 'stsTotal', 'stsDegraded', 'crashloop', 'restarts1h', 'memPct', 'cpuPct', 'diskPct'],
  panels: ['deployPct', 'stsPct', 'dsPct', 'cpuAllocatable', 'cpuRequests', 'cpuUsedCores', 'memAllocatable', 'memRequests', 'memUsedBytes', 'nodeMemTop', 'restartTop', 'topPodCpu', 'topPodMem', 'topNsMem']
};

export const NS_LABEL = 'namespace';
