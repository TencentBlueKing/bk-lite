import * as assert from 'node:assert/strict';

import { allStates } from '../src/app/alarm/constants/alarm';

assert.deepEqual(
  allStates,
  [
    'pending',
    'processing',
    'unassigned',
    'closed',
    'resolved',
    'auto_recovery',
    'auto_close',
  ],
  '历史告警的全部状态必须包含人工解决和自动恢复状态'
);

assert.ok(
  !(allStates as readonly string[]).includes('recovered'),
  'Alert.status 不支持 recovered，前端不得发送该状态'
);

console.log('alarm history status filter test passed');
