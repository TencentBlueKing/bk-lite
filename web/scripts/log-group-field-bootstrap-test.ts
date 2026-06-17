import assert from 'node:assert/strict';

import {
  COMMON_LOG_GROUP_FIELDS,
  discoverLogGroupRuleFields,
} from '../src/app/log/(pages)/integration/grouping/fieldBootstrap';

async function main() {
  const defaultCalls: Record<string, unknown>[] = [];
  const defaultResult = await discoverLogGroupRuleFields(
    async (params = {}) => {
      defaultCalls.push(params);
      return ['host.name'];
    },
    new Date('2026-06-16T08:00:00.000Z')
  );

  assert.deepEqual(defaultResult, {
    fields: ['host.name'],
    source: 'default',
  });
  assert.deepEqual(defaultCalls, [{ scope: 'log_group_create' }]);

  const fallbackCalls: Record<string, unknown>[] = [];
  const fallbackResult = await discoverLogGroupRuleFields(
    async (params = {}) => {
      fallbackCalls.push(params);
      return fallbackCalls.length === 1 ? [] : ['service.name'];
    },
    new Date('2026-06-16T08:00:00.000Z')
  );

  assert.deepEqual(fallbackResult, {
    fields: ['service.name'],
    source: 'expanded',
  });
  assert.equal(fallbackCalls.length, 2);
  assert.deepEqual(fallbackCalls[0], { scope: 'log_group_create' });
  assert.equal(fallbackCalls[1].scope, 'log_group_create');
  assert.equal(fallbackCalls[1].start_time, '2026-06-15T08:00:00.000Z');
  assert.equal(fallbackCalls[1].end_time, '2026-06-16T08:00:00.000Z');

  const emptyResult = await discoverLogGroupRuleFields(async () => []);
  assert.equal(emptyResult.source, 'fallback');
  assert.deepEqual(emptyResult.fields, COMMON_LOG_GROUP_FIELDS);

  const permissionResult = await discoverLogGroupRuleFields(async () => {
    throw { response: { status: 403 }, message: 'no permission' };
  });
  assert.equal(permissionResult.source, 'permission-blocked');
  assert.deepEqual(permissionResult.fields, COMMON_LOG_GROUP_FIELDS);

  console.log('log-group-field-bootstrap validation passed');
}

main();
