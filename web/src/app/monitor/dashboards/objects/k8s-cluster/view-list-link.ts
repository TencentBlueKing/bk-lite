/** 列表已有的指标列：与 display_field_key(plugin, metric) / 后端 ordering 白名单一致。 */
export const K8S_VIEW_POD_CPU_ORDERING = 'K8S::pod_cpu_utilization';
export const K8S_VIEW_POD_MEM_ORDERING = 'K8S::pod_memory_utilization';
export const K8S_VIEW_NODE_MEM_ORDERING = 'K8S::node_memory_utilization';

export function resolveMonitorObjectIdByName(
  data: unknown,
  name: string
): string {
  if (!Array.isArray(data)) return '';
  for (const item of data) {
    if (!item || typeof item !== 'object') continue;
    const row = item as { name?: string; id?: string | number };
    if (row.name === name && row.id != null) return String(row.id);
  }
  return '';
}

export function buildK8sClusterViewListHref(options: {
  objectId: string;
  clusterInstanceId: string;
  ordering?: string;
}): string | null {
  const objectId = String(options.objectId || '').trim();
  const clusterInstanceId = String(options.clusterInstanceId || '').trim();
  if (!objectId || !clusterInstanceId) return null;
  const params = new URLSearchParams();
  params.set('object_id', objectId);
  params.set('vm_params.instance_id', clusterInstanceId);
  if (options.ordering) {
    params.set('ordering', options.ordering);
    params.set('order', 'desc');
  }
  return `/monitor/view?${params.toString()}`;
}
