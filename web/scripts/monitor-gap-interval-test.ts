import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ChartData } from '../src/app/monitor/types';
import {
  attachGapIntervals,
  buildGapDetectionParams,
  deriveVisibleGapIntervalsFromChartData,
  GAP_INTERVAL_AREA_STYLE,
  GAP_INTERVAL_BOUNDARY_STYLE,
  getChartDataWithGapBreaks,
  expandGapIntervalsToChartPoints,
  getRenderedGapIntervals,
  mergeGapIntervalsForDisplay,
} from '../src/app/monitor/utils/gapIntervals';
import { areLazyMetricItemPropsEqual } from '../src/app/monitor/components/metric-views/lazyMetricItemMemo';
import { createMetricQueryWindow } from '../src/app/monitor/components/metric-views/queryWindow';

const memoizedViewData: ChartData[] = [{ time: 300, value1: 1 }];
const stableMetricProps = {
  item: { id: 1, viewData: memoizedViewData },
  xAxisDomain: [0, 900] as [number, number],
  isLoading: false,
  resetKey: 1,
  isLoaded: true,
  isCancelled: false,
  isInViewport: true,
};

assert.equal(
  areLazyMetricItemPropsEqual(
    stableMetricProps,
    {
      ...stableMetricProps,
      xAxisDomain: [0, 3600],
    }
  ),
  false,
  'changing a fixed query window must re-render the chart even when data is unchanged'
);

assert.deepEqual(
  createMetricQueryWindow({ timeRange: [], originValue: 60 }, 3_600_000),
  {
    startMs: 0,
    endMs: 3_600_000,
    xAxisDomain: [0, 3600],
  },
  'one query cycle must share one exact one-hour request and chart window'
);

for (const minutes of [15, 30, 60]) {
  const queryWindow = createMetricQueryWindow(
    { timeRange: [], originValue: minutes },
    3_600_000
  );
  assert.equal(
    queryWindow && queryWindow.xAxisDomain[1] - queryWindow.xAxisDomain[0],
    minutes * 60,
    `recent ${minutes} minutes must produce an exact fixed chart domain`
  );
}

for (const entryFile of [
  'src/app/monitor/(pages)/view/monitorView.tsx',
  'src/app/monitor/components/metric-views/index.tsx',
]) {
  const source = readFileSync(resolve(process.cwd(), entryFile), 'utf8');
  assert.match(
    source,
    /xAxisDomain=\{activeQueryWindow\?\.xAxisDomain\}/,
    `${entryFile} must pass the shared query window to LazyMetricItem`
  );
}

assert.deepEqual(
  createMetricQueryWindow({ timeRange: [600_000, 1_500_000], originValue: 0 }, 9_999_999),
  {
    startMs: 600_000,
    endMs: 1_500_000,
    xAxisDomain: [600, 1500],
  },
  'custom ranges must not depend on the current clock'
);

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
  fill: 'var(--color-chart-gap-fill)',
  fillOpacity: 1,
  strokeOpacity: 0,
});

assert.deepEqual(GAP_INTERVAL_BOUNDARY_STYLE, {
  stroke: 'var(--color-chart-gap-boundary)',
  strokeDasharray: '3 3',
  strokeWidth: 1,
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

const clippedXAxisDomain: [number, number] = [100, 900];
const clippedLeadingGapData: ChartData[] = [300, 360, 420].map((time, index) => ({
  time,
  value1: index + 1,
  seriesMetrics: { value1: { instance_id: 'host-a' } },
}));
const clippedLeadingGap = [{
  start: 0,
  end: 240,
  duration: 300,
  series: [{ metric: { instance_id: 'host-a' } }],
}];

assert.deepEqual(
  getRenderedGapIntervals(clippedLeadingGapData, clippedLeadingGap, clippedXAxisDomain),
  [{
    start: 100,
    end: 270,
    duration: 170,
    series: [{ metric: { instance_id: 'host-a' } }],
  }]
);

assert.deepEqual(
  getChartDataWithGapBreaks(
    clippedLeadingGapData,
    clippedLeadingGap,
    clippedXAxisDomain
  ).map((point) => ({ time: point.time, value1: point.value1 })),
  [
    { time: 185, value1: null },
    { time: 270, value1: 1 },
    { time: 300, value1: 1 },
    { time: 360, value1: 2 },
    { time: 420, value1: 3 },
  ]
);

assert.deepEqual(
  getChartDataWithGapBreaks(
    [
      { time: 0, value1: 1, seriesMetrics: { value1: { instance_id: 'host-a' } } },
      { time: 72, value1: 2, seriesMetrics: { value1: { instance_id: 'host-a' } } },
      { time: 216, value1: 3, seriesMetrics: { value1: { instance_id: 'host-a' } } },
    ],
    [{
      start: 100,
      end: 170,
      duration: 70,
      series: [{ metric: { instance_id: 'host-a' } }],
    }]
  ).map((point) => ({ time: point.time, value1: point.value1 })),
  [
    { time: 0, value1: 1 },
    { time: 72, value1: 2 },
    { time: 86, value1: 2 },
    { time: 139.5, value1: null },
    { time: 193, value1: 3 },
    { time: 216, value1: 3 },
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
  [{ start: 86, end: 193, duration: 107 }]
);

assert.deepEqual(
  getRenderedGapIntervals(
    [
      { time: 0, value1: 1 },
      { time: 75, value1: 1 },
      { time: 150, value1: Number.NaN },
      { time: 225, value1: Number.NaN },
      { time: 300, value1: 1 },
      { time: 375, value1: 1 },
    ],
    [{ start: 160, end: 260, duration: 100 }]
  ),
  [{ start: 117.5, end: 280, duration: 162.5 }]
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
      start: 91,
      end: 173,
      duration: 82,
      series: [
        {
          metric: { instance_id: 'host-a', mount: '/' },
          missing_points: 3,
        },
      ],
    },
  ]
);

assert.deepEqual(
  getRenderedGapIntervals(
    [
      { time: 600, value1: 1, seriesMetrics: { value1: { instance_id: 'host-a' } } },
      { time: 660, value1: 2, seriesMetrics: { value1: { instance_id: 'host-a' } } },
      { time: 720, value1: 3, seriesMetrics: { value1: { instance_id: 'host-a' } } },
    ],
    [
      { start: 0, end: 540, duration: 600, series: [{ metric: { instance_id: 'host-a' } }] },
      { start: 780, end: 900, duration: 180, series: [{ metric: { instance_id: 'host-a' } }] },
    ],
    [0, 900]
  ),
  [
    { start: 0, end: 570, duration: 570, series: [{ metric: { instance_id: 'host-a' } }] },
    { start: 750, end: 900, duration: 150, series: [{ metric: { instance_id: 'host-a' } }] },
  ]
);

console.log('monitor gap interval logic ok');
