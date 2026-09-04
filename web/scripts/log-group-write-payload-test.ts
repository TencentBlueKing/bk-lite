import assert from 'node:assert/strict';

import { buildLogGroupSubmitPayload } from '../src/app/log/(pages)/integration/grouping/logGroupWritePayload';

const organizations = [1, 2];

const builtInPayload = buildLogGroupSubmitPayload({
  values: { organizations, name: 'Default' },
  term: null,
  conditions: [{ field: null, op: null, value: '' }],
  id: 'default',
  isBuiltIn: true
});

assert.deepEqual(builtInPayload, {
  organizations,
  name: 'Default',
  id: 'default',
  rule: {}
});

const customPayload = buildLogGroupSubmitPayload({
  values: { organizations, name: 'app' },
  term: 'AND',
  conditions: [{ field: 'cluster', op: '==', value: 'prod' }],
  id: 'g-1',
  isBuiltIn: false
});

assert.deepEqual(customPayload.rule, {
  mode: 'AND',
  conditions: [{ field: 'cluster', op: '==', value: 'prod' }]
});

const starPayload = buildLogGroupSubmitPayload({
  values: { organizations, name: 'custom-star' },
  term: null,
  conditions: [],
  id: 'g-star',
  isBuiltIn: false
});

assert.deepEqual(starPayload.rule, {});

console.log('log-group-write-payload validation passed');
