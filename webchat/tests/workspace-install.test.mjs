import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const packageJson = JSON.parse(fs.readFileSync(path.join(rootDir, 'package.json'), 'utf8'));
const corePackage = JSON.parse(
  fs.readFileSync(path.join(rootDir, 'packages/webchat-core/package.json'), 'utf8')
);
const uiPackage = JSON.parse(fs.readFileSync(path.join(rootDir, 'packages/webchat-ui/package.json'), 'utf8'));
const demoPackage = JSON.parse(
  fs.readFileSync(path.join(rootDir, 'packages/webchat-demo/package.json'), 'utf8')
);
const workflow = fs.readFileSync(
  path.resolve(rootDir, '../.github/workflows/webchat-tests.yml'),
  'utf8'
);

test('root package owns the complete WebChat workspace install graph', () => {
  assert.deepEqual(packageJson.workspaces, [
    'packages/webchat-core',
    'packages/webchat-ui',
    'packages/webchat-demo',
  ]);
  assert.equal(packageJson.scripts['build:core'], 'npm run build --workspace @webchat/core');
  assert.equal(packageJson.scripts['build:ui'], 'npm run build --workspace @webchat/ui');
  assert.equal(packageJson.scripts['build:browser'], 'npm run build:browser --workspace @webchat/ui');
  assert.equal(packageJson.scripts['build:demo'], 'npm run build --workspace @webchat/demo');
  assert.equal(packageJson.engines.node, '>=18.18.0');
  assert.equal(uiPackage.dependencies['@webchat/core'], corePackage.version);
  assert.equal(demoPackage.dependencies['@webchat/ui'], uiPackage.version);
  assert.doesNotMatch(JSON.stringify(uiPackage.dependencies), /file:/);
  assert.doesNotMatch(JSON.stringify(demoPackage.dependencies), /file:/);
});

test('reachable CI uses the root lockfile instead of installing child packages independently', () => {
  assert.match(workflow, /working-directory: webchat/);
  assert.match(workflow, /run: npm ci\n/);
  assert.doesNotMatch(workflow, /npm ci --prefix/);
  assert.match(workflow, /node-version: \['18\.18\.0', '20'\]/);
});

test('packed core package supports both ESM import and CommonJS require', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-core-consumer-'));
  const cache = path.join(fixture, 'npm-cache');
  const pack = spawnSync(
    'npm',
    ['pack', '--workspace', '@webchat/core', '--pack-destination', fixture, '--json'],
    { cwd: rootDir, encoding: 'utf8', env: { ...process.env, npm_config_cache: cache } }
  );
  assert.equal(pack.status, 0, pack.stderr);
  const [{ filename }] = JSON.parse(pack.stdout);
  const packageDir = path.join(fixture, 'consumer/node_modules/@webchat/core');
  fs.mkdirSync(packageDir, { recursive: true });
  const extract = spawnSync(
    'tar',
    ['-xzf', path.join(fixture, filename), '--strip-components=1', '-C', packageDir],
    { encoding: 'utf8' }
  );
  assert.equal(extract.status, 0, extract.stderr);

  const consumerDir = path.join(fixture, 'consumer');
  const esm = spawnSync(
    process.execPath,
    ['--input-type=module', '--eval', "import { SSEStreamParser } from '@webchat/core'; console.log(typeof SSEStreamParser)"],
    { cwd: consumerDir, encoding: 'utf8' }
  );
  assert.equal(esm.status, 0, esm.stderr);
  assert.equal(esm.stdout.trim(), 'function');

  const cjs = spawnSync(
    process.execPath,
    ['--eval', "const { SSEStreamParser } = require('@webchat/core'); console.log(typeof SSEStreamParser)"],
    { cwd: consumerDir, encoding: 'utf8' }
  );
  assert.equal(cjs.status, 0, cjs.stderr);
  assert.equal(cjs.stdout.trim(), 'function');
});
