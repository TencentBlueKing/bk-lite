import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  buildFirstLevelIndex,
  lookupFirstLevel,
  resolveTopoEdgeEndpoints,
  type LevelNodes,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/topoLevelIndex.ts';

const webRoot = process.cwd();
const topoDataPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/assetData/detail/relationships/topoData.tsx'
);
const pagePath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/assetData/detail/relationships/page.tsx'
);
const menuPath = path.join(webRoot, 'src/app/cmdb/constants/menu.json');
const localePath = path.join(webRoot, 'src/app/cmdb/locales/zh.json');

const topoDataSource = fs.readFileSync(topoDataPath, 'utf8');
const pageSource = fs.readFileSync(pagePath, 'utf8');
const menuSource = fs.readFileSync(menuPath, 'utf8');
const localeSource = fs.readFileSync(localePath, 'utf8');

assert.match(menuSource, /"title": "资产"/);
assert.match(menuSource, /"title": "关联关系"/);
assert.match(localeSource, /"topo": "拓扑"/);
assert.match(pageSource, /t\('topo'\)/);
assert.match(pageSource, /activeTab === 'topo'/);

const createNodesAndEdgesMatch = topoDataSource.match(
  /const createNodesAndEdges = \([\s\S]*?\n  \};/
);
assert.ok(createNodesAndEdgesMatch, 'createNodesAndEdges must exist');
const createNodesAndEdgesSource = createNodesAndEdgesMatch[0];

assert.doesNotMatch(
  createNodesAndEdgesSource,
  /Object\.keys\(levelNodes\)\.find/,
  'createNodesAndEdges must not scan levelNodes with Object.keys().find for each id'
);
assert.doesNotMatch(
  createNodesAndEdgesSource,
  /levelNodes\[.*\]\?\.some\(\(n\) => n\.id === id\)/,
  'createNodesAndEdges must not scan a level array with some() for each id'
);
assert.match(
  topoDataSource,
  /from ['"]\.\/topoLevelIndex['"]/,
  'topoData must import the extracted level index'
);
assert.match(
  createNodesAndEdgesSource,
  /lookupFirstLevel\(|levelIndex\.get\(/,
  'createNodesAndEdges must query the Map instead of scanning levelNodes'
);

const emptyIndex = buildFirstLevelIndex({});
assert.equal(emptyIndex.size, 0);
assert.equal(lookupFirstLevel(emptyIndex, 'missing'), undefined);

const emptyStats = { comparisons: 0 };
assert.equal(lookupFirstLevel(emptyIndex, 'root', emptyStats), undefined);
assert.equal(emptyStats.comparisons, 1);

const duplicateLevelNodes: LevelNodes = {
  1: [{ id: 'root', parentId: null }],
  3: [{ id: 'dup', parentId: 'other' }],
  2: [
    { id: 'dup', parentId: 'root' },
    { id: 'leaf', parentId: 'dup' },
  ],
};
const duplicateIndex = buildFirstLevelIndex(duplicateLevelNodes);
assert.equal(duplicateIndex.get('root'), 1);
assert.equal(duplicateIndex.get('dup'), 2);
assert.equal(duplicateIndex.get('leaf'), 2);
assert.equal(lookupFirstLevel(duplicateIndex, 'dup'), 2);

assert.deepEqual(resolveTopoEdgeEndpoints('src', 'child', 'parent'), {
  source: 'parent',
  target: 'child',
});
assert.deepEqual(resolveTopoEdgeEndpoints('dst', 'child', 'parent'), {
  source: 'child',
  target: 'parent',
});
assert.match(
  createNodesAndEdgesSource,
  /resolveTopoEdgeEndpoints\(|type === ["']src["'] \? parentId : id/,
  'src/dst edge direction must stay parent→child for src and child→parent for dst'
);

const assertLinearLookups = (size: number) => {
  const levelNodes: LevelNodes = {
    1: [{ id: 'root', parentId: null }],
    2: Array.from({ length: size }, (_, index) => ({
      id: `n${index}`,
      parentId: 'root',
    })),
  };
  const index = buildFirstLevelIndex(levelNodes);
  const stats = { comparisons: 0 };
  assert.equal(lookupFirstLevel(index, 'root', stats), 1);
  for (let i = 0; i < size; i += 1) {
    assert.equal(lookupFirstLevel(index, `n${i}`, stats), 2);
  }
  const lookupCount = size + 1;
  assert.equal(
    stats.comparisons,
    lookupCount,
    `${size} same-layer lookups must stay linear (1 Map get per id), got ${stats.comparisons}`
  );
  assert.ok(
    stats.comparisons <= lookupCount,
    `${size} same-layer lookups must not rescan the layer array`
  );
};

assertLinearLookups(100);
assertLinearLookups(1000);

console.log('cmdb topo level index behavior OK');
console.log('页面入口：菜单「资产」→「关联关系」；页签「拓扑」');
