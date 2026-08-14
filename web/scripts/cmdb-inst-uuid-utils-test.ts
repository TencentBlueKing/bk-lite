import assert from 'node:assert/strict';

import {
  isCmdbInstUuid,
  resolveCmdbInstUuid,
} from '../src/app/cmdb/utils/instUuid';

assert.equal(isCmdbInstUuid('550e8400-e29b-41d4-a716-446655440000'), true);
assert.equal(isCmdbInstUuid('550e8400-e29b-41d4-a716-446655440000'.toUpperCase()), true);
assert.equal(isCmdbInstUuid('12345'), false);
assert.equal(isCmdbInstUuid('undefined'), false);
assert.equal(isCmdbInstUuid(''), false);
assert.equal(isCmdbInstUuid(null), false);

assert.equal(
  resolveCmdbInstUuid(undefined, 12, '550e8400-e29b-41d4-a716-446655440000'),
  '550e8400-e29b-41d4-a716-446655440000',
);
assert.equal(resolveCmdbInstUuid(99, 'not-a-uuid'), null);

console.log('cmdb-inst-uuid-utils-test: ok');
