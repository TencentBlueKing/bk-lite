import assert from 'node:assert/strict';
import {
  attachGapIntervals,
  buildGapDetectionParams,
  deriveVisibleGapIntervalsFromChartData,
  GAP_INTERVAL_AREA_STYLE,
  getChartDataWithGapBreaks,
  expandGapIntervalsToChartPoints,
  getRenderedGapIntervals,
  mergeGapIntervalsForDisplay,
} from '../src/app/monitor/utils/gapIntervals';

const params = buildGapDetectionParams(
  {
    query: 'cpu_usage',
    start: 0,
    end: 600000,
    step: 3600,
  },
  60
);

assert.deepEqual(params, {
  query: 'cpu_usage',
  start: 0,
  end: 600000,
  step: 3600,
  detect_gaps: true,
  collection_interval: 60,
});

assert.deepEqual(
  buildGapDetectionParams(
    {
      query: 'cpu_usage',
      start: 0,
      end: 600000,
      step: 3600,
    },
    ''
  ),
  {
    query: 'cpu_usage',
    start: 0,
    end: 600000,
    step: 3600,
  }
);

const chartData = attachGapIntervals(
  [
    { time: 0, value1: 1 },
    { time: 3600, value1: 2 },
  ],
  [
    { start: 180, end: 420, duration: 300 },
    { start: Number.NaN, end: 900 },
  ]
);

assert.deepEqual(chartData, [
  {
    time: 0,
    value1: 1,
    gapIntervals: [{ start: 180, end: 420, duration: 300 }],
  },
  {
    time: 3600,
    value1: 2,
    gapIntervals: [{ start: 180, end: 420, duration: 300 }],
  },
]);

assert.deepEqual(GAP_INTERVAL_AREA_STYLE, {
  fill: 'rgba(245, 63, 63, 0.18)',
  fillOpacity: 1,
  strokeOpacity: 0,
});

assert.deepEqual(
  expandGapIntervalsToChartPoints(
    [
      { time: 0, value1: 1 },
      { time: 3600, value1: 2 },
      { time: 7200, value1: 3 },
    ],
    [{ start: 3660, end: 3900, duration: 300 }]
  ),
  [{ start: 3600, end: 7200, duration: 3600 }]
);

assert.deepEqual(
  mergeGapIntervalsForDisplay([
    { start: 0, end: 216, duration: 216 },
    { start: 180, end: 360, duration: 180 },
    { start: 720, end: 792, duration: 72 },
  ]),
  [
    { start: 0, end: 360, duration: 360 },
    { start: 720, end: 792, duration: 72 },
  ]
);

assert.deepEqual(
  deriveVisibleGapIntervalsFromChartData(
    [
      { time: 0, value1: 1, value2: 10 },
      { time: 72, value1: Number.NaN, value2: 11 },
      { time: 144, value2: 12 },
      { time: 216, value1: 2, value2: 13 },
    ],
    ['value1', 'value2']
  ),
  [{ start: 0, end: 216, duration: 216 }]
);

assert.deepEqual(
  deriveVisibleGapIntervalsFromChartData(
    [
      { time: 0 },
      { time: 72, value1: 1 },
      { time: 144, value1: Number.NaN },
    ],
    ['value1']
  ),
  []
);

assert.deepEqual(
  getRenderedGapIntervals(
    [
      { time: 0, value1: 1 },
      { time: 72, value1: 2 },
      { time: 144, value2: 10 },
      { time: 216, value1: 3 },
    ],
    []
  ),
  []
);

assert.deepEqual(
  getRenderedGapIntervals(
    [
      { time: 0, value1: 1 },
      { time: 75, value1: 1 },
      { time: 300, value1: 1 },
      { time: 375, value1: 1 },
    ],
    []
  ),
  [{ start: 75, end: 300, duration: 225 }]
);

assert.deepEqual(
  getChartDataWithGapBreaks(
    [
      { time: 0, value1: 1 },
      { time: 75, value1: 1 },
      { time: 300, value1: 1 },
      { time: 375, value1: 1 },
    ],
    []
  ).map((point) => ({
    time: point.time,
    value1: point.value1,
  })),
  [
    { time: 0, value1: 1 },
    { time: 75, value1: 1 },
    { time: 187.5, value1: null },
    { time: 300, value1: 1 },
    { time: 375, value1: 1 },
  ]
);

assert.deepEqual(
  getRenderedGapIntervals(
    [
      { time: 0, value1: 1 },
      { time: 72, value1: 2 },
      { time: 144, value1: Number.NaN },
      { time: 216, value1: 3 },
    ],
    [{ start: 100, end: 170, duration: 70 }]
  ),
  [{ start: 72, end: 216, duration: 144 }]
);

assert.deepEqual(
  getRenderedGapIntervals(
    [
      {
        time: 72,
        value1: 1,
        value2: 9,
        seriesMetrics: {
          value1: { instance_id: 'host-a', mount: '/' },
          value2: { instance_id: 'host-a', mount: '/boot' },
        },
      },
      {
        time: 100,
        value1: Number.NaN,
        value2: 9,
        seriesMetrics: {
          value1: { instance_id: 'host-a', mount: '/' },
          value2: { instance_id: 'host-a', mount: '/boot' },
        },
      },
      {
        time: 144,
        value1: Number.NaN,
        value2: 9,
        seriesMetrics: {
          value1: { instance_id: 'host-a', mount: '/' },
          value2: { instance_id: 'host-a', mount: '/boot' },
        },
      },
      {
        time: 216,
        value1: 2,
        value2: 9,
        seriesMetrics: {
          value1: { instance_id: 'host-a', mount: '/' },
          value2: { instance_id: 'host-a', mount: '/boot' },
        },
      },
    ],
    [
      {
        start: 110,
        end: 130,
        duration: 30,
        series: [
          {
            metric: { instance_id: 'host-a', mount: '/' },
            missing_points: 3,
          },
        ],
      },
    ]
  ),
  [
    {
      start: 72,
      end: 216,
      duration: 144,
      series: [
        {
          metric: { instance_id: 'host-a', mount: '/' },
          missing_points: 3,
        },
      ],
    },
  ]
);

console.log('monitor gap interval logic ok');
