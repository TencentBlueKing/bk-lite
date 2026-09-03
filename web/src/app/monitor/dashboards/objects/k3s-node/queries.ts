export const K3S_NODE_TOP_POD_CPU =
  'topk(5, sum by (pod) (rate(prometheus_remote_write_container_cpu_usage_seconds_total{instance_type="k3s",__$labels__}[5m])))';
export const K3S_NODE_TOP_POD_MEM =
  'topk(5, sum by (pod) (prometheus_remote_write_container_memory_working_set_bytes{instance_type="k3s",__$labels__}))';
