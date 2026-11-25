import assert from 'node:assert/strict';
import test from 'node:test';
import {
  applyChartDisplay,
  chartDisplayControls,
  CHART_DISPLAY_KEYS,
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

test('read keeps legacy limit and sort without chartType and hides unowned switches', () => {
  assert.equal(readChartDisplay({ displayLimit: 2, stackBars: true }).displayLimit, 2);
  assert.equal(readChartDisplay({ displayLimit: 2, stackBars: true }).stackBars, undefined);
  assert.equal(
    readChartDisplay({ chartType: 'line', stackBars: true, displayLimit: 4 }).stackBars,
    undefined,
  );
  assert.equal(
    readChartDisplay({ chartType: 'line', stackBars: true, displayLimit: 4 }).displayLimit,
    undefined,
  );
  assert.equal(readChartDisplay({ chartType: 'eventTable', autoScroll: true }).autoScroll, true);
  assert.equal(readChartDisplay({ chartType: 'cardList', autoScroll: true }).autoScroll, true);
  assert.equal(readChartDisplay({ chartType: 'multiValue', autoScroll: true }).autoScroll, true);
  assert.equal(readChartDisplay({ chartType: 'pie', autoScroll: true }).autoScroll, undefined);
  assert.equal(readChartDisplay({ chartType: 'bar', stackBars: true }).stackBars, true);
  assert.equal(readChartDisplay({ chartType: 'table', autoScroll: true }).autoScroll, true);
  assert.equal(readChartDisplay({ chartType: 'table', autoScroll: 'true' }).autoScroll, undefined);
  assert.equal(readChartDisplay({ chartType: 'table', scrollSeconds: 1.5 }).scrollSeconds, 1.5);
  assert.equal(readChartDisplay({ chartType: 'eventTable', scrollSeconds: 4 }).scrollSeconds, 4);
  assert.equal(readChartDisplay({ chartType: 'table', scrollSeconds: 0 }).scrollSeconds, undefined);
  assert.equal(readChartDisplay({ chartType: 'table', scrollSeconds: '2' }).scrollSeconds, undefined);
  assert.equal(readChartDisplay({ chartType: 'bar', scrollSeconds: 3 }).scrollSeconds, undefined);
  assert.equal(readChartDisplay({ chartType: 'bar', sortByValue: 1 }).sortByValue, undefined);
});

test('reference lines keep finite numbers and drop invalid rows', () => {
  const display = readChartDisplay({
    chartType: 'line',
    referenceLines: [
      { name: ' baseline ', value: 0 },
      { name: 'low', value: -2 },
      { name: 'dup', value: 1 },
      { name: 'dup', value: 1 },
      { name: '   ', value: 4 },
      { name: 'text', value: '0' },
      { name: 'nan', value: Number.NaN },
      { name: 3, value: 3 },
      { value: 8 },
      null,
      { name: 'inf', value: Infinity },
      { name: 'alert', value: 80, color: '#d97706' },
      { name: 'named', value: 3, color: 'red' },
    ],
  });
  assert.deepEqual(display.referenceLines, [
    { name: 'baseline', value: 0 },
    { name: 'low', value: -2 },
    { name: 'dup', value: 1 },
    { name: 'dup', value: 1 },
    { name: 'alert', value: 80, color: '#d97706' },
    { name: 'named', value: 3 },
  ]);
  assert.equal(readChartDisplay({ chartType: 'bar', referenceLines: [] }).referenceLines, undefined);
  assert.equal(
    readChartDisplay({ chartType: 'pie', referenceLines: [{ name: 'baseline', value: 0 }] }).referenceLines,
    undefined,
  );
});

test('chart display controls come from the slot catalog', () => {
  assert.deepEqual(CHART_DISPLAY_KEYS, [
    'displayLimit',
    'sortByValue',
    'stackBars',
    'referenceLines',
    'autoScroll',
    'scrollSeconds',
  ]);
  assert.deepEqual(chartDisplayControls('topN'), {
    limit: true,
    sort: false,
    stackBars: false,
    referenceLines: false,
    autoScroll: true,
  });
  assert.deepEqual(chartDisplayControls('pie'), {
    limit: true,
    sort: true,
    stackBars: false,
    referenceLines: false,
    autoScroll: false,
  });
  assert.deepEqual(chartDisplayControls('line'), {
    limit: false,
    sort: false,
    stackBars: false,
    referenceLines: true,
    autoScroll: false,
  });
  assert.deepEqual(chartDisplayControls('eventTable'), {
    limit: false,
    sort: false,
    stackBars: false,
    referenceLines: false,
    autoScroll: true,
  });
  assert.equal(chartDisplayControls('cardList').autoScroll, true);
  assert.equal(chartDisplayControls('multiValue').autoScroll, true);
  assert.deepEqual(chartDisplayControls(undefined), chartDisplayControls('gauge'));
});

test('applyChartDisplay writes owned slots and deletes the rest', () => {
  const topN: Record<string, unknown> = { sortByValue: true, stackBars: true, thresholdColors: [{ value: '1' }] };
  applyChartDisplay(topN, { chartType: 'topN', displayLimit: 3, sortByValue: true, stackBars: true });
  assert.deepEqual(topN, { displayLimit: 3, thresholdColors: [{ value: '1' }] });

  const line: Record<string, unknown> = {
    displayLimit: 3,
    sortByValue: true,
    stackBars: true,
    thresholdColors: [{ value: '9', color: 'red' }],
  };
  applyChartDisplay(line, {
    chartType: 'line',
    displayLimit: 3,
    sortByValue: true,
    stackBars: true,
    referenceLines: [{ name: 'baseline', value: 0 }],
  });
  assert.deepEqual(line, {
    referenceLines: [{ name: 'baseline', value: 0 }],
    thresholdColors: [{ value: '9', color: 'red' }],
  });

  const pie: Record<string, unknown> = { stackBars: true };
  applyChartDisplay(pie, { chartType: 'pie', displayLimit: 2, sortByValue: true, stackBars: true });
  assert.deepEqual(pie, { displayLimit: 2, sortByValue: true });

  const bar: Record<string, unknown> = {
    displayLimit: 4,
    sortByValue: true,
    stackBars: true,
    referenceLines: [{ name: 'baseline', value: 0 }],
  };
  applyChartDisplay(bar, {
    chartType: 'bar',
    displayLimit: '4',
    sortByValue: false,
    stackBars: false,
    referenceLines: [],
  });
  assert.deepEqual(bar, {});

  const blankName: Record<string, unknown> = {
    referenceLines: [{ name: 'baseline', value: 0 }],
    stackBars: true,
  };
  applyChartDisplay(blankName, {
    chartType: 'bar',
    stackBars: false,
    referenceLines: [{ name: '  ', value: 0 }],
  });
  assert.equal('referenceLines' in blankName, false);
  assert.equal('stackBars' in blankName, false);

  applyChartDisplay(line, {
    chartType: 'line',
    referenceLines: [{ name: 'baseline', value: 0 }],
  });
  assert.deepEqual(line.referenceLines, [{ name: 'baseline', value: 0 }]);

  const eventTable: Record<string, unknown> = { scrollSeconds: 9 };
  applyChartDisplay(eventTable, {
    chartType: 'eventTable',
    autoScroll: true,
    scrollSeconds: 1.5,
  });
  assert.deepEqual(eventTable, { autoScroll: true, scrollSeconds: 1.5 });

  const barSpeed: Record<string, unknown> = { autoScroll: true, scrollSeconds: 4 };
  applyChartDisplay(barSpeed, { chartType: 'bar', autoScroll: true, scrollSeconds: 4 });
  assert.deepEqual(barSpeed, {});
});
