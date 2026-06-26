import assert from 'node:assert/strict';

import { buildAlertSnapshotChartValues } from '../src/app/monitor/(pages)/event/alert/alertDetailUtils';

const thresholdSnapshots = [
  {
    type: 'pre_alert',
    raw_data: {
      values: [
        [100, '71'],
      ],
    },
  },
  {
    type: 'event',
    raw_data: {
      values: [
        [200, '82'],
        [260, '91'],
      ],
    },
  },
  {
    type: 'event',
    raw_data: {
      values: [
        [260, '91'],
        [320, '95'],
      ],
    },
  },
];

assert.deepEqual(buildAlertSnapshotChartValues(thresholdSnapshots), [
  [100, '71'],
  [200, '82'],
  [260, '91'],
  [320, '95'],
]);

const noDataSnapshots = [
  {
    type: 'no_data',
    event_time: '1970-01-01T00:05:00Z',
    raw_data: {},
  },
  {
    type: 'event',
    raw_data: {
      values: [
        [400, '1'],
        [460, '2'],
      ],
    },
  },
];

assert.deepEqual(buildAlertSnapshotChartValues(noDataSnapshots), [
  [400, '1'],
  [460, '2'],
]);

console.log('monitor-alert-detail snapshot validation passed');
