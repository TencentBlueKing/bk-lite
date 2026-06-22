import assert from 'node:assert/strict';
import {
  attachGapIntervals,
  buildGapDetectionParams,
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

console.log('monitor gap interval logic ok');
