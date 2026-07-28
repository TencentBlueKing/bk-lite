import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { normalizeTestConnectionResponse } from '../src/app/system-manager/api/integration-center';

const requestSource = fs.readFileSync(path.resolve(import.meta.dirname, '../src/utils/request.ts'), 'utf8');
const integrationCenterApiSource = fs.readFileSync(
  path.resolve(import.meta.dirname, '../src/app/system-manager/api/integration-center/index.ts'),
  'utf8',
);

assert.doesNotMatch(requestSource, /postRaw/);
assert.match(integrationCenterApiSource, /const \{ get, post, put, del \} = useApiClient\(\);/);
assert.match(integrationCenterApiSource, /const response = await post\(/);

const runtimeFailure = {
  success: false,
  summary: 'AD connection credentials were rejected',
  request_id: 'req-1',
  partial_success: false,
  retryable: false,
  payload: {
    provider_key: 'ad',
    instance_status: 'verification_failed',
    capability_status: {},
    capability_results: {},
  },
  errors: [],
};

assert.deepEqual(
  normalizeTestConnectionResponse({ result: false, data: runtimeFailure }),
  { result: false, data: runtimeFailure },
);
assert.deepEqual(
  normalizeTestConnectionResponse({ result: true, data: runtimeFailure }),
  { result: false, data: runtimeFailure },
);
assert.deepEqual(
  normalizeTestConnectionResponse({ result: true, data: { result: false, data: runtimeFailure } }),
  { result: false, data: runtimeFailure },
);
assert.deepEqual(
  normalizeTestConnectionResponse({ message: 'success', data: { result: true, data: { result: false, data: runtimeFailure } } }),
  { result: false, data: runtimeFailure },
);
assert.deepEqual(normalizeTestConnectionResponse(runtimeFailure), { result: false, data: runtimeFailure });

console.log('integration center test connection response tests passed');
