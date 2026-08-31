import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  APP_TOPO_DEFAULT_EXPAND_DEPTH,
  APP_TOPO_EXPAND_DEPTH_OPTIONS,
  APP_TOPO_EXPAND_DEPTH_STORAGE_KEY,
  parseAppTopoExpandDepth,
  readAppTopoExpandDepth,
  writeAppTopoExpandDepth,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/expandDepth';

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel: string) => fs.readFileSync(path.join(webRoot, rel), 'utf8');

assert.deepEqual([...APP_TOPO_EXPAND_DEPTH_OPTIONS], [1, 2, 3, 4, 5]);
assert.equal(APP_TOPO_DEFAULT_EXPAND_DEPTH, 3);
assert.equal(parseAppTopoExpandDepth(1), 1);
assert.equal(parseAppTopoExpandDepth('5'), 5);
assert.equal(parseAppTopoExpandDepth(3), 3);
assert.equal(parseAppTopoExpandDepth(0), 3);
assert.equal(parseAppTopoExpandDepth(6), 3);
assert.equal(parseAppTopoExpandDepth('nope'), 3);
assert.equal(parseAppTopoExpandDepth(null), 3);

const store: Record<string, string> = {};
const storage = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => {
    store[key] = value;
  },
};

assert.equal(readAppTopoExpandDepth(storage), 3);
assert.equal(writeAppTopoExpandDepth(storage, 5), true);
assert.equal(store[APP_TOPO_EXPAND_DEPTH_STORAGE_KEY], '5');
assert.equal(readAppTopoExpandDepth(storage), 5);
store[APP_TOPO_EXPAND_DEPTH_STORAGE_KEY] = '9';
assert.equal(readAppTopoExpandDepth(storage), 3);
assert.equal(readAppTopoExpandDepth(null), 3);

const overviewSrc = read(
  'src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/index.tsx'
);
assert.match(overviewSrc, /ExpandDepthControl/);
assert.match(overviewSrc, /readAppTopoExpandDepth/);
assert.match(overviewSrc, /writeAppTopoExpandDepth/);
assert.match(overviewSrc, /getApplicationResourceTopology\([\s\S]*expandDepth/);
assert.doesNotMatch(
  overviewSrc,
  /initialDepth = modelId === 'system' \? 2 : 1/
);

const controlSrc = read(
  'src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/ExpandDepthControl.tsx'
);
assert.match(controlSrc, /Segmented/);
assert.match(controlSrc, /APP_TOPO_EXPAND_DEPTH_OPTIONS/);
assert.match(controlSrc, /ApplicationResourceOverview\.expandDepthLabel/);

const zh = JSON.parse(read('src/app/cmdb/locales/zh.json'));
const en = JSON.parse(read('src/app/cmdb/locales/en.json'));
assert.equal(zh.ApplicationResourceOverview.expandDepthLabel, '展开层级');
assert.equal(en.ApplicationResourceOverview.expandDepthLabel, 'Expand depth');

console.log('cmdb-app-topo-expand-depth-test passed');
