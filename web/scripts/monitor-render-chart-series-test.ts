import assert from 'node:assert/strict';
import { renderChart } from '../src/app/monitor/utils/common';

const splitSeriesChartData = renderChart(
  [
    {
      metric: { instance_id: 'host-a', mountpoint: '/' },
      values: [
        [0, '10'],
        [60, '10'],
      ],
    },
    {
      metric: { mountpoint: '/', instance_id: 'host-a' },
      values: [
        [300, '10'],
        [360, '10'],
      ],
    },
  ],
  [
    {
      instance_id_values: ['host-a'],
      instance_id_keys: ['instance_id'],
      instance_name: 'Host A',
      dimensions: [{ name: 'mountpoint', description: 'Mount point' }],
      title: 'Disk used',
    },
  ]
);

assert.deepEqual(
  splitSeriesChartData.map((point) => ({
    time: point.time,
    value1: point.value1,
    value2: point.value2,
  })),
  [
    { time: 0, value1: 10, value2: undefined },
    { time: 60, value1: 10, value2: undefined },
    { time: 300, value1: 10, value2: undefined },
    { time: 360, value1: 10, value2: undefined },
  ]
);

const multiDimensionChartData = renderChart(
  [
    {
      metric: { instance_id: 'host-a', mountpoint: '/' },
      values: [[0, '10']],
    },
    {
      metric: { instance_id: 'host-a', mountpoint: '/data' },
      values: [[0, '20']],
    },
  ],
  [
    {
      instance_id_values: ['host-a'],
      instance_id_keys: ['instance_id'],
      instance_name: 'Host A',
      dimensions: [{ name: 'mountpoint', description: 'Mount point' }],
      title: 'Disk used',
    },
  ]
);

assert.deepEqual(
  multiDimensionChartData.map((point) => ({
    time: point.time,
    value1: point.value1,
    value2: point.value2,
  })),
  [{ time: 0, value1: 10, value2: 20 }]
);

const volatileHostChartData = renderChart(
  [
    {
      metric: { instance_id: 'host-a', mount: '/', host: 'container-old' },
      values: [
        [0, '10'],
        [75, '10'],
        [150, null],
        [225, null],
      ],
    },
    {
      metric: { instance_id: 'host-a', mount: '/', host: 'container-new' },
      values: [
        [150, null],
        [225, null],
        [300, '10'],
        [375, '10'],
      ],
    },
  ],
  [
    {
      instance_id_values: ['host-a'],
      instance_id_keys: ['instance_id'],
      instance_name: 'Host A',
      dimensions: [{ name: 'mount', description: 'Mount point' }],
      title: 'Disk free',
    },
  ]
);

assert.deepEqual(
  volatileHostChartData.map((point) => ({
    time: point.time,
    value1: point.value1,
    value2: point.value2,
  })),
  [
    { time: 0, value1: 10, value2: undefined },
    { time: 75, value1: 10, value2: undefined },
    { time: 300, value1: 10, value2: undefined },
    { time: 375, value1: 10, value2: undefined },
  ]
);

const outOfOrderSeriesChartData = renderChart(
  [
    {
      metric: { instance_id: 'host-a', mount: '/', host: 'container-new' },
      values: [[300, '10']],
    },
    {
      metric: { instance_id: 'host-a', mount: '/', host: 'container-old' },
      values: [[75, '10']],
    },
  ],
  [
    {
      instance_id_values: ['host-a'],
      instance_id_keys: ['instance_id'],
      instance_name: 'Host A',
      dimensions: [{ name: 'mount', description: 'Mount point' }],
      title: 'Disk free',
    },
  ]
);

assert.deepEqual(
  outOfOrderSeriesChartData.map((point) => point.time),
  [75, 300]
);

console.log('monitor render chart series identity ok');
