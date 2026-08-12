import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { syncWebPublic } from '../scripts/sync-web-public.mjs';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const workflowPath = path.resolve(rootDir, '../.github/workflows/webchat-tests.yml');

test('check mode verifies committed browser assets without rewriting them', () => {
  const result = spawnSync(process.execPath, ['scripts/sync-web-public.mjs', '--check'], {
    cwd: rootDir,
    encoding: 'utf8',
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /verified web\/public\/webchat\/webchat\.js/);
  assert.match(result.stdout, /verified web\/public\/webchat\/style\.css/);
  assert.doesNotMatch(result.stdout, / -> /);
});

test('check mode fails closed on a stale public asset and does not overwrite it', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-public-check-'));
  const source = path.join(fixture, 'source');
  const target = path.join(fixture, 'target');
  fs.mkdirSync(source);
  fs.mkdirSync(target);

  for (const file of ['webchat.js', 'style.css']) {
    fs.writeFileSync(path.join(source, file), `current ${file}`);
    fs.writeFileSync(path.join(target, file), file === 'webchat.js' ? 'stale bundle' : `current ${file}`);
  }

  assert.throws(() => syncWebPublic({ check: true, source, target }), /stale public asset/);
  assert.equal(fs.readFileSync(path.join(target, 'webchat.js'), 'utf8'), 'stale bundle');
});

test('reachable CI rejects generated browser assets that were not committed', () => {
  const workflow = fs.readFileSync(workflowPath, 'utf8');

  assert.match(workflow, /working-directory: webchat/);
  assert.match(workflow, /npm run build:core && npm run build:ui && npm run build:browser/);
  assert.match(workflow, /npm run check:web-public/);
  assert.match(workflow, /git diff --exit-code --/);
  assert.match(workflow, /packages\/webchat-ui\/dist\/browser\/webchat\.js/);
  assert.match(workflow, /\.\.\/web\/public\/webchat\/webchat\.js/);
});
