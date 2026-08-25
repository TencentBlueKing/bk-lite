import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  buildK8sResourceUrl,
  K8S_RESOURCE_NAV_ITEMS,
  K8S_TOPOLOGY_LAYERS,
  getK8sResourceColumns,
  mergeTopologyBranch,
  PodBranchQueue,
  stripK8sClusterScopedParams,
} from '../src/app/cmdb/(pages)/assetData/detail/k8sResources/model';
import {
  buildTopologyPaths,
  getTopologyFocus,
  groupTopologyNodes,
} from '../src/app/cmdb/(pages)/assetData/detail/k8sResources/topologyLayout';

assert.equal(buildK8sResourceUrl('overview', '9'), '/cmdb/api/instance/k8s_resource_overview/9/');
assert.equal(
  buildK8sResourceUrl('layer', '9', { layer: 'namespace', page: 2 }),
  '/cmdb/api/instance/k8s_resource_layer/9/namespace/?page=2&page_size=20'
);
assert.equal(
  buildK8sResourceUrl('workloadPods', '9', { workloadId: '21', page: 2 }),
  '/cmdb/api/instance/k8s_workload_pods/9/21/?page=2&page_size=50'
);
assert.equal(
  buildK8sResourceUrl('unownedPods', '9', { page: 1 }),
  '/cmdb/api/instance/k8s_unowned_pods/9/?page=1&page_size=50'
);
assert.equal(
  buildK8sResourceUrl('resources', '9', { kind: 'pod', page: 3, search: 'api server', namespaceId: '7' }),
  '/cmdb/api/instance/k8s_resource_list/9/pod/?page=3&page_size=20&search=api+server&namespace_id=7'
);

const keptParams = new URLSearchParams('sub=pod&inst_uuid=cluster-a');
assert.equal(stripK8sClusterScopedParams(keptParams), false);
assert.equal(keptParams.toString(), 'sub=pod&inst_uuid=cluster-a');

const scopedParams = new URLSearchParams('sub=pod&namespace_id=ns-1&workload_id=wl-1&node_id=n-1&expanded_workloads=wl-1');
assert.equal(stripK8sClusterScopedParams(scopedParams), true);
assert.equal(scopedParams.get('sub'), 'pod');
assert.equal(scopedParams.get('expanded_workloads'), 'wl-1');
assert.equal(scopedParams.get('namespace_id'), null);
assert.equal(scopedParams.get('workload_id'), null);
assert.equal(scopedParams.get('node_id'), null);

assert.deepEqual(K8S_RESOURCE_NAV_ITEMS.map((item) => item.key), [
  'overview', 'namespace', 'deployment', 'statefulset', 'daemonset', 'job',
  'cronjob', 'other_workload', 'pod', 'node',
]);
assert.deepEqual(K8S_RESOURCE_NAV_ITEMS.map(({ key, group }) => [key, group]), [
  ['overview', 'base'], ['namespace', 'base'],
  ['deployment', 'workload'], ['statefulset', 'workload'],
  ['daemonset', 'workload'], ['job', 'workload'],
  ['cronjob', 'workload'], ['other_workload', 'workload'],
  ['pod', 'pod'], ['node', 'node'],
]);
assert.equal(K8S_RESOURCE_NAV_ITEMS.some((item) => /topology|network/i.test(item.key)), false);
assert.deepEqual(K8S_TOPOLOGY_LAYERS, ['cluster', 'namespace', 'workload', 'pod', 'node']);

const groupedTopologyNodes = groupTopologyNodes([
  { id: 'virtual-node', model_id: 'virtual', name: '未调度', layer: 'node' },
  { id: 'node-2', model_id: 'k8s_node', name: 'node-02', layer: 'node' },
  { id: 'node-1', model_id: 'k8s_node', name: 'node-01', layer: 'node' },
]);
assert.deepEqual(groupedTopologyNodes.node.map((node) => node.id), ['node-1', 'node-2', 'virtual-node']);
assert.deepEqual(groupedTopologyNodes.pod, []);

assert.deepEqual(
  buildTopologyPaths(
    [{ id: 'edge-1', source: 'source', target: 'target', kind: 'pod-node' }],
    new Map([
      ['source', { left: 0, top: 0, width: 100, height: 50 }],
      ['target', { left: 200, top: 20, width: 100, height: 50 }],
    ])
  ),
  [{ id: 'edge-1', d: 'M 100 25 C 150 25, 150 45, 200 45' }]
);
assert.deepEqual(
  buildTopologyPaths(
    [{ id: 'missing-target', source: 'source', target: 'missing', kind: 'pod-node' }],
    new Map([['source', { left: 0, top: 0, width: 100, height: 50 }]])
  ),
  []
);

