import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  consumeProxyTimeoutMs,
  DEFAULT_TIMEOUT_MS,
  getInitialProxyTimeoutMs,
  getProxyTimeoutHeaderValue,
  PROXY_TIMEOUT_HEADER,
  scheduleProxyAbort,
  SSE_TIMEOUT_MS,
} from '../src/utils/proxyTimeout.ts';
import {
  buildTimeseriesPredictRequest,
  TIMESERIES_PREDICT_REQUEST_TIMEOUT_MS,
} from '../src/app/mlops/api/timeseriesPredictRequest.ts';

assert.equal(getInitialProxyTimeoutMs(null), DEFAULT_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('*/*'), DEFAULT_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('application/json'), DEFAULT_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('text/event-stream'), SSE_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('text/event-stream; q=0'), DEFAULT_TIMEOUT_MS);
assert.equal(
  getInitialProxyTimeoutMs('application/json, Text/Event-Stream; q=0.9'),
  SSE_TIMEOUT_MS
);
assert.equal(getInitialProxyTimeoutMs('application/json', '120000'), 120_000);
assert.equal(getInitialProxyTimeoutMs('application/json', '600000'), SSE_TIMEOUT_MS);
assert.equal(getInitialProxyTimeoutMs('application/json', 'invalid'), DEFAULT_TIMEOUT_MS);

assert.equal(getProxyTimeoutHeaderValue(undefined), null);
assert.equal(getProxyTimeoutHeaderValue(DEFAULT_TIMEOUT_MS), null);
assert.equal(getProxyTimeoutHeaderValue(120_000), '120000');
assert.equal(getProxyTimeoutHeaderValue(0), String(SSE_TIMEOUT_MS));
assert.equal(getProxyTimeoutHeaderValue(600_000), String(SSE_TIMEOUT_MS));

const ordinaryHeaders = new Headers({
  Accept: 'application/json',
  [PROXY_TIMEOUT_HEADER]: '120000',
});
assert.equal(consumeProxyTimeoutMs(ordinaryHeaders), 120_000);
assert.equal(ordinaryHeaders.has(PROXY_TIMEOUT_HEADER), false);

const sseHeaders = new Headers({
  Accept: 'text/event-stream',
  [PROXY_TIMEOUT_HEADER]: '120000',
});
assert.equal(consumeProxyTimeoutMs(sseHeaders), SSE_TIMEOUT_MS);
assert.equal(sseHeaders.has(PROXY_TIMEOUT_HEADER), false);

const abortController = new AbortController();
scheduleProxyAbort(abortController, 1);

const routeSource = readFileSync(
  new URL('../src/app/(core)/api/proxy/[...path]/route.ts', import.meta.url),
  'utf8'
);
assert.match(
  routeSource,
  /consumeProxyTimeoutMs\(headers\)/,
  'the proxy must consume its timeout contract before fetch'
);

const requestSource = readFileSync(
  new URL('../src/utils/request.ts', import.meta.url),
  'utf8'
);
assert.match(requestSource, /timeout: 60000/, 'ordinary API requests must use the 60 second default');
assert.match(
  requestSource,
  /getProxyTimeoutHeaderValue\(config\.timeout\)/,
  'explicit client timeouts must be mapped to the proxy compatibility header'
);

const timeseriesPayload = { data: [], config: { steps: 1000 } };
const timeseriesRequest = buildTimeseriesPredictRequest(42, timeseriesPayload);
assert.equal(
  timeseriesRequest.url,
  '/mlops/timeseries_predict_servings/42/predict/'
);
assert.equal(timeseriesRequest.data, timeseriesPayload);
assert.equal(
  timeseriesRequest.config.timeout,
  TIMESERIES_PREDICT_REQUEST_TIMEOUT_MS
);
assert.equal(
  getProxyTimeoutHeaderValue(timeseriesRequest.config.timeout),
  String(TIMESERIES_PREDICT_REQUEST_TIMEOUT_MS),
  'timeseries prediction must forward its Axios timeout into the proxy contract'
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
  )
];

for (const section of sseRequestSections) {
  assert.match(section, /Accept: 'text\/event-stream'/, 'each SSE fetch must identify its request');
}

const nodeExecutionSource = readSource(
  '../src/app/opspilot/components/chatflow/hooks/useNodeExecution.ts'
);
const testExecutionRequestSection = sourceSection(
  nodeExecutionSource,
  'const handleSSEExecution = useCallback(',
  "const executionId = response.headers.get('X-Execution-ID')"
);
assert.doesNotMatch(
  testExecutionRequestSection,
  /Accept: 'text\/event-stream'/,
  'the asynchronous test request returns JSON and must keep the default timeout'
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

setTimeout(() => {
  assert.equal(abortController.signal.aborted, true);
  console.log('proxy request timeout tests passed');
}, 10);
