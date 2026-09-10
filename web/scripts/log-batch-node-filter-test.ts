/**
 * 日志批量接入节点下拉：已选节点一次构建 Set，成员查询 O(1)。
 *
 * 运行：tsx scripts/log-batch-node-filter-test.ts
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import {
  buildSelectedNodeIdSet,
  filterAvailableNodes,
} from '../src/app/log/hooks/integration/common/filterAvailableNodes';

interface NodeItem {
  id: unknown;
  name: string;
}

interface RowItem {
  node_ids?: unknown;
}

const filterByIncludes = (
  nodeList: NodeItem[],
  dataSource: RowItem[],
  currentRowNodeId: unknown,
  stats: { comparisons: number }
): NodeItem[] => {
  const nodeIds = dataSource
    .map((item) => item.node_ids)
    .filter((item) => item !== currentRowNodeId);
  return nodeList.filter((item) => {
    for (const occupiedId of nodeIds) {
      stats.comparisons += 1;
      if (occupiedId === item.id) {
        return false;
      }
    }
    return true;
  });
};

const filterBySetCounted = (
  nodeList: NodeItem[],
  selectedNodeIds: Set<unknown>,
  currentRowNodeId: unknown,
  stats: { lookups: number }
): NodeItem[] => {
  return nodeList.filter((item) => {
    if (item.id === currentRowNodeId) {
      return true;
    }
    stats.lookups += 1;
    return !selectedNodeIds.has(item.id);
  });
};

const countIncludesForAllRows = (rowCount: number, nodeCount: number) => {
  const nodeList = Array.from({ length: nodeCount }, (_, index) => ({
    id: `n${index}`,
    name: `node-${index}`,
  }));
  const dataSource = Array.from({ length: rowCount }, (_, index) => ({
    node_ids: `n${index % nodeCount}`,
  }));
  const stats = { comparisons: 0 };
  for (const row of dataSource) {
    filterByIncludes(nodeList, dataSource, row.node_ids, stats);
  }
  return stats.comparisons;
};

const countSetLookupsForAllRows = (rowCount: number, nodeCount: number) => {
  const nodeList = Array.from({ length: nodeCount }, (_, index) => ({
    id: `n${index}`,
    name: `node-${index}`,
  }));
  const dataSource = Array.from({ length: rowCount }, (_, index) => ({
    node_ids: `n${index % nodeCount}`,
  }));
  const selectedNodeIds = buildSelectedNodeIdSet(dataSource);
  const stats = { lookups: 0 };
  for (const row of dataSource) {
    filterBySetCounted(nodeList, selectedNodeIds, row.node_ids, stats);
  }
  return stats.lookups;
};

const nodeList: NodeItem[] = [
  { id: 'n1', name: 'alpha' },
  { id: 'n2', name: 'beta' },
  { id: 'n3', name: 'gamma' },
  { id: 'n4', name: 'delta' },
];

const dataSource: RowItem[] = [
  { node_ids: 'n1' },
  { node_ids: 'n2' },
  { node_ids: '' },
  { node_ids: 'n2' },
];

const selectedNodeIds = buildSelectedNodeIdSet(dataSource);

const idsOf = (nodes: NodeItem[]) => nodes.map((item) => item.id);

assert.deepEqual(
  idsOf(filterAvailableNodes(nodeList, selectedNodeIds, 'n1')),
  ['n1', 'n3', 'n4'],
  '当前行已选节点仍可选，其他行占用的节点不可选'
);
assert.deepEqual(
  idsOf(filterAvailableNodes(nodeList, selectedNodeIds, 'n2')),
  ['n2', 'n3', 'n4'],
  '重复已选值时当前行节点仍可选'
);
assert.deepEqual(
  idsOf(filterAvailableNodes(nodeList, selectedNodeIds, '')),
  ['n3', 'n4'],
  '空行不占用具体节点，但其他行已选节点仍不可选'
);

const includesStats = { comparisons: 0 };
assert.deepEqual(
  idsOf(filterByIncludes(nodeList, dataSource, 'n1', includesStats)),
  idsOf(filterAvailableNodes(nodeList, selectedNodeIds, 'n1')),
  'Set 过滤结果应与 includes 语义一致'
);
assert.deepEqual(
  idsOf(filterByIncludes(nodeList, dataSource, 'n2', { comparisons: 0 })),
  idsOf(filterAvailableNodes(nodeList, selectedNodeIds, 'n2')),
  '重复已选值时 Set 与 includes 语义一致'
);
assert.deepEqual(
  idsOf(filterByIncludes(nodeList, dataSource, '', { comparisons: 0 })),
  idsOf(filterAvailableNodes(nodeList, selectedNodeIds, '')),
  '空行时 Set 与 includes 语义一致'
);

const mixedNodes: NodeItem[] = [
  { id: 1, name: 'numeric' },
  { id: '1', name: 'string' },
  { id: 'n3', name: 'other' },
];
const mixedRows: RowItem[] = [{ node_ids: 1 }, { node_ids: 'n3' }];
const mixedSelected = buildSelectedNodeIdSet(mixedRows);
assert.deepEqual(
  idsOf(filterAvailableNodes(mixedNodes, mixedSelected, 1)),
  [1, '1'],
  '不得强制转换 ID 类型：数字 1 与字符串 1 应视为不同节点'
);
assert.deepEqual(
  idsOf(filterAvailableNodes(mixedNodes, mixedSelected, 1)),
  idsOf(filterByIncludes(mixedNodes, mixedRows, 1, { comparisons: 0 })),
  '不强制转换 ID 时 Set 与 includes 语义仍一致'
);

const originalOrder = filterAvailableNodes(nodeList, selectedNodeIds, 'n1');
assert.deepEqual(
  idsOf(originalOrder),
  ['n1', 'n3', 'n4'],
  '过滤后必须保持 nodeList 原顺序'
);

const includes20 = countIncludesForAllRows(20, 200);
const includes40 = countIncludesForAllRows(40, 200);
assert.ok(
  includes40 / includes20 > 3.5,
  `includes 路径比较次数应随 R 二次增长，实际 ${includes20} -> ${includes40}`
);

const set20 = countSetLookupsForAllRows(20, 200);
const set40 = countSetLookupsForAllRows(40, 200);
assert.ok(
  set40 / set20 < 2.5,
  `Set 路径成员查询应为 O(1)，总次数随 R 线性，实际 ${set20} -> ${set40}`
);
assert.equal(
  set20 / (20 * 200) < 1,
  true,
  '当前行短路后 Set.has 次数应少于每行全量扫描'
);

const workspaceRoot = process.cwd();
const commonColumns = fs.readFileSync(
  path.join(
    workspaceRoot,
    'src/app/log/hooks/integration/common/commonColumns.tsx'
  ),
  'utf8'
);

assert.equal(
  /nodeIds\.includes/.test(commonColumns),
  false,
  '源码不得再对已选数组做每行 includes 扫描'
);
assert.match(
  commonColumns,
  /buildSelectedNodeIdSet/,
  'getCommonColumns 应一次构建已选节点 Set'
);
assert.match(
  commonColumns,
  /filterAvailableNodes/,
  'getFilterNodes 应复用 Set 过滤'
);

console.log('日志批量接入节点 Set 过滤测试通过');
