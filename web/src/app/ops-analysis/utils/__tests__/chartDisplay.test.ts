import assert from 'node:assert/strict';
import test from 'node:test';
import {
  chartDisplayPatch,
  presentBar,
  presentPie,
  presentRanking,
  readChartDisplay,
} from '../chartDisplay';

const ranked = [
  { name: 'same', value: 1 },
  { name: 'same', value: 9 },
  { name: 'later', value: 3 },
];

test('invalid limits do not cut', () => {
  const invalid = [null, '', 0, -2, 1.5, Number.NaN, true, '2', false, Infinity];
  invalid.forEach((displayLimit) => {
    const display = readChartDisplay({ displayLimit, sortByValue: 'true' });
    assert.equal(display.displayLimit, undefined);
    assert.equal(display.sortByValue, undefined);
    assert.equal(presentRanking(ranked, display), ranked);
  });
  assert.deepEqual(readChartDisplay(undefined), {});
  assert.equal(readChartDisplay({ sortByValue: false }).sortByValue, undefined);
  assert.equal(readChartDisplay({ sortByValue: true }).sortByValue, true);
});

test('ranking keeps the first N rows and does not reorder', () => {
  const shown = presentRanking(ranked, readChartDisplay({ displayLimit: 2 }));
  assert.equal(shown.length, 2);
  assert.equal(shown[0], ranked[0]);
  assert.equal(shown[1], ranked[1]);
  assert.deepEqual(shown.map((item) => item.name), ['same', 'same']);
  assert.equal(presentRanking(ranked, readChartDisplay({ displayLimit: 3 })), ranked);
  assert.equal(presentRanking(ranked, {}), ranked);
});

test('pie with neither option returns the same array', () => {
  const slices = [
    { name: 'a', value: 1, __link: { raw: 1 } },
    { name: 'b', value: 4 },
  ];
  assert.equal(presentPie(slices, {}, '其他'), slices);
});

test('pie sort is value desc and stable on ties', () => {
  const slices = [
    { name: 'low', value: 1 },
    { name: 'tie-a', value: 4, __link: { raw: 'a' } },
    { name: 'tie-b', value: 4, __link: { raw: 'b' } },
  ];
  const shown = presentPie(slices, { sortByValue: true }, '其他');
  assert.deepEqual(shown.map((slice) => slice.name), ['tie-a', 'tie-b', 'low']);
  assert.equal(shown[0], slices[1]);
  assert.equal(shown[1], slices[2]);
  assert.equal(shown[0]?.__link?.raw, 'a');
});

test('pie limit without sort keeps the current prefix', () => {
  const slices = [
    { name: 'first', value: 1, __link: { raw: 'first' } },
    { name: 'second', value: 9 },
    { name: 'third', value: 4 },
  ];
  const shown = presentPie(slices, readChartDisplay({ displayLimit: 2 }), '其他');
  assert.equal(shown[0], slices[0]);
  assert.equal(shown[1], slices[1]);
  assert.equal(shown[2]?.name, '其他');
  assert.equal(shown[2]?.value, 4);
  assert.equal(shown[2]?.__link, undefined);
  assert.equal('label' in (shown[2] || {}), false);
});

test('pie sort plus limit keeps the largest N and appends one unlinked tail', () => {
  const slices = [
    { name: 'small', value: 1, __link: { raw: 'small' } },
    { name: 'large', value: 8, __link: { raw: 'large' } },
    { name: 'mid', value: 3, __link: { raw: 'mid' } },
  ];
  const shown = presentPie(
    slices,
    { ...readChartDisplay({ displayLimit: 2 }), sortByValue: true },
    '其他',
  );
  assert.equal(shown[0], slices[1]);
  assert.equal(shown[1], slices[2]);
  assert.deepEqual(shown[2], { name: '其他', value: 1 });
  assert.equal(shown[2]?.__link, undefined);
});

test('pie with no tail does not append', () => {
  const slices = [
    { name: 'a', value: 2 },
    { name: 'b', value: 1 },
  ];
  assert.equal(presentPie(slices, readChartDisplay({ displayLimit: 2 }), '其他'), slices);
  const sorted = presentPie(slices, { sortByValue: true }, '其他');
  assert.deepEqual(sorted.map((slice) => slice.name), ['a', 'b']);
  assert.equal(sorted.some((slice) => slice.name === '其他'), false);
});

