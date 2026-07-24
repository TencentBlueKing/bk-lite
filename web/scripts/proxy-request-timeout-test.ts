import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  DEFAULT_TIMEOUT_MS,
  getInitialProxyTimeoutMs,
  SSE_TIMEOUT_MS,
} from '../src/app/(core)/api/proxy/[...path]/timeout.ts';

assert.equal(getInitialProxyTimeoutMs(null), DEFAULT_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('*/*'), DEFAULT_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('application/json'), DEFAULT_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('text/event-stream'), SSE_TIMEOUT_MS);
assert.equal(
  getInitialProxyTimeoutMs('application/json, Text/Event-Stream; q=0.9'),
  SSE_TIMEOUT_MS
);

const routeSource = readFileSync(
  new URL('../src/app/(core)/api/proxy/[...path]/route.ts', import.meta.url),
  'utf8'
);
assert.match(
  routeSource,
  /getInitialProxyTimeoutMs\(req\.headers\.get\('accept'\)\)/,
  'the proxy must select its timeout before fetch from the request Accept header'
);

function readSource(file: string): string {
  return readFileSync(new URL(file, import.meta.url), 'utf8');
}

function sourceSection(source: string, start: string, end: string): string {
  const startIndex = source.indexOf(start);
  const endIndex = source.indexOf(end, startIndex);
  assert.notEqual(startIndex, -1, `missing section start: ${start}`);
  assert.notEqual(endIndex, -1, `missing section end: ${end}`);
  return source.slice(startIndex, endIndex);
}

const sseRequestSections = [
  sourceSection(
    readSource('../src/app/job/hooks/useExecutionStream.ts'),
    'const response = await fetch(',
    'if (!response.ok'
  ),
  sourceSection(
    readSource('../src/app/log/(pages)/search/logTerminal/index.tsx'),
    'const response = await fetch(',
    'fetchData?.(false)'
  ),
  sourceSection(
    readSource('../src/app/opspilot/components/custom-chat-sse/hooks/useSSEStream.ts'),
    'const handleSSEStream = useCallback(',
    'if (!response.ok'
  ),
  sourceSection(
    readSource('../src/app/opspilot/components/chatflow/hooks/useNodeExecution.ts'),
    'const handleSSEExecution = useCallback(',
    "const executionId = response.headers.get('X-Execution-ID')"
  ),
];

for (const section of sseRequestSections) {
  assert.match(section, /Accept: 'text\/event-stream'/, 'each SSE fetch must identify its request');
}

const nodeExecutionSource = readSource(
  '../src/app/opspilot/components/chatflow/hooks/useNodeExecution.ts'
);
const interruptRequestSection = sourceSection(
  nodeExecutionSource,
  'const interruptExecution = useCallback(',
  'useEffect(() => {'
);
assert.doesNotMatch(
  interruptRequestSection,
  /Accept: 'text\/event-stream'/,
  'the non-streaming interrupt request must keep the default timeout'
);

console.log('proxy request timeout tests passed');
