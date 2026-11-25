import assert from 'node:assert/strict';
import test from 'node:test';
import { referenceLineColor } from '../chartDisplay';
import {
  applyBarLineGuides,
  REFERENCE_GUIDE_SERIES_ID,
  withoutReferenceGuideSeries,
  type BarLineGuideOption,
} from '../barLineGuides';

const identity = (value: number) => value;

const paint = (
  option: BarLineGuideOption,
  input: Parameters<typeof applyBarLineGuides>[1],
) => {
  applyBarLineGuides(option, input);
  return option;
};

const baseInput = {
  scale: identity,
  scaleFloat: identity,
};

const guideOf = (option: BarLineGuideOption) => {
  const guide = option.series.find((series) => series.id === REFERENCE_GUIDE_SERIES_ID);
  assert.equal(guide?.yAxisIndex, 0);
  assert.equal(option.series[0]?.id === REFERENCE_GUIDE_SERIES_ID, false);
  assert.equal(option.series[0]?.markLine, undefined);
  return guide;
};

test('bar stack writes total and line deletes stack', () => {
  const bar = paint({
    series: [{ stack: 'old' }, { itemStyle: { color: '#111' } } as { stack?: string }],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'bar',
    display: { stackBars: true },
    data: { categories: ['a'], series: [{ name: 'a', data: [1] }, { name: 'b', data: [2] }] },
  });
  assert.equal(bar.series[0]?.stack, 'total');
  assert.equal(bar.series[1]?.stack, 'total');
  assert.equal((bar.series[1] as { itemStyle?: { color?: string } }).itemStyle?.color, '#111');
  assert.equal('lineStyle' in (bar.series[0] || {}), false);

  const line = paint({
    series: [{ stack: 'total', lineStyle: { color: '#222' } }],
    yAxis: { min: 4, max: 9 },
  }, {
    ...baseInput,
    chart: 'line',
    display: { stackBars: true },
    data: { categories: ['a'], values: [1, 3] },
  });
  assert.equal('stack' in (line.series[0] || {}), false);
  assert.equal((line.series[0] as { lineStyle?: { color?: string } }).lineStyle?.color, '#222');
  assert.equal(line.series.length, 1);
  assert.equal('min' in line.yAxis, false);
  assert.equal('max' in line.yAxis, false);
});

test('reference name is the label and zero stays while threshold zero is skipped', () => {
  const option = paint({
    series: [{}],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'line',
    display: {
      referenceLines: [
        { name: 'baseline', value: 0 as never },
        { name: 'low', value: -2 as never },
      ],
    },
    data: { categories: ['a'], values: [1, 5] },
    thresholdColors: [
      { value: 0, color: '#skip' },
      { value: '10', color: '#limit' },
    ],
  });
  const markLine = guideOf(option)?.markLine as {
    silent: boolean;
    symbol: string;
    data: Array<{
      yAxis: number;
      label: { formatter: string; color: string; position: string };
    }>;
  };
  assert.equal(markLine.silent, true);
  assert.equal(markLine.symbol, 'none');
  assert.deepEqual(markLine.data.map((item) => item.yAxis), [10, 0, -2]);
  assert.equal(markLine.data[0]?.label.formatter, '10');
  assert.equal(markLine.data[0]?.label.color, '#limit');
  assert.equal(markLine.data[1]?.label.formatter, 'baseline');
  assert.equal(markLine.data[1]?.label.color, referenceLineColor());
  assert.equal(markLine.data[1]?.label.position, 'insideEndTop');
  assert.equal(markLine.data[2]?.label.formatter, 'low');
  assert.equal(markLine.data[2]?.label.position, 'insideEndTop');
  assert.equal(option.yAxis.min, -2);
  assert.equal('max' in option.yAxis, false);
});

test('axis end is set only when a reference sits outside the plotted extent', () => {
  const inside = paint({
    series: [{}],
    yAxis: { min: 1, max: 9 },
  }, {
    ...baseInput,
    chart: 'bar',
    display: { referenceLines: [{ name: 'mid', value: 3 as never }] },
    data: { categories: ['a', 'b'], values: [1, 5] },
  });
  assert.equal('min' in inside.yAxis, false);
  assert.equal('max' in inside.yAxis, false);
  assert.equal(inside.series[0]?.markLine, undefined);
  assert.equal(guideOf(inside)?.id, REFERENCE_GUIDE_SERIES_ID);

  const above = paint({
    series: [{}],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'bar',
    display: { referenceLines: [{ name: 'high', value: 8 as never }] },
    data: { categories: ['a'], values: [1, 5] },
  });
  assert.equal('min' in above.yAxis, false);
  assert.equal(above.yAxis.max, 8);
  const highMark = (guideOf(above)?.markLine as { data: Array<{ yAxis: number; label: { position: string; color: string } }> }).data[0];
  assert.equal(highMark?.yAxis, 8);
  assert.equal(highMark?.label.position, 'insideEndBottom');
  assert.equal(highMark?.label.color, referenceLineColor());

  const empty = paint({
    series: [],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'line',
    display: {
      referenceLines: [
        { name: 'low', value: -2 as never },
        { name: 'high', value: 4 as never },
      ],
    },
    data: { categories: ['a'], values: [null] },
  });
  assert.equal(empty.series.length, 0);
  assert.equal(empty.yAxis.min, -2);
  assert.equal(empty.yAxis.max, 4);
});

