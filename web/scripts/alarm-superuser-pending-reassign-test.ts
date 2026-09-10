import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const alarmDir = resolve(here, '../src/app/alarm');

const pageAction = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/alarmAction.tsx'),
  'utf8'
);
const sharedAction = readFileSync(
  resolve(alarmDir, 'components/alarm-action/index.tsx'),
  'utf8'
);

assert.match(
  pageAction,
  /canReassignAlert/,
  'list/detail alarm actions must use the shared reassign access helper'
);
assert.match(
  sharedAction,
  /canReassignAlert/,
  'shared alarm-action must use the shared reassign access helper'
);
assert.match(
  pageAction,
  /isSuperUser/,
  'list/detail alarm actions must read platform superuser state'
);
assert.match(
  sharedAction,
  /isSuperUser/,
  'shared alarm-action must accept platform superuser state'
);

console.log('alarm superuser pending reassign ui test passed');