test('bar time axis returns the same object even when both options are set', () => {
  const chart = {
    categories: ['earlier', 'later'],
    series: [
      { name: 'in', data: [1, 100] },
      { name: 'out', data: [2, 3] },
    ],
  };
  const rawData = {
    in: [[1700000000, 1], [1700003600, 100]],
    out: [[1700000000, 2], [1700003600, 3]],
  };
  const shown = presentBar(
    chart,
    { ...readChartDisplay({ displayLimit: 1 }), sortByValue: true },
    { rawData, mapping: undefined, otherName: '其他' },
  );
  assert.equal(shown, chart);
  assert.deepEqual(shown.categories, ['earlier', 'later']);
});

test('bar limit without sort keeps the current prefix', () => {
  const chart = {
    categories: ['low', 'high', 'mid'],
    values: [1, 5, 3],
  };
  const rawData = [
    { name: 'low', value: 1 },
    { name: 'high', value: 5 },
    { name: 'mid', value: 3 },
  ];
  const shown = presentBar(chart, readChartDisplay({ displayLimit: 2 }), {
    rawData,
    mapping: undefined,
    otherName: '其他',
  });
  assert.deepEqual(shown.categories, ['low', 'high', '其他']);
  assert.deepEqual(shown.values, [1, 5, 3]);
});

test('bar non-time multi-series sorts by the sum and appends 其他', () => {
  const chart = {
    categories: ['mid', 'empty', 'top', 'zero'],
    series: [
      { name: 'cpu', data: [1, null, 2, 0] },
      { name: 'mem', data: [1, null, 4, 0] },
    ],
  };
  const rawData = [
    { name: 'mid' },
    { name: 'empty' },
    { name: 'top' },
    { name: 'zero' },
  ];
  const input = { rawData, mapping: undefined, otherName: '其他' };
  assert.equal(presentBar(chart, {}, input), chart);

  const shown = presentBar(
    chart,
    { ...readChartDisplay({ displayLimit: 3 }), sortByValue: true },
    input,
  );
  assert.notEqual(shown, chart);
  assert.deepEqual(shown.categories, ['top', 'mid', 'zero', '其他']);
  assert.deepEqual(shown.series?.map((series) => series.data), [
    [2, 1, 0, null],
    [4, 1, 0, null],
  ]);
  assert.deepEqual(chart.categories, ['mid', 'empty', 'top', 'zero']);
  assert.deepEqual(chart.series?.[0]?.data, [1, null, 2, 0]);
  assert.deepEqual(chart.series?.[1]?.data, [1, null, 4, 0]);
});

test('bar points follow kept categories and a mismatched list is dropped', () => {
  const aligned = {
    categories: ['low', 'high'],
    values: [1, 5],
    points: [{ raw: 'low' }, { raw: 'high' }],
  };
  const shown = presentBar(
    aligned,
    { ...readChartDisplay({ displayLimit: 1 }), sortByValue: true },
    {
      rawData: [{ name: 'low' }, { name: 'high' }],
      mapping: undefined,
      otherName: '其他',
    },
  );
  assert.deepEqual(shown.categories, ['high', '其他']);
  assert.deepEqual(shown.values, [5, 1]);
  assert.deepEqual(shown.points, [{ raw: 'high' }]);

  const mismatched = presentBar(
    {
      categories: ['low', 'high'],
      values: [1, 5],
      points: [{ raw: 'only' }],
    },
    { sortByValue: true },
    {
      rawData: [{ name: 'low' }, { name: 'high' }],
      mapping: undefined,
      otherName: '其他',
    },
  );
  assert.equal('points' in mismatched, false);
  assert.deepEqual(mismatched.categories, ['high', 'low']);
});

test('chartDisplayPatch clears sort for topN and clears both for line', () => {
  assert.deepEqual(
    chartDisplayPatch({ chartType: 'topN', displayLimit: 3, sortByValue: true }),
    { displayLimit: 3, sortByValue: undefined },
  );
  assert.deepEqual(
    chartDisplayPatch({ chartType: 'line', displayLimit: 3, sortByValue: true }),
    { displayLimit: undefined, sortByValue: undefined },
  );
  assert.deepEqual(
    chartDisplayPatch({ chartType: 'pie', displayLimit: 2, sortByValue: true }),
    { displayLimit: 2, sortByValue: true },
  );
  assert.deepEqual(
    chartDisplayPatch({ chartType: 'bar', displayLimit: '4', sortByValue: false }),
    { displayLimit: undefined, sortByValue: undefined },
  );
});