const focusedWorkload = getTopologyFocus('workload-1', {
  nodes: [
    { id: 'cluster', model_id: 'k8s_cluster', name: 'cluster', layer: 'cluster' },
    { id: 'namespace-1', model_id: 'k8s_namespace', name: 'namespace-1', layer: 'namespace' },
    { id: 'namespace-2', model_id: 'k8s_namespace', name: 'namespace-2', layer: 'namespace' },
    { id: 'workload-1', model_id: 'k8s_workload', name: 'workload-1', layer: 'workload' },
    { id: 'workload-2', model_id: 'k8s_workload', name: 'workload-2', layer: 'workload' },
    { id: 'pod-1', model_id: 'k8s_pod', name: 'pod-1', layer: 'pod' },
    { id: 'node-1', model_id: 'k8s_node', name: 'node-1', layer: 'node' },
  ],
  edges: [
    { id: 'cluster-ns-1', source: 'cluster', target: 'namespace-1', kind: 'cluster-namespace' },
    { id: 'cluster-ns-2', source: 'cluster', target: 'namespace-2', kind: 'cluster-namespace' },
    { id: 'ns-workload-1', source: 'namespace-1', target: 'workload-1', kind: 'namespace-workload' },
    { id: 'ns-workload-2', source: 'namespace-2', target: 'workload-2', kind: 'namespace-workload' },
    { id: 'workload-pod-1', source: 'workload-1', target: 'pod-1', kind: 'workload-pod' },
    { id: 'pod-node-1', source: 'pod-1', target: 'node-1', kind: 'pod-node' },
  ],
});
assert.deepEqual([...focusedWorkload.nodes].sort(), [
  'cluster', 'namespace-1', 'node-1', 'pod-1', 'workload-1',
]);
assert.equal(focusedWorkload.nodes.has('namespace-2'), false);
assert.equal(focusedWorkload.nodes.has('workload-2'), false);

assert.deepEqual(getK8sResourceColumns('namespace').map((item) => item.key), ['name', 'workload_count', 'pod_count']);
assert.deepEqual(getK8sResourceColumns('pod').map((item) => item.key), [
  'name', 'namespace', 'workload', 'node', 'ip_addr', 'request_cpu',
  'request_memory', 'limit_cpu', 'limit_memory',
]);
assert.equal(getK8sResourceColumns('pod').some((item) => /yaml|operate|action/i.test(item.key)), false);

