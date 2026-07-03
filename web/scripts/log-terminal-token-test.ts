import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const source = readFileSync(
  path.join(
    process.cwd(),
    'src/app/log/(pages)/search/logTerminal/index.tsx'
  ),
  'utf8'
);

assert(
  !source.includes('const tokenRef = useRef(token)'),
  'LogTerminal must not keep the initial auth token in a ref'
);

assert(
  source.includes('if (!token) return;'),
  'LogTerminal should wait for an available auth token before opening the tail stream'
);

assert(
  source.includes('Authorization: `Bearer ${token}`'),
  'LogTerminal tail requests should use the current auth token'
);

assert.match(
  source,
  /\}, \[query, stopLogStream, t, fetchData, token\]\);/,
  'startLogStream dependencies should include token so auth context updates refresh the callback'
);

assert.match(
  source,
  /\}, \[stopLogStream, isLoading, token\]\);/,
  'the auto-start effect should rerun when auth token becomes available without depending on unstable render-time callbacks'
);

console.log('log terminal token validation passed');
