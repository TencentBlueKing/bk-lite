import assert from 'node:assert/strict';

import {
  buildAlertDetailMetricQuery,
  buildAlertSnapshotChartValues,
  resolveAlertDetailChartUnit,
  resolveAlertDetailMetric
} from '../src/app/monitor/(pages)/event/alert/alertDetailUtils';

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

const formulaMetric = resolveAlertDetailMetric(
  {
    policy: {
      calculation_unit: 'bytes',
      query_condition: {
        type: 'formula',
        result_name: '测试计算指标',
      },
    },
  },
  {}
);

assert.equal(formulaMetric.display_name, '测试计算指标');
assert.equal(formulaMetric.unit, 'bytes');

assert.equal(
  resolveAlertDetailChartUnit(
    {
      policy: {
        threshold_unit: 'kibibytes',
        calculation_unit: 'bytes'
      }
    },
    ''
  ),
  'kibibytes'
);
assert.equal(
  resolveAlertDetailChartUnit(
    {
      policy: {
        threshold_unit: 'kibibytes',
        calculation_unit: 'bytes'
      }
    },
    'mebibytes'
  ),
  'mebibytes'
);
assert.equal(
  resolveAlertDetailChartUnit(
    { policy: { calculation_unit: 'bytes', metric_unit: 'bytes' } },
    ''
  ),
  'bytes'
);

const metricAlert = {
  policy: {
    monitor_object: 42,
    query_condition: {
      type: 'metric',
      metric_id: 88
    }
  }
};

assert.deepEqual(buildAlertDetailMetricQuery(metricAlert), {
  id: 88,
  monitor_object_id: 42
});
assert.equal(
  buildAlertDetailMetricQuery({
    policy: {
      query_condition: { type: 'metric', metric_id: 88 }
    }
  }),
  null
);
assert.equal(
  buildAlertDetailMetricQuery({
    policy: {
      monitor_object: 'all',
      query_condition: { type: 'metric', metric_id: 88 }
    }
  }),
  null
);
assert.equal(
  buildAlertDetailMetricQuery({
    policy: {
      monitor_object: 42,
      query_condition: { type: 'formula', result_name: 'cpu_sum' }
    }
  }),
  null
);
assert.equal(
  buildAlertDetailMetricQuery({
    policy: {
      monitor_object: 42,
      query_condition: { type: 'pmq' }
    }
  }),
  null
);

console.log('monitor-alert-detail snapshot validation passed');