const menuConfig = fs.readFileSync('src/app/cmdb/constants/menu.json', 'utf8');
const sideMenuLayout = fs.readFileSync('src/app/cmdb/(pages)/assetData/components/sub-layout/index.tsx', 'utf8');
const pageSource = fs.readFileSync('src/app/cmdb/(pages)/assetData/detail/k8sResources/page.tsx', 'utf8');
const contentSource = fs.readFileSync(
  'src/app/cmdb/(pages)/assetData/detail/k8sResources/K8sResourceDetailsContent.tsx',
  'utf8'
);
const implSource = `${pageSource}\n${contentSource}`;
const topologySource = fs.readFileSync('src/app/cmdb/(pages)/assetData/detail/k8sResources/topology.tsx', 'utf8');
const stylesSource = fs.readFileSync('src/app/cmdb/(pages)/assetData/detail/k8sResources/styles.module.scss', 'utf8');
const resourceTablePath = 'src/app/cmdb/(pages)/assetData/detail/k8sResources/resourceTable.tsx';
assert.equal((menuConfig.match(/"name": "asset_k8s_resources"/g) || []).length, 2);
const parsedMenu = JSON.parse(menuConfig) as Record<string, Array<{
  url?: string;
  children?: Array<{ name: string }>;
}>>;
for (const locale of ['zh', 'en']) {
  const detailItems = parsedMenu[locale].find((item) => item.url === '/cmdb/assetData')?.children || [];
  const baseInfoIndex = detailItems.findIndex((item) => item.name === 'asset_basic_information');
  const resourceIndex = detailItems.findIndex((item) => item.name === 'asset_k8s_resources');
  const relationshipsIndex = detailItems.findIndex((item) => item.name === 'asset_relationships');
  assert.ok(resourceIndex > baseInfoIndex, `${locale}: 资源详情必须位于基础信息之后`);
  assert.ok(resourceIndex < relationshipsIndex, `${locale}: 资源详情必须位于关联关系之前`);
}
assert.match(sideMenuLayout, /menu\.name !== 'asset_k8s_resources' \|\| modelId === 'k8s_cluster'/);
// Detail page stays a thin searchParams → Content wrapper (hub injects instId directly).
assert.match(pageSource, /<K8sResourceDetailsContent\s+instUuid=\{instUuid\}\s*\/>/);
assert.match(pageSource, /searchParams\.get\('inst_uuid'\)/);
assert.match(contentSource, /K8sResourceDetailsContentProps/);
assert.match(contentSource, /instId\?:\s*string/);
assert.match(implSource, /sub === 'overview' && overview && <K8sOverviewContent/);
assert.match(implSource, /sub !== 'overview' && <K8sResourceList/);
assert.match(
  contentSource,
  /useEffect\(\(\) => \{ load\(\); \}, \[clusterId, kind, page, pageSize, order, namespaceFilter, workloadFilter, nodeFilter\]\)/,
  '资源列表必须在集群切换后重新拉取，不能只跟 kind/分页走'
);
assert.match(contentSource, /key=\{clusterId\}/, '切换集群时必须重置列表本地状态');
assert.match(contentSource, /stripK8sClusterScopedParams/, '切换集群时必须丢掉上一集群的列表筛选');
assert.match(implSource, /const branchCache = new Map/);
assert.match(implSource, /expanded_workloads/);
assert.match(implSource, /branchCache\.delete/);
assert.match(implSource, /getUnownedPods/);
assert.doesNotMatch(implSource, />\s*(编辑|查看 YAML|更多|批量|设置|下载)\s*</);
assert.doesNotMatch(implSource, /<Descriptions|K8sResourceOverview\.facts/);
assert.doesNotMatch(topologySource, /NetworkTopologyX6Canvas|buildNetworkTopologyX6GraphData|minimap|fitView/);
assert.match(topologySource, /<svg/);
assert.match(topologySource, /ResizeObserver/);
assert.match(topologySource, /data-topology-node/);
assert.match(topologySource, /role="button"/);
assert.match(topologySource, /onContextMenu=/);
assert.match(topologySource, /event\.shiftKey && event\.key === 'F10'/);
assert.match(stylesSource, /\.topologyViewport[\s\S]*overflow-y:\s*auto/);
assert.match(stylesSource, /\.topologyEdges[\s\S]*pointer-events:\s*none/);
assert.match(stylesSource, /flex:\s*0 0 220px/);
assert.match(stylesSource, /flex-basis:\s*56px/);
assert.match(implSource, /contentRect\.width - 220 < 1100/);
assert.match(implSource, /sessionStorage\.setItem\('cmdb-k8s-nav-collapsed'/);
assert.equal(fs.existsSync(resourceTablePath), true, 'K8S 资源列表必须抽取并复用资产实例 CustomTable');
const resourceTableSource = fs.readFileSync(resourceTablePath, 'utf8');
assert.match(resourceTableSource, /import CustomTable from '@\/components\/custom-table'/);
assert.match(resourceTableSource, /size="small"/);
assert.match(resourceTableSource, /fieldSetting=\{\{[\s\S]*showSetting: false/);
assert.doesNotMatch(resourceTableSource, /rowSelection=/);
assert.doesNotMatch(resourceTableSource, /calc\(100vh/, '表格高度必须由实际父容器计算');
assert.doesNotMatch(resourceTableSource, /import \{[^}]*Table[^}]*\} from 'antd'/);
assert.match(implSource, /<K8sResourceTable/);
assert.doesNotMatch(implSource, /<Table\s/);
assert.match(implSource, /target="_blank"/);
assert.match(implSource, /rel="noopener noreferrer"/);
assert.match(implSource, /styles\.listContent/);
assert.match(implSource, /wrapperClassName=\{styles\.listSpin\}/);
assert.match(implSource, /styles\.tableShell/);
assert.match(implSource, /styles\.overviewStage/);
assert.match(implSource, /styles\.metricGrid/);
assert.match(stylesSource, /\.listContent[\s\S]*overflow:\s*hidden/);
assert.match(stylesSource, /\.resourceList[\s\S]*overflow:\s*hidden/);
assert.match(stylesSource, /\.tableShell[\s\S]*flex:\s*1/);
assert.match(stylesSource, /\.topologyCard[\s\S]*flex:\s*1/);
assert.match(stylesSource, /\.topologyViewport[\s\S]*flex:\s*1/);
assert.doesNotMatch(stylesSource, /min-height:\s*98px/);
assert.doesNotMatch(stylesSource, /height:\s*520px/);

const merged = mergeTopologyBranch(
  { nodes: [{ id: 'node-1', layer: 'node', model_id: 'k8s_node', name: 'n1' }], edges: [] },
  {
    nodes: [
      { id: 'pod-1', layer: 'pod', model_id: 'k8s_pod', name: 'p1' },
      { id: 'node-1', layer: 'node', model_id: 'k8s_node', name: 'n1' },
    ],
    edges: [{ id: 'pod-node:1', source: 'pod-1', target: 'node-1', kind: 'pod-node' }],
  }
);
assert.equal(merged.nodes.filter((item) => item.id === 'node-1').length, 1);

async function testQueue() {
  const starts: string[] = [];
  const releases: Array<() => void> = [];
  const queue = new PodBranchQueue(4);
  const tasks = Array.from({ length: 6 }, (_, index) => queue.enqueue(`w${index}`, () => {
    starts.push(`w${index}`);
    return new Promise<void>((resolve) => releases.push(resolve));
  }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(starts.length, 4);
  releases.shift()?.();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(starts.length, 5);
  releases.forEach((release) => release());
  await new Promise((resolve) => setTimeout(resolve, 0));
  releases.forEach((release) => release());
  await Promise.all(tasks);
}

testQueue().then(() => console.log('cmdb-k8s-resource-overview test passed'));
