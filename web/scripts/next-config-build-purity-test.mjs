import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsRoot = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptsRoot, '..');
const repositoryRoot = path.resolve(webRoot, '..');

const result = spawnSync(
  process.execPath,
  [
    '--permission',
    `--allow-fs-read=${repositoryRoot}`,
    '--input-type=module',
    '--eval',
    "await import('./next.config.mjs')",
  ],
  {
    cwd: webRoot,
    encoding: 'utf8',
    env: {
      ...process.env,
      NODE_ENV: 'production',
    },
  }
);

assert.equal(
  result.status,
  0,
  `next.config.mjs should load successfully:\n${result.stderr}`
);
assert.doesNotMatch(
  result.stdout,
  /Preparing build assets|Enterprise modules prepared|Locales combined|Menus combined|Copied contents of/,
  `loading next.config.mjs must not prepare or copy build assets:\n${result.stdout}`
);

console.log('next config production import is side-effect free');
