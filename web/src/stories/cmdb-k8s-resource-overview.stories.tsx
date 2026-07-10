import React, { useMemo, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { K8sOverviewContent } from '@/app/cmdb/(pages)/assetData/detail/k8sResources/page';
import type { K8sBranchData, K8sOverviewData } from '@/app/cmdb/(pages)/assetData/detail/k8sResources/model';
import { mergeTopologyBranch } from '@/app/cmdb/(pages)/assetData/detail/k8sResources/model';
import { K8sResourceTable } from '@/app/cmdb/(pages)/assetData/detail/k8sResources/resourceTable';

const overview: K8sOverviewData = {
  summary: { namespace_count: 18, workload_count: 126, other_workload_count: 7, pod_count: 326, node_count: 23 },
  collection_facts: {
    last_reported_at: '2026-07-10 14:32:08',
    last_success_at: '2026-07-10 14:31:56',
    last_error: null,
    collector_task: '生产 K8S 集群采集',
  },
  layers: {
    namespace: { shown: 4, count: 18, page_size: 20 },
    workload: { shown: 4, count: 126, page_size: 50 },
    node: { shown: 3, count: 23, page_size: 50 },
  },
  topology: {
    nodes: [
      { id: '1', model_id: 'k8s_cluster', name: '银行集群（prod）', layer: 'cluster' },
      { id: '10', model_id: 'k8s_namespace', name: 'default', layer: 'namespace' },
      { id: '11', model_id: 'k8s_namespace', name: 'payment', layer: 'namespace' },
      { id: '12', model_id: 'k8s_namespace', name: 'bee-system', layer: 'namespace' },
      { id: '20', model_id: 'k8s_workload', name: 'payment-service', layer: 'workload', workload_type: 'deployment', pod_count: 46 },
      { id: '21', model_id: 'k8s_workload', name: 'payment-worker', layer: 'workload', workload_type: 'deployment', pod_count: 30 },
      { id: '22', model_id: 'k8s_workload', name: 'payment-mq', layer: 'workload', workload_type: 'statefulset', pod_count: 5 },
      { id: '30', model_id: 'k8s_node', name: 'node-10.0.1.32', layer: 'node' },
      { id: '31', model_id: 'k8s_node', name: 'node-10.0.1.18', layer: 'node' },
      { id: '32', model_id: 'k8s_node', name: 'node-10.0.1.20', layer: 'node' },
    ],
    edges: [
      { id: 'e1', source: '1', target: '10', kind: 'cluster-namespace' },
      { id: 'e2', source: '1', target: '11', kind: 'cluster-namespace' },
      { id: 'e3', source: '1', target: '12', kind: 'cluster-namespace' },
      { id: 'e4', source: '11', target: '20', kind: 'namespace-workload' },
      { id: 'e5', source: '11', target: '21', kind: 'namespace-workload' },
      { id: 'e6', source: '11', target: '22', kind: 'namespace-workload' },
      { id: 'e7', source: '1', target: '30', kind: 'cluster-node' },
      { id: 'e8', source: '1', target: '31', kind: 'cluster-node' },
      { id: 'e9', source: '1', target: '32', kind: 'cluster-node' },
    ],
  },
};

const branch: K8sBranchData = {
  count: 46, page: 1, page_size: 50,
  nodes: [
    { id: '40', model_id: 'k8s_pod', name: 'payment-svc-7d8f6cfd-a2d9', layer: 'pod' },
    { id: '41', model_id: 'k8s_pod', name: 'payment-svc-7d8f6cfd-b7km', layer: 'pod' },
    { id: '42', model_id: 'k8s_pod', name: 'payment-svc-7d8f6cfd-x8pq', layer: 'pod' },
  ],
  edges: [
    { id: 'p1', source: '20', target: '40', kind: 'workload-pod' },
    { id: 'p2', source: '20', target: '41', kind: 'workload-pod' },
    { id: 'p3', source: '20', target: '42', kind: 'workload-pod' },
    { id: 'n1', source: '40', target: '30', kind: 'pod-node' },
    { id: 'n2', source: '41', target: '31', kind: 'pod-node' },
    { id: 'n3', source: '42', target: 'virtual:unscheduled', kind: 'pod-node' },
  ],
};
branch.nodes.push({ id: 'virtual:unscheduled', model_id: 'virtual', name: '未调度', layer: 'node' });

const longTopology = {
  nodes: [
    { id: 'long-cluster', model_id: 'k8s_cluster', name: '生产集群', layer: 'cluster' as const },
    ...Array.from({ length: 12 }, (_, index) => [
      { id: `long-ns-${index}`, model_id: 'k8s_namespace', name: `namespace-${String(index + 1).padStart(2, '0')}`, layer: 'namespace' as const },
      { id: `long-workload-${index}`, model_id: 'k8s_workload', name: `service-${String(index + 1).padStart(2, '0')}`, layer: 'workload' as const, workload_type: 'deployment', pod_count: 1 },
      { id: `long-pod-${index}`, model_id: 'k8s_pod', name: `service-${String(index + 1).padStart(2, '0')}-7d8f`, layer: 'pod' as const },
      { id: `long-node-${index}`, model_id: 'k8s_node', name: `node-10.0.2.${index + 1}`, layer: 'node' as const },
    ]).flat(),
  ],
  edges: Array.from({ length: 12 }, (_, index) => [
    { id: `long-cluster-ns-${index}`, source: 'long-cluster', target: `long-ns-${index}`, kind: 'cluster-namespace' },
    { id: `long-ns-workload-${index}`, source: `long-ns-${index}`, target: `long-workload-${index}`, kind: 'namespace-workload' },
    { id: `long-workload-pod-${index}`, source: `long-workload-${index}`, target: `long-pod-${index}`, kind: 'workload-pod' },
    { id: `long-pod-node-${index}`, source: `long-pod-${index}`, target: `long-node-${index}`, kind: 'pod-node' },
  ]).flat(),
};

const Prototype = () => {
  const [expanded, setExpanded] = useState(new Set(['20']));
  const topology = useMemo(() => expanded.has('20') ? mergeTopologyBranch(overview.topology, branch) : overview.topology, [expanded]);
  return <div style={{ width: '100%', minHeight: 860, boxSizing: 'border-box', padding: 20, background: '#f5f7fb' }}>
    <K8sOverviewContent
      data={overview}
      topology={topology}
      expanded={expanded}
      branches={{ 20: { status: 'loaded', page: 1, loaded: 3, count: 46, data: branch } }}
      onToggleWorkload={(id) => setExpanded((current) => {
        const next = new Set(current);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      })}
      onLoadMorePods={() => undefined}
      onLoadMoreLayer={() => undefined}
      onOpenList={() => undefined}
      unownedExpanded={false}
      onToggleUnowned={() => undefined}
    />
  </div>;
};

const LongTopologyPrototype = () => (
  <div style={{ width: '100%', minHeight: 860, boxSizing: 'border-box', padding: 20, background: '#f5f7fb' }}>
    <K8sOverviewContent
      data={{
        ...overview,
        summary: { namespace_count: 12, workload_count: 12, other_workload_count: 0, pod_count: 12, node_count: 12 },
        layers: {
          namespace: { shown: 12, count: 12, page_size: 20 },
          workload: { shown: 12, count: 12, page_size: 50 },
          node: { shown: 12, count: 12, page_size: 50 },
        },
        topology: longTopology,
      }}
      topology={longTopology}
      expanded={new Set(longTopology.nodes.filter((node) => node.layer === 'workload').map((node) => node.id))}
      branches={Object.fromEntries(
        longTopology.nodes
          .filter((node) => node.layer === 'workload')
          .map((node) => [node.id, { status: 'loaded', page: 1, loaded: 1, count: 1 }])
      )}
      onToggleWorkload={() => undefined}
      onLoadMorePods={() => undefined}
      onLoadMoreLayer={() => undefined}
      onOpenList={() => undefined}
      unownedExpanded={false}
      onToggleUnowned={() => undefined}
    />
  </div>
);

const ResourceListPrototype = () => {
  const items = [
    ['local-path-provisioner', 'kube-system', 1, 1],
    ['coredns', 'kube-system', 2, 2],
    ['telegraf-resource', 'monitoring', 1, 1],
    ['kube-state-metrics', 'monitoring', 1, 1],
    ['kubernetes-event-exporter', 'monitoring', 1, 1],
    ['gateway', 'default', 3, 3],
  ].map(([name, namespace, replicas, podCount], index) => ({
    id: String(index + 1), name, namespace, workload_type: 'deployment', replicas, pod_count: podCount,
  }));
  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', sorter: true, render: (value: unknown) => <a>{String(value)}</a> },
    { title: '命名空间', dataIndex: 'namespace', key: 'namespace', sorter: true },
    { title: '类型', dataIndex: 'workload_type', key: 'workload_type', sorter: true },
    { title: '副本数', dataIndex: 'replicas', key: 'replicas', sorter: true },
    { title: 'Pod', dataIndex: 'pod_count', key: 'pod_count', sorter: true },
  ];
  return <div style={{ width: '100%', height: 620, boxSizing: 'border-box', padding: 24, background: '#fff' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
      <div style={{ width: 280, height: 32, padding: '5px 12px', border: '1px solid #d9d9d9', borderRadius: 6, color: '#8c8c8c' }}>搜索名称</div>
      <button style={{ height: 32, padding: '0 15px', border: '1px solid #d9d9d9', borderRadius: 6, background: '#fff' }}>刷新</button>
    </div>
    <K8sResourceTable
      items={items}
      columns={columns}
      loading={false}
      page={1}
      pageSize={20}
      count={128}
      onPageChange={() => undefined}
      onSortChange={() => undefined}
    />
  </div>;
};

const meta = {
  title: 'CMDB/K8S 资源详情/概览',
  parameters: { layout: 'fullscreen' },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const DefaultExpandedWorkload: Story = { name: '默认展开一个 Workload', render: () => <Prototype /> };
export const LongScrollableTopology: Story = { name: '长列共享滚动', render: () => <LongTopologyPrototype /> };
export const ReadonlyResourceList: Story = { name: '只读资源列表', render: () => <ResourceListPrototype /> };
