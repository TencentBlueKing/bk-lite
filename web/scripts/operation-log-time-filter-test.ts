import assert from 'node:assert/strict';
import {
  buildOperationLogParams,
} from '../src/app/system-manager/utils/operationLogParams';

function run(name: string, fn: () => void) {
  fn();
  console.log(`  ✓ ${name}`);
}

// fixed epoch ms so the test is deterministic
const T0 = 1_700_000_000_000;
const T1 = 1_700_086_400_000;

run('time range -> backend contract param names', () => {
  const params = buildOperationLogParams({}, [T0, T1], 1, 20);
  assert.ok(
    'operation_time_start' in params,
    'must send operation_time_start (backend OperationLogFilter contract)'
  );
  assert.ok(
    'operation_time_end' in params,
    'must send operation_time_end (backend OperationLogFilter contract)'
  );
  assert.ok(
    !('start_time' in params),
    'must NOT send legacy start_time (backend silently ignores it)'
  );
  assert.ok(
    !('end_time' in params),
    'must NOT send legacy end_time (backend silently ignores it)'
  );
});

run('time values formatted YYYY-MM-DD HH:mm:ss', () => {
  const params = buildOperationLogParams({}, [T0, T1], 1, 20);
  assert.match(params.operation_time_start, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  assert.match(params.operation_time_end, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
});

run('no time range -> no time params', () => {
  const params = buildOperationLogParams({}, [], 1, 20);
  assert.ok(!('operation_time_start' in params));
  assert.ok(!('operation_time_end' in params));
});

run('other filters pass through unchanged', () => {
  const params = buildOperationLogParams(
    { username: 'admin', app: 'cmdb', actionType: 'create' },
    [],
    2,
    50
  );
  assert.equal(params.username, 'admin');
  assert.equal(params.app, 'cmdb');
  assert.equal(params.action_type, 'create');
  assert.equal(params.page, 2);
  assert.equal(params.page_size, 50);
});

console.log('All operation-log time-filter tests passed.');
