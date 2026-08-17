import assert from 'node:assert/strict';

import {
  buildAlertDetailMetricQuery,
  buildAlertSnapshotChartModel,
  buildAlertSnapshotChartValues,
  decorateAlertSnapshotChartData,
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
assert.deepEqual(buildAlertSnapshotChartModel(thresholdSnapshots).gapIntervals, []);
assert.deepEqual(buildAlertSnapshotChartModel(thresholdSnapshots).xAxisDomain, [100, 320]);
assert.deepEqual(buildAlertSnapshotChartModel(thresholdSnapshots).noDataTimes, []);
assert.equal(buildAlertSnapshotChartModel(thresholdSnapshots, { alertType: 'alert' }).gapIntervals.length, 0);

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

assert.deepEqual(
  buildAlertSnapshotChartValues(noDataSnapshots),
  [
    [400, '1'],
    [460, '2'],
  ]
);
assert.deepEqual(buildAlertSnapshotChartModel(noDataSnapshots).gapIntervals, []);
assert.deepEqual(
  buildAlertSnapshotChartModel(noDataSnapshots, { alertType: 'no_data' }).gapIntervals,
  [
    { start: 300, end: 400, duration: 100, align: 'exact' },
  ]
);
assert.deepEqual(
  buildAlertSnapshotChartModel(noDataSnapshots, { alertType: 'no_data' }).xAxisDomain,
  [300, 460]
);

const unix = (iso: string) => Date.parse(iso) / 1000;

const firingNoDataSnapshots = [
  {
    type: 'pre_alert',
    snapshot_time: '2026-08-17T03:22:00Z',
    raw_data: {
      values: [
        [unix('2026-08-17T03:22:00Z'), '0.12'],
      ],
    },
  },
  ...Array.from({ length: 15 }, (_, index) => ({
    type: 'no_data',
    snapshot_time: `2026-08-17T03:${String(23 + index).padStart(2, '0')}:00Z`,
    raw_data: {},
  })),
];

const firingNoDataChart = buildAlertSnapshotChartModel(firingNoDataSnapshots, {
  alertType: 'no_data',
});
assert.deepEqual(firingNoDataChart.dataValues, [[unix('2026-08-17T03:22:00Z'), '0.12']]);
assert.equal(firingNoDataChart.gapIntervals.length, 1);
assert.equal(firingNoDataChart.gapIntervals[0].start, unix('2026-08-17T03:22:00Z'));
assert.equal(firingNoDataChart.gapIntervals[0].end, unix('2026-08-17T03:37:00Z'));
assert.equal(firingNoDataChart.gapIntervals[0].align, 'exact');
assert.deepEqual(firingNoDataChart.xAxisDomain, [
  unix('2026-08-17T03:22:00Z'),
  unix('2026-08-17T03:37:00Z'),
]);
assert.equal(firingNoDataChart.noDataTimes.length, 15);

const decoratedFiringNoDataChart = decorateAlertSnapshotChartData(
  [{ time: unix('2026-08-17T03:22:00Z'), value1: 0.12 }],
  firingNoDataChart.gapIntervals,
  firingNoDataChart.xAxisDomain,
  firingNoDataChart.noDataTimes
);
assert.equal(
  decoratedFiringNoDataChart.find((item) => item.time === unix('2026-08-17T03:22:00Z'))?.value1,
  0.12
);
assert.equal(
  decoratedFiringNoDataChart.filter((item) => item.noDataSnapshot).length,
  15
);

const recoveredNoDataSnapshots = [
  {
    type: 'no_data',
    snapshot_time: '2026-08-14T03:02:00Z',
    raw_data: {},
  },
  {
    type: 'no_data',
    snapshot_time: '2026-08-14T03:07:00Z',
    raw_data: {},
  },
  {
    type: 'no_data',
    snapshot_time: '2026-08-14T03:12:00Z',
    raw_data: {},
  },
  {
    type: 'event',
    raw_data: {
      values: [
        [unix('2026-08-14T03:12:00Z'), '4'],
        [unix('2026-08-14T03:15:00Z'), '12'],
      ],
    },
  },
];

const recoveredNoDataChart = buildAlertSnapshotChartModel(recoveredNoDataSnapshots, {
  alertType: 'no_data',
});
assert.deepEqual(recoveredNoDataChart.dataValues, [
  [unix('2026-08-14T03:12:00Z'), '4'],
  [unix('2026-08-14T03:15:00Z'), '12'],
]);
assert.deepEqual(recoveredNoDataChart.gapIntervals, [
  {
    start: unix('2026-08-14T03:02:00Z'),
    end: unix('2026-08-14T03:12:00Z'),
    duration: 600,
    align: 'exact',
  },
]);
assert.deepEqual(recoveredNoDataChart.xAxisDomain, [
  unix('2026-08-14T03:02:00Z'),
  unix('2026-08-14T03:15:00Z'),
]);

const onlyNoDataSnapshots = [
  {
    type: 'no_data',
    snapshot_time: '2026-08-17T03:24:00Z',
    raw_data: {},
  },
  {
    type: 'no_data',
    snapshot_time: '2026-08-17T03:34:00Z',
    raw_data: {},
  },
];

const onlyNoDataChart = buildAlertSnapshotChartModel(onlyNoDataSnapshots, {
  alertType: 'no_data',
});
assert.deepEqual(onlyNoDataChart.dataValues, []);
assert.deepEqual(onlyNoDataChart.gapIntervals, [
  {
    start: Date.parse('2026-08-17T03:24:00Z') / 1000,
    end: Date.parse('2026-08-17T03:34:00Z') / 1000,
    duration: 600,
    align: 'exact',
  },
]);
assert.deepEqual(onlyNoDataChart.xAxisDomain, [
  Date.parse('2026-08-17T03:24:00Z') / 1000,
  Date.parse('2026-08-17T03:34:00Z') / 1000,
]);

const noDataSnapshotsWithValues = [
  {
    type: 'pre_alert',
    raw_data: {
      values: [[100, '8']],
    },
  },
  {
    type: 'no_data',
    snapshot_time: '1970-01-01T00:03:20Z',
    raw_data: {
      values: [[200, '8']],
    },
  },
  {
    type: 'event',
    raw_data: {
      values: [[300, '11']],
    },
  },
];

const noDataWithValuesChart = buildAlertSnapshotChartModel(noDataSnapshotsWithValues, {
  alertType: 'no_data',
});
assert.deepEqual(noDataWithValuesChart.dataValues, [
  [100, '8'],
  [300, '11'],
]);
assert.deepEqual(noDataWithValuesChart.gapIntervals, [
  { start: 100, end: 300, duration: 200, align: 'exact' },
]);

const leftoverBeforeNoData = buildAlertSnapshotChartModel(
  [
    {
      type: 'pre_alert',
      raw_data: { values: [[100, '1']] },
    },
    {
      type: 'event',
      raw_data: { values: [[140, '1'], [180, '1']] },
    },
    {
      type: 'no_data',
      snapshot_time: '1970-01-01T00:04:00Z',
      raw_data: {},
    },
    {
      type: 'no_data',
      snapshot_time: '1970-01-01T00:05:00Z',
      raw_data: {},
    },
  ],
  { alertType: 'no_data' }
);
assert.deepEqual(leftoverBeforeNoData.dataValues, [[100, '1']]);
assert.deepEqual(leftoverBeforeNoData.gapIntervals, [
  { start: 100, end: 300, duration: 200, align: 'exact' },
]);

const delayedNoDataChart = buildAlertSnapshotChartModel(
  [
    {
      type: 'pre_alert',
      snapshot_time: '2026-08-17T06:24:01Z',
      raw_data: {
        values: [
          [unix('2026-08-17T06:19:01Z'), '1'],
          [unix('2026-08-17T06:24:01Z'), '1'],
        ],
      },
    },
    {
      type: 'no_data',
      event_time: '2026-08-17T06:34:02Z',
    },
    {
      type: 'no_data',
      event_time: '2026-08-17T06:44:02Z',
    },
  ],
  { alertType: 'no_data' }
);
assert.equal(delayedNoDataChart.gapIntervals[0].start, unix('2026-08-17T06:24:01Z'));
assert.equal(delayedNoDataChart.gapIntervals[0].end, unix('2026-08-17T06:44:02Z'));
assert.deepEqual(delayedNoDataChart.noDataTimes, [
  unix('2026-08-17T06:34:02Z'),
  unix('2026-08-17T06:44:02Z'),
]);
assert.deepEqual(delayedNoDataChart.dataValues, [
  [unix('2026-08-17T06:19:01Z'), '1'],
  [unix('2026-08-17T06:24:01Z'), '1'],
]);
assert.deepEqual(
  buildAlertSnapshotChartModel(
    [
      {
        type: 'pre_alert',
        raw_data: { values: [[100, '1']] },
      },
      {
        type: 'event',
        raw_data: { values: [[140, '1'], [180, '1']] },
      },
    ],
    { alertType: 'alert' }
  ).dataValues,
  [
    [100, '1'],
    [140, '1'],
    [180, '1'],
  ]
);

// 阈值告警持续触发时，后续扫描的 raw_data.values 可能停在同一个汇聚窗口，
// 但 event_time 仍在前进。详情图必须跟扫描时间轴，不能停在第一段窗口末尾。
const stalledThresholdSnapshots = [
  {
    type: 'pre_alert',
    snapshot_time: '2026-08-17T07:11:01Z',
    raw_data: {
      values: [[unix('2026-08-17T07:11:01Z'), '1']],
    },
  },
  {
    type: 'event',
    event_time: '2026-08-17T07:11:01Z',
    snapshot_time: '2026-08-17T07:11:01Z',
    raw_data: {
      values: [
        [unix('2026-08-17T07:11:01Z'), '1'],
        [unix('2026-08-17T07:16:02Z'), '1'],
      ],
    },
  },
  {
    type: 'event',
    event_time: '2026-08-17T07:22:02Z',
    snapshot_time: '2026-08-17T07:22:02Z',
    raw_data: {
      values: [[unix('2026-08-17T07:16:02Z'), '1']],
    },
  },
  {
    type: 'event',
    event_time: '2026-08-17T07:23:00Z',
    snapshot_time: '2026-08-17T07:23:00Z',
    raw_data: {
      values: [[unix('2026-08-17T07:16:02Z'), '1']],
    },
  },
];
const stalledThresholdChart = buildAlertSnapshotChartModel(
  stalledThresholdSnapshots,
  { alertType: 'alert' }
);
assert.deepEqual(stalledThresholdChart.dataValues, [
  [unix('2026-08-17T07:11:01Z'), '1'],
  [unix('2026-08-17T07:16:02Z'), '1'],
  [unix('2026-08-17T07:22:02Z'), '1'],
  [unix('2026-08-17T07:23:00Z'), '1'],
]);
assert.deepEqual(stalledThresholdChart.xAxisDomain, [
  unix('2026-08-17T07:11:01Z'),
  unix('2026-08-17T07:23:00Z'),
]);
assert.equal(stalledThresholdChart.gapIntervals.length, 0);
assert.deepEqual(
  buildAlertSnapshotChartModel(stalledThresholdSnapshots, {
    alertType: 'no_data',
  }).dataValues,
  [
    [unix('2026-08-17T07:11:01Z'), '1'],
    [unix('2026-08-17T07:16:02Z'), '1'],
  ]
);

const decoratedEmptyChart = decorateAlertSnapshotChartData(
  [],
  onlyNoDataChart.gapIntervals,
  onlyNoDataChart.xAxisDomain
);
assert.deepEqual(
  decoratedEmptyChart.map((item) => item.time),
  onlyNoDataChart.xAxisDomain
);
assert.deepEqual(decoratedEmptyChart[0]?.gapIntervals, onlyNoDataChart.gapIntervals);
assert.equal(decoratedEmptyChart[0]?.value1, null);
assert.equal(decoratedEmptyChart[1]?.value1, null);

const firingOnlyNoDataSnapshots = Array.from({ length: 12 }, (_, index) => ({
  type: 'no_data',
  event_time: `2026-08-17T06:${String(index + 1).padStart(2, '0')}:00Z`,
}));
const firingOnlyNoDataChart = buildAlertSnapshotChartModel(firingOnlyNoDataSnapshots, {
  alertType: 'no_data',
});
assert.deepEqual(firingOnlyNoDataChart.dataValues, []);
assert.equal(firingOnlyNoDataChart.gapIntervals.length, 1);
assert.equal(firingOnlyNoDataChart.gapIntervals[0].start, unix('2026-08-17T06:01:00Z'));
assert.equal(firingOnlyNoDataChart.gapIntervals[0].end, unix('2026-08-17T06:12:00Z'));
assert.deepEqual(firingOnlyNoDataChart.xAxisDomain, [
  unix('2026-08-17T06:01:00Z'),
  unix('2026-08-17T06:12:00Z'),
]);
assert.deepEqual(
  firingOnlyNoDataChart.noDataTimes,
  Array.from({ length: 12 }, (_, index) =>
    unix(`2026-08-17T06:${String(index + 1).padStart(2, '0')}:00Z`)
  )
);
const decoratedFiringOnlyNoDataChart = decorateAlertSnapshotChartData(
  [],
  firingOnlyNoDataChart.gapIntervals,
  firingOnlyNoDataChart.xAxisDomain,
  firingOnlyNoDataChart.noDataTimes
);
assert.equal(decoratedFiringOnlyNoDataChart.length, 12);
assert.ok(
  decoratedFiringOnlyNoDataChart.every(
    (item) => item.value1 === null && item.noDataSnapshot === true
  )
);
assert.deepEqual(
  decoratedFiringOnlyNoDataChart.map((item) => item.time),
  firingOnlyNoDataChart.noDataTimes
);
assert.deepEqual(
  decoratedFiringOnlyNoDataChart[0]?.gapIntervals,
  firingOnlyNoDataChart.gapIntervals
);

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
