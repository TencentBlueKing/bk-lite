import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const graphTab = read('src/app/opspilot/components/wiki/GraphTab.tsx');
const graphExplorer = read('src/app/opspilot/components/wiki/GraphExplorer.tsx');
const wikiTypes = read('src/app/opspilot/types/wiki.ts');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(wikiTypes, /export interface WikiGraphBridgeNode/);
assert.match(wikiTypes, /export interface WikiGraphSparseCommunity/);
assert.match(wikiTypes, /export interface WikiGraphCrossCommunityEdge/);

assert.match(graphTab, /fetchGraphAnalysis,\s*rebuildRelations,\s*scan/);
assert.match(graphTab, /handleCreateInsightChecks/);
assert.match(graphTab, /await scan\(kbId\)/);
assert.match(graphTab, /onCreateInsightChecks=\{handleCreateInsightChecks\}/);

assert.match(graphExplorer, /onCreateInsightChecks\?: \(\) => void/);
assert.match(graphExplorer, /creatingInsightChecks\?: boolean/);
assert.match(graphExplorer, /bridge_nodes as WikiGraphBridgeNode\[\]/);
assert.match(graphExplorer, /sparse_communities as WikiGraphSparseCommunity\[\]/);
assert.match(graphExplorer, /cross_community_edges as WikiGraphCrossCommunityEdge\[\]/);
assert.match(graphExplorer, /wiki\.bridgeNodes/);
assert.match(graphExplorer, /wiki\.sparseCommunities/);
assert.match(graphExplorer, /wiki\.crossCommunityEdges/);
assert.match(graphExplorer, /wiki\.createInsightChecks/);
assert.match(graphExplorer, /wiki\.rebuildRelations/);

for (const key of [
  'bridgeNodes',
  'sparseCommunities',
  'crossCommunityEdges',
  'createInsightChecks',
  'createInsightChecksDone',
  'rebuildRelations',
  'graphInsightChecks',
  'density',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki graph actionable insights validation passed');
