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

console.log('web Dockerfile supports the legacy Docker builder');
