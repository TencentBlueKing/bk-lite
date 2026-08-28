import assert from 'node:assert/strict';
import type {
  ApplicationResourceNode,
  ApplicationResourceTopologyData,
} from '../src/app/cmdb/types/applicationResourceOverview';
import { resolveLayer } from '../src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/resolveLayer';

function node(partial: Partial<ApplicationResourceNode> & Pick<ApplicationResourceNode, 'id'>): ApplicationResourceNode {
  return {
    name: partial.name || partial.id,
    model_id: 'custom',
    hop: 1,
    category: 'other',
    ...partial,
  };
}

const root = node({ id: 'sys', model_id: 'system', hop: 0, category: 'application' });

function topology(nodes: ApplicationResourceNode[], links: ApplicationResourceTopologyData['links'] = []): ApplicationResourceTopologyData {
  return {
    center: root,
    nodes: [root, ...nodes],
    links,
    truncated: false,
  };
}

const customOnInfra = node({
  id: 'biz',
  model_id: 'custom_biz',
  category: 'other',
  app_topo_layer: 'service',
});
const mysqlOnHost = node({
  id: 'db',
  model_id: 'mysql',
  category: 'database',
  app_topo_layer: 'host',
});
const mysqlFallback = node({
  id: 'db-fallback',
  model_id: 'mysql',
  category: 'database',
});
const vmLinkedToHost = node({
  id: 'vm',
  model_id: 'vmware_vm',
  category: 'host',
});
const hostNode = node({
  id: 'host-a',
  model_id: 'host',
  category: 'host',
});

const graph = topology(
  [customOnInfra, mysqlOnHost, mysqlFallback, vmLinkedToHost, hostNode],
  [
    { id: 'l1', source: 'vm', target: 'host-a' },
  ]
);

assert.equal(resolveLayer(graph, root, root), 'root');
assert.equal(resolveLayer(graph, customOnInfra, root), 'service');
assert.equal(resolveLayer(graph, mysqlOnHost, root), 'host');
assert.equal(resolveLayer(graph, mysqlFallback, root), 'appService');
assert.equal(resolveLayer(graph, vmLinkedToHost, root), 'host');
assert.equal(resolveLayer(graph, hostNode, root), 'host');

const unclassified = node({
  id: 'k8s',
  model_id: 'k8s_cluster',
  category: 'other',
  app_topo_layer: 'none',
});
assert.equal(resolveLayer(graph, unclassified, root), null);

const relatedSystem = node({
  id: 'sys-b',
  model_id: 'system',
  category: 'application',
  app_topo_layer: 'system',
  hop: 1,
});
assert.equal(resolveLayer(graph, relatedSystem, root), 'root');

const centerIsMysql = node({
  id: 'center-db',
  model_id: 'mysql',
  category: 'database',
  app_topo_layer: 'appService',
  hop: 0,
});
assert.equal(resolveLayer(graph, centerIsMysql, centerIsMysql), 'root');

console.log('cmdb-app-topo-resolve-layer test passed');
