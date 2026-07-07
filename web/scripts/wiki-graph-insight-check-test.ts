import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const checkTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/CheckTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.ok(zh.wiki.checkBridgeNode, 'missing zh wiki.checkBridgeNode');
assert.ok(en.wiki.checkBridgeNode, 'missing en wiki.checkBridgeNode');
assert.ok(zh.wiki.checkSparseCommunity, 'missing zh wiki.checkSparseCommunity');
assert.ok(en.wiki.checkSparseCommunity, 'missing en wiki.checkSparseCommunity');
assert.ok(zh.wiki.checkCrossCommunityEdge, 'missing zh wiki.checkCrossCommunityEdge');
assert.ok(en.wiki.checkCrossCommunityEdge, 'missing en wiki.checkCrossCommunityEdge');
assert.match(checkTab, /bridge_node:\s*'wiki\.checkBridgeNode'/);
assert.match(checkTab, /sparse_community:\s*'wiki\.checkSparseCommunity'/);
assert.match(checkTab, /cross_community_edge:\s*'wiki\.checkCrossCommunityEdge'/);

console.log('wiki graph insight check validation passed');
