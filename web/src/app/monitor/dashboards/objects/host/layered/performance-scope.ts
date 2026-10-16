/** 性能页 KPI、趋势、详细指标用到的主机级查询。不含磁盘、网络、进程。 */
export const HOST_PERFORMANCE_METRIC_NAMES = [
  'cpu_usage_total',
  'cpu_usage_user_total',
  'cpu_usage_system_total',
  'cpu_usage_iowait_total',
  'cpu_usage_irq_total',
  'cpu_usage_steal_total',
  'system_load1',
  'system_load5',
  'system_load15',
  'cpu_n',
  'system_uptime',
  'mem_used_percent',
  'mem_available',
  'mem_total',
  'mem_used',
  'mem_cached',
  'mem_buffered',
  'mem_shared',
  'host_mem_swap_used_bytes',
  'host_mem_swap_total_bytes',
  'mem_swap_free',
  'nvidia_smi_utilization_gpu',
  'nvidia_smi_memory_used',
  'nvidia_smi_memory_total',
  'nvidia_smi_temperature_gpu'
] as const;

export type MetricBlockPhase = 'loading' | 'error' | 'ready';

/** 本块已有可画数据就就绪；否则仍在请求中保持 loading；相关查询都失败才是 error。 */
export const metricBlockPhase = (
  names: readonly string[],
  pending: ReadonlySet<string>,
  loadStateByName: Readonly<Record<string, 'success' | 'error' | undefined>>,
  hasValue: boolean
): MetricBlockPhase => {
  if (hasValue) return 'ready';
  if (names.some((name) => pending.has(name))) return 'loading';
  const involved = names.filter((name) => loadStateByName[name]);
  if (involved.length > 0 && involved.every((name) => loadStateByName[name] === 'error')) return 'error';
  return 'ready';
};
