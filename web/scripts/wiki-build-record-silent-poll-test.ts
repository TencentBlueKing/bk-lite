import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const buildRecordTab = fs.readFileSync(
  path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'),
  'utf8',
);

assert.match(buildRecordTab, /options\?: \{ silent\?: boolean \}/);
assert.match(buildRecordTab, /await load\(\{ silent: true \}\)/);
assert.match(buildRecordTab, /if \(!silent\) \{\s*setLoading\(true\);/s);
assert.match(buildRecordTab, /if \(!silent\) \{\s*setLoading\(false\);/s);
assert.doesNotMatch(
  buildRecordTab,
  /setInterval\(\(\) => load\(\), 3000\)/,
  'BuildRecordTab polling must not toggle table loading every tick',
);

console.log('wiki build record silent poll validation passed');