test('stacked bars measure positive and negative sums and rise from zero', () => {
  const stacked = paint({
    series: [{}, {}],
    yAxis: { min: -1 },
  }, {
    ...baseInput,
    chart: 'bar',
    display: {
      stackBars: true,
      referenceLines: [{ name: 'mid', value: 1 as never }],
    },
    data: {
      categories: ['a', 'b'],
      series: [
        { name: 'p', data: [2, 3] },
        { name: 'q', data: [3, 4] },
      ],
    },
  });
  assert.equal(
    stacked.series
      .filter((series) => series.id !== REFERENCE_GUIDE_SERIES_ID)
      .every((series) => series.stack === 'total'),
    true,
  );
  assert.equal(guideOf(stacked)?.stack, undefined);
  assert.equal('min' in stacked.yAxis, false);
  assert.equal('max' in stacked.yAxis, false);

  const belowZero = paint({
    series: [{}, {}],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'bar',
    display: {
      stackBars: true,
      referenceLines: [{ name: 'under', value: -1 as never }],
    },
    data: {
      categories: ['a'],
      values: [1],
      series: [{ name: 'q', data: [4] }],
    },
  });
  assert.equal(belowZero.yAxis.min, -1);
  assert.equal('max' in belowZero.yAxis, false);
});

test('a chosen reference color is the line color', () => {
  const option = paint({
    series: [{}],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'bar',
    display: {
      referenceLines: [{ name: 'alert', value: 8 as never, color: '#dc2626' }],
    },
    data: { categories: ['a'], values: [1, 5] },
  });
  const mark = (guideOf(option)?.markLine as { data: Array<{ lineStyle: { color: string } }> }).data[0];
  assert.equal(mark?.lineStyle.color, '#dc2626');
});

test('guide series stays off the legend and off the first data series', () => {
  const option = paint({
    series: [{ name: 'right', yAxisIndex: 1 }, { name: 'left', yAxisIndex: 0 }],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'line',
    display: { referenceLines: [{ name: '警戒', value: 80 as never }] },
    data: {
      categories: ['a'],
      series: [{ name: 'right', data: [1] }, { name: 'left', data: [40] }],
    },
  });
  assert.equal(option.series[0]?.yAxisIndex, 1);
  assert.equal(option.series[0]?.markLine, undefined);
  assert.equal(guideOf(option)?.yAxisIndex, 0);
  assert.deepEqual(
    withoutReferenceGuideSeries(option.series).map((series) => series.name),
    ['right', 'left'],
  );
});

test('a long series still yields an extent without spreading every point', () => {
  const values = Array.from({ length: 130_000 }, (_, index) => index - 10);
  const option = paint({
    series: [{}],
    yAxis: {},
  }, {
    ...baseInput,
    chart: 'line',
    display: { referenceLines: [{ name: 'low', value: -20 as never }] },
    data: { categories: ['a'], values },
  });
  assert.equal(option.yAxis.min, -20);
  assert.equal('max' in option.yAxis, false);
});

test('switches off do not walk the points', () => {
  const values = [1, 2, 3];
  let scanned = false;
  values.forEach = (() => {
    scanned = true;
  }) as typeof values.forEach;
  const option = paint({
    series: [{ stack: 'total', markLine: { data: [1] } }],
    yAxis: { min: 1, max: 9 },
  }, {
    ...baseInput,
    chart: 'bar',
    display: {},
    data: { categories: ['a', 'b', 'c'], values },
    thresholdColors: [{ value: 0, color: '#skip' }],
  });
  assert.equal(scanned, false);
  assert.equal(option.series.length, 1);
  assert.equal('stack' in (option.series[0] || {}), false);
  assert.equal('markLine' in (option.series[0] || {}), false);
  assert.equal('min' in option.yAxis, false);
  assert.equal('max' in option.yAxis, false);
});
