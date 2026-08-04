import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  getCleanupTimeoutMax,
  normalizeCleanupTimeout
} from '../src/app/monitor/(pages)/integration/object/cleanupTimeout';

assert.deepEqual(
  normalizeCleanupTimeout({
    cleanup_timeout_value: 30,
    cleanup_timeout_unit: 'minute'
  }),
  { value: 30, unit: 'minute' }
);

assert.deepEqual(normalizeCleanupTimeout({ cleanup_timeout_days: 7 }), {
  value: 7,
  unit: 'day'
});

assert.deepEqual(normalizeCleanupTimeout({}), { value: 1, unit: 'day' });
assert.equal(getCleanupTimeoutMax('minute'), 1440);
assert.equal(getCleanupTimeoutMax('hour'), 720);
assert.equal(getCleanupTimeoutMax('day'), 365);

assert.deepEqual(
  normalizeCleanupTimeout({
    cleanup_timeout_value: 12,
    cleanup_timeout_unit: 'hour'
  }),
  { value: 12, unit: 'hour' }
);

const objectPageSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/monitor/(pages)/integration/object/page.tsx'
  ),
  'utf8'
);
const displayAction = objectPageSource.match(
  /<Button[\s\S]*?displayFieldsModalRef\.current\?\.showModal[\s\S]*?<\/Button>/
)?.[0];
assert.ok(displayAction, '应能定位到监控对象展示列入口');
assert.doesNotMatch(
  displayAction,
  /disabled=\{isBuiltin\}/,
  '内置对象必须允许配置全局展示列'
);
assert.doesNotMatch(
  objectPageSource,
  /<Switch[\s\S]*?disabled=\{\(record as MonitorObjectItem\)\.is_builtin\}[\s\S]*?handleVisibilityChange/,
  '内置对象必须允许配置可见性'
);
assert.match(
  objectPageSource,
  /<Popconfirm[\s\S]*?handleDeleteObject\(record as MonitorObjectItem\)[\s\S]*?disabled=\{isBuiltin\}/,
  '内置对象删除入口必须保持禁用'
);

console.log('monitor cleanup timeout contract: OK');
