import assert from 'node:assert/strict';
import { buildLogAlertRawColumns } from '../src/app/log/(pages)/event/alert/rawLogColumns';

assert.deepEqual(
  buildLogAlertRawColumns({
    isAggregate: false,
    showFields: ['timestamp', 'message', 'host.name']
  }).map((item) => item.dataIndex),
  ['_time', '_msg', 'host.name']
);

assert.deepEqual(
  buildLogAlertRawColumns({
    isAggregate: false,
    showFields: ['_time', '_msg', 'timestamp', 'message']
  }).map((item) => item.dataIndex),
  ['_time', '_msg']
);

assert.deepEqual(
  buildLogAlertRawColumns({
    isAggregate: true,
    rawData: [{ id: 0, total_count: 12, service: 'api' }]
  }).map((item) => item.dataIndex),
  ['total_count', 'service']
);

console.log('log-alert-raw-columns validation passed');
