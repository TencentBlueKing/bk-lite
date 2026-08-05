import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { parseActiveApps, updateWorkspacePackages } = require('./generate-workspace.js');

const original = `packages:
  - 'src/app/*'

verifyDepsBeforeRun: false

overrides:
  '@types/react': 19.2.18

allowBuilds:
  sharp: true
`;

const selected = updateWorkspacePackages(original, parseActiveApps('cmdb, monitor,cmdb'));
assert.match(selected, /packages:\n  - 'src\/app\/cmdb'\n  - 'src\/app\/monitor'/);
assert.match(selected, /verifyDepsBeforeRun: false/);
assert.match(selected, /overrides:\n  '@types\/react': 19\.2\.18/);
assert.match(selected, /allowBuilds:\n  sharp: true/);

const restored = updateWorkspacePackages(selected, parseActiveApps(''));
assert.match(restored, /packages:\n  - 'src\/app\/\*'/);
assert.match(restored, /verifyDepsBeforeRun: false/);
assert.match(restored, /overrides:\n  '@types\/react': 19\.2\.18/);

assert.deepEqual(parseActiveApps('(cmdb),monitor'), ['cmdb', 'monitor']);
assert.throws(() => parseActiveApps('../cmdb'), /无效的应用名称/);

console.log('generate-workspace checks passed');
