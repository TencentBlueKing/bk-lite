import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsRoot = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptsRoot, '..');
const packageJson = JSON.parse(
  fs.readFileSync(path.join(webRoot, 'package.json'), 'utf8')
);

assert.equal(packageJson.scripts.build, 'node scripts/build.mjs --turbopack');
assert.equal(
  packageJson.scripts.analyze,
  'node scripts/build.mjs --analyze --webpack'
);

const result = spawnSync(
  process.execPath,
  ['scripts/build.mjs', '--help'],
  {
    cwd: webRoot,
    encoding: 'utf8',
  }
);

assert.equal(
  result.status,
  0,
  `build entry should delegate to the local Next CLI:\n${result.stderr}`
);
assert.equal(
  result.stdout.match(/\[1\/2\] 正在准备构建资源/g)?.length,
  1,
  `build assets should start exactly once:\n${result.stdout}`
);
assert.equal(
  result.stdout.match(/Enterprise modules prepared successfully/g)?.length,
  1,
  `enterprise preparation should run exactly once:\n${result.stdout}`
);
assert.equal(
  result.stdout.match(/Locales combined successfully/g)?.length,
  1,
  `locale preparation should run exactly once:\n${result.stdout}`
);
assert.match(result.stdout, /Usage: next build/);

console.log('build entry prepares assets once before invoking Next');
