import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsRoot = path.dirname(fileURLToPath(import.meta.url));
const dockerfile = fs.readFileSync(path.resolve(scriptsRoot, '..', 'Dockerfile'), 'utf8');

assert.doesNotMatch(
  dockerfile,
  /RUN\s+--mount=/,
  'web Dockerfile must remain compatible with the legacy Docker builder'
);
assert.match(dockerfile, /^RUN pnpm install --frozen-lockfile$/m);
assert.match(dockerfile, /^RUN pnpm run build$/m);
assert.match(
  dockerfile,
  /pnpm config set registry "\$NEXUS_NODEJS_REPOSITY";\s*\\\n\s*pnpm config set trust-lockfile true;/,
  'Nexus builds must trust the committed lockfile so tarball host differences do not fail frozen install'
);

const lockfile = fs.readFileSync(path.resolve(scriptsRoot, '..', 'pnpm-lock.yaml'), 'utf8');
assert.doesNotMatch(
  lockfile,
  /tarball:\s+https:\/\/registry\.npmmirror\.com\//,
  'web lockfile must not pin npmmirror tarball hosts; CI installs from Nexus'
);

console.log('web Dockerfile supports the legacy Docker builder');
