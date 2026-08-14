import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  filterRelationLinks,
  resolveNeighborhood,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/nodeFocus';

const links = [
  { id: 'l1', source: 'sys', target: 'app-a', asst_id: 'contains' },
  { id: 'l2', source: 'app-a', target: 'host-1', asst_id: 'runs_on' },
  { id: 'l3', source: 'app-a', target: 'host-2', asst_id: 'runs_on' },
  { id: 'l4', source: 'app-b', target: 'host-2', asst_id: 'runs_on' },
  { id: 'l5', source: 'host-1', target: 'mysql-1', asst_id: 'connects' },
];

const empty = resolveNeighborhood(links, null);
assert.equal(empty.nodeIds.size, 0);
assert.equal(empty.linkIds.size, 0);

const isolated = resolveNeighborhood(links, 'orphan');
assert.deepEqual([...isolated.nodeIds], ['orphan']);
assert.equal(isolated.linkIds.size, 0);

const appA = resolveNeighborhood(links, 'app-a');
assert.deepEqual([...appA.nodeIds].sort(), ['app-a', 'host-1', 'host-2', 'sys']);
assert.deepEqual([...appA.linkIds].sort(), ['l1', 'l2', 'l3']);
assert.ok(!appA.nodeIds.has('app-b'));
assert.ok(!appA.nodeIds.has('mysql-1'));
assert.ok(!appA.linkIds.has('l5'));

const nodes = new Map([
  ['sys', { name: 'sys-ecom' }],
  ['app-a', { name: 'checkout-svc' }],
  ['app-b', { name: 'pay-svc' }],
  ['host-1', { name: 'host-web-01' }],
  ['host-2', { name: 'host-api-01' }],
  ['mysql-1', { name: 'mysql-core' }],
]);

assert.equal(filterRelationLinks(links, nodes, '').length, 5);
assert.equal(filterRelationLinks(links, nodes, '   ').length, 5);

const byName = filterRelationLinks(links, nodes, 'checkout-svc');
assert.deepEqual(byName.map((link) => link.id).sort(), ['l1', 'l2', 'l3']);

const byPartialHost = filterRelationLinks(links, nodes, 'web-01');
assert.deepEqual(byPartialHost.map((link) => link.id).sort(), ['l2', 'l5']);

const byRelation = filterRelationLinks(links, nodes, 'CONTAINS');
assert.deepEqual(byRelation.map((link) => link.id), ['l1']);

const byId = filterRelationLinks(links, nodes, 'mysql-1');
assert.deepEqual(byId.map((link) => link.id), ['l5']);

assert.equal(filterRelationLinks(links, nodes, 'no-such-node').length, 0);

const focusedAppA = filterRelationLinks(links, nodes, '', 'app-a');
assert.deepEqual(focusedAppA.map((link) => link.id).sort(), ['l1', 'l2', 'l3']);

const focusedThenSearch = filterRelationLinks(links, nodes, 'web-01', 'app-a');
assert.deepEqual(focusedThenSearch.map((link) => link.id), ['l2']);

const byReverseType = filterRelationLinks(
  [{ id: 'l6', source: 'sys', target: 'app-a', asst_id: 'contains', model_asst_id: 'is_contained_in' }],
  nodes,
  'contained'
);
assert.deepEqual(byReverseType.map((link) => link.id), ['l6']);

const overviewSrc = fs.readFileSync(
  path.resolve('src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/index.tsx'),
  'utf8'
);
assert.match(overviewSrc, /onNodeClick=\{handleSelectNode\}/);
assert.match(overviewSrc, /onBlankClick=\{handleClearNodeFocus\}/);
assert.match(overviewSrc, /handleViewRelations/);
assert.match(overviewSrc, /handleViewNodeDetail/);
assert.match(overviewSrc, /buildBaseInfoPath/);
assert.match(overviewSrc, /ApplicationResourceOverview\.viewRelations/);
assert.match(overviewSrc, /ViewsHub\.viewDetail/);
assert.match(overviewSrc, /relationSearchPlaceholder/);
assert.match(overviewSrc, /relationFocusNodeId/);

const zhSrc = fs.readFileSync(path.resolve('src/app/cmdb/locales/zh.json'), 'utf8');
assert.match(zhSrc, /"viewRelations": "查看关联"/);
assert.match(zhSrc, /"relationSearchPlaceholder": "搜索源、目标或关系"/);

console.log('cmdb-app-topology-node-focus test passed');
