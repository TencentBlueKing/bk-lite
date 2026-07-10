export type K8sLayer = 'cluster' | 'namespace' | 'workload' | 'pod' | 'node';
export type K8sResourceKind =
  | 'namespace'
  | 'deployment'
  | 'statefulset'
  | 'daemonset'
  | 'job'
  | 'cronjob'
  | 'other_workload'
  | 'pod'
  | 'node';
export type K8sResourceSubView = 'overview' | K8sResourceKind;
export type K8sResourceNavGroup = 'base' | 'workload' | 'pod' | 'node';

export interface K8sTopologyNode {
  id: string;
  model_id: string;
  name: string;
  layer: K8sLayer;
  workload_type?: string;
  pod_count?: number;
}

export interface K8sTopologyEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
}

export interface K8sTopologyData {
  nodes: K8sTopologyNode[];
  edges: K8sTopologyEdge[];
}

export interface K8sOverviewData {
  summary: {
    namespace_count: number;
    workload_count: number;
    other_workload_count: number;
    pod_count: number;
    node_count: number;
  };
  collection_facts: Record<string, string | null | undefined>;
  topology: K8sTopologyData;
  layers: Record<'namespace' | 'workload' | 'node', { shown: number; count: number; page_size: number }>;
}

export interface K8sBranchData extends K8sTopologyData {
  count: number;
  page: number;
  page_size: number;
}

export interface K8sResourceColumn {
  key: string;
  title: string;
}

export const K8S_TOPOLOGY_LAYERS: K8sLayer[] = ['cluster', 'namespace', 'workload', 'pod', 'node'];

export const K8S_RESOURCE_NAV_ITEMS: Array<{ key: K8sResourceSubView; label: string; group: K8sResourceNavGroup }> = [
  { key: 'overview', label: '概览', group: 'base' },
  { key: 'namespace', label: '命名空间', group: 'base' },
  { key: 'deployment', label: 'Deployment', group: 'workload' },
  { key: 'statefulset', label: 'StatefulSet', group: 'workload' },
  { key: 'daemonset', label: 'DaemonSet', group: 'workload' },
  { key: 'job', label: 'Job', group: 'workload' },
  { key: 'cronjob', label: 'CronJob', group: 'workload' },
  { key: 'other_workload', label: '其他工作负载', group: 'workload' },
  { key: 'pod', label: 'Pod', group: 'pod' },
  { key: 'node', label: 'Node', group: 'node' },
];

const COLUMN_MAP: Record<K8sResourceKind, K8sResourceColumn[]> = {
  namespace: [
    { key: 'name', title: '名称' },
    { key: 'workload_count', title: '工作负载' },
    { key: 'pod_count', title: 'Pod' },
  ],
  deployment: [], statefulset: [], daemonset: [], job: [], cronjob: [], other_workload: [],
  pod: [
    { key: 'name', title: '名称' }, { key: 'namespace', title: '命名空间' },
    { key: 'workload', title: '工作负载' }, { key: 'node', title: 'Node' },
    { key: 'ip_addr', title: 'Pod IP' }, { key: 'request_cpu', title: 'CPU 请求' },
    { key: 'request_memory', title: '内存请求' }, { key: 'limit_cpu', title: 'CPU 限制' },
    { key: 'limit_memory', title: '内存限制' },
  ],
  node: [
    { key: 'name', title: '名称' }, { key: 'role', title: '角色' },
    { key: 'cpu', title: 'CPU' }, { key: 'memory', title: '内存' }, { key: 'disk', title: '磁盘' },
  ],
};

const WORKLOAD_COLUMNS: K8sResourceColumn[] = [
  { key: 'name', title: '名称' }, { key: 'namespace', title: '命名空间' },
  { key: 'workload_type', title: '类型' }, { key: 'replicas', title: '副本数' },
  { key: 'pod_count', title: 'Pod' },
];

export const getK8sResourceColumns = (kind: K8sResourceKind) =>
  COLUMN_MAP[kind].length ? COLUMN_MAP[kind] : WORKLOAD_COLUMNS;

type UrlAction = 'overview' | 'layer' | 'workloadPods' | 'unownedPods' | 'resources';
interface UrlOptions {
  layer?: 'namespace' | 'workload' | 'node'; workloadId?: string; kind?: K8sResourceKind;
  page?: number; pageSize?: number; search?: string; order?: string;
  namespaceId?: string; workloadFilterId?: string; nodeId?: string; namespaceIds?: string[];
}

export const buildK8sResourceUrl = (action: UrlAction, clusterId: string, options: UrlOptions = {}) => {
  if (action === 'overview') return `/cmdb/api/instance/k8s_resource_overview/${clusterId}/`;
  const path = action === 'workloadPods'
    ? `/cmdb/api/instance/k8s_workload_pods/${clusterId}/${options.workloadId}/`
    : action === 'unownedPods'
      ? `/cmdb/api/instance/k8s_unowned_pods/${clusterId}/`
      : action === 'layer'
        ? `/cmdb/api/instance/k8s_resource_layer/${clusterId}/${options.layer}/`
        : `/cmdb/api/instance/k8s_resource_list/${clusterId}/${options.kind}/`;
  const query = new URLSearchParams();
  if (options.page) query.set('page', String(options.page));
  const defaultPageSize = action === 'resources' ? 20 : action === 'layer' && options.layer === 'namespace' ? 20 : 50;
  query.set('page_size', String(options.pageSize || defaultPageSize));
  if (options.search) query.set('search', options.search);
  if (options.order) query.set('order', options.order);
  if (options.namespaceId) query.set('namespace_id', options.namespaceId);
  if (options.workloadFilterId) query.set('workload_id', options.workloadFilterId);
  if (options.nodeId) query.set('node_id', options.nodeId);
  if (options.namespaceIds?.length) query.set('namespace_ids', options.namespaceIds.join(','));
  return `${path}?${query.toString()}`;
};

export const mergeTopologyBranch = (base: K8sTopologyData, branch: K8sTopologyData): K8sTopologyData => ({
  nodes: [...new Map([...base.nodes, ...branch.nodes].map((item) => [item.id, item])).values()],
  edges: [...new Map([...base.edges, ...branch.edges].map((item) => [item.id, item])).values()],
});

interface QueueItem<T> {
  key: string;
  run: () => Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

export class PodBranchQueue {
  private active = 0;
  private readonly waiting: QueueItem<unknown>[] = [];

  constructor(private readonly concurrency = 4) {}

  enqueue<T>(key: string, run: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.waiting.push({ key, run, resolve, reject } as QueueItem<unknown>);
      this.drain();
    });
  }

  cancelWaiting(key: string) {
    const index = this.waiting.findIndex((item) => item.key === key);
    if (index >= 0) this.waiting.splice(index, 1).forEach((item) => item.reject(new Error('cancelled')));
  }

  private drain() {
    while (this.active < this.concurrency && this.waiting.length) {
      const item = this.waiting.shift();
      if (!item) return;
      this.active += 1;
      item.run().then(item.resolve, item.reject).finally(() => {
        this.active -= 1;
        this.drain();
      });
    }
  }
}
