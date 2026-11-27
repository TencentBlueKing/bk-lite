/**
 * Docker 专业盘查询。20 分钟只取当前值和源时间，24 小时只探测有没有系列。
 * 趋势图走范围查询，不把窗口写进这些即时表达式。
 */
export const DOCKER_PRO_QUERY = {
  runningValue: 'last_over_time(docker_n_containers_running{__$labels__}[20m])',
  runningTime: 'tlast_over_time(docker_n_containers_running{__$labels__}[20m])',
  runningCapability: 'tlast_over_time(docker_n_containers_running{__$labels__}[24h])',
  stoppedValue: 'last_over_time(docker_n_containers_stopped{__$labels__}[20m])',
  stoppedTime: 'tlast_over_time(docker_n_containers_stopped{__$labels__}[20m])',
  stoppedCapability: 'tlast_over_time(docker_n_containers_stopped{__$labels__}[24h])',
  totalValue: 'last_over_time(docker_n_containers{__$labels__}[20m])',
  totalTime: 'tlast_over_time(docker_n_containers{__$labels__}[20m])',
  totalCapability: 'tlast_over_time(docker_n_containers{__$labels__}[24h])',
  cpuValue: 'last_over_time(docker_container_cpu_usage_percent{__$labels__}[20m])',
  cpuTime: 'tlast_over_time(docker_container_cpu_usage_percent{__$labels__}[20m])',
  cpuCapability: 'tlast_over_time(docker_container_cpu_usage_percent{__$labels__}[24h])',
  cpuChart: 'topk(8, max by (container_name) (docker_container_cpu_usage_percent{__$labels__}))',
  memPercentValue: 'last_over_time(docker_container_mem_usage_percent{__$labels__}[20m])',
  memPercentTime: 'tlast_over_time(docker_container_mem_usage_percent{__$labels__}[20m])',
  memPercentCapability: 'tlast_over_time(docker_container_mem_usage_percent{__$labels__}[24h])',
  memPercentChart: 'topk(8, max by (container_name) (docker_container_mem_usage_percent{__$labels__}))',
  memBytesValue: 'last_over_time(docker_container_mem_usage{__$labels__}[20m])',
  memBytesTime: 'tlast_over_time(docker_container_mem_usage{__$labels__}[20m])',
  memBytesCapability: 'tlast_over_time(docker_container_mem_usage{__$labels__}[24h])',
  memBytesChart: 'max by (container_name) (docker_container_mem_usage{__$labels__})',
  restartValue: 'last_over_time(docker_container_status_restart_count{__$labels__}[20m])',
  restartTime: 'tlast_over_time(docker_container_status_restart_count{__$labels__}[20m])'
} as const;

export type DockerProQueryKey = keyof typeof DOCKER_PRO_QUERY;
