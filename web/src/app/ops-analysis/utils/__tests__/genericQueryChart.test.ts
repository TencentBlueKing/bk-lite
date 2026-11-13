import assert from 'node:assert/strict';
import test from 'node:test';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { extractComparableValue } from '@/app/ops-analysis/utils/compareQuery';
import { localizeOptionLoadError } from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import { parseTableLikeData } from '@/app/ops-analysis/utils/tableLikeData';

const nameValueRows = [
  { name: 'Linux', value: 3 },
  { name: 'Windows', value: 0 },
];

test('name and value rows render without field mapping', () => {
  const bar = ChartDataTransformer.transformToLineBarData(nameValueRows);
  const pie = ChartDataTransformer.transformToPieData(nameValueRows);
  assert.deepEqual(bar.categories, ['Linux', 'Windows']);
  assert.deepEqual(bar.values, [3, 0]);
  assert.equal(ChartDataTransformer.validateLineBarData(nameValueRows, '数据格式不匹配').isValid, true);
  assert.equal(ChartDataTransformer.validatePieData(nameValueRows, '数据格式不匹配').isValid, true);
  assert.deepEqual(pie.map((item) => item.value), [3, 0]);
  const wrapped = { items: nameValueRows, count: 2 };
  assert.equal(ChartDataTransformer.validatePieData(wrapped, '数据格式不匹配').isValid, false);
});

test('an empty items list stays empty instead of a format error', () => {
  const emptyCategory = { items: [] };
  assert.equal(ChartDataTransformer.isStructurallyEmpty(emptyCategory), true);
  assert.equal(ChartDataTransformer.validateLineBarData(emptyCategory, '数据格式不匹配').isValid, true);
  assert.equal(ChartDataTransformer.validatePieData(emptyCategory, '数据格式不匹配').isValid, true);
  assert.deepEqual(ChartDataTransformer.transformToLineBarData(emptyCategory).categories, []);
  const table = parseTableLikeData({
    items: [],
    count: 0,
    page: 1,
    page_size: 20,
  }, { current: 1, pageSize: 20 });
  assert.deepEqual(table.rows, []);
  assert.equal(table.pagination.total, 0);
});

test('metric series map coerces a missing point to zero and treats an empty map as empty', () => {
  const chart = ChartDataTransformer.transformToLineBarData({
    host: [
      ['2026-01-01T00:00:00Z', null],
      ['2026-01-01T00:01:00Z', 0],
      ['2026-01-01T00:02:00Z', 1],
    ],
  });
  assert.deepEqual([...(chart.series?.[0]?.data ?? [])], [0, 0, 1]);
  assert.equal(ChartDataTransformer.isStructurallyEmpty({}), true);
  assert.equal(ChartDataTransformer.validateLineBarData({}, '数据格式不匹配').isValid, true);
});

test('a selected measure stays null instead of becoming zero', () => {
  const chart = ChartDataTransformer.transformToLineBarData({
    structure: 'table',
    status: 'missing',
    items: [{ instance_name: 'host', value: null, status: 'missing' }],
  }, { dimensionField: 'instance_name', valueField: 'value' });
  assert.deepEqual(chart.values, [null]);
});

test('legacy datasources still coerce null to zero and reject unmapped objects', () => {
  const legacy = ChartDataTransformer.transformToLineBarData({
    cpu: [
      ['2026-01-01T00:00:00Z', null],
      ['2026-01-01T00:01:00Z', 2],
    ],
  });
  assert.deepEqual([...(legacy.series?.[0]?.data ?? [])].sort(), [0, 2]);
  const unmapped = ChartDataTransformer.validateLineBarData(
    { total: 1, unit: '个' },
    '数据格式不匹配',
  );
  assert.equal(unmapped.isValid, false);
});

test('model count and instance total zeros stay visible instead of an empty state', () => {
  for (const aggregation of ['模型计数', '实例总数']) {
    const payload = {
      structure: 'value',
      value: 0,
      unit: '个',
      aggregation,
    };
    assert.equal(extractComparableValue(payload), 0);
    assert.equal(ChartDataTransformer.isStructurallyEmpty(payload), false);
    assert.equal(Object.keys(payload).includes('title'), false);
  }
  const missing = {
    value: null,
    unit: '',
    aggregation: 'sum(cpu)',
  };
  assert.equal(extractComparableValue(missing), null);
  assert.equal(ChartDataTransformer.isStructurallyEmpty(missing), false);
});

test('single value reads the value envelope and keeps zero distinct from empty', () => {
  assert.equal(extractComparableValue({
    structure: 'value',
    value: 0,
    unit: '个',
    aggregation: '实例计数',
  }), 0);
  assert.equal(extractComparableValue({
    structure: 'value',
    value: null,
    unit: '',
    aggregation: 'sum(cpu)',
  }), null);
});

test('option load errors stay in Chinese', () => {
  const zh: Record<string, string> = {
    'dashboard.optionPageLimitExceeded': '选项超过分页上限，无法继续加载',
    'dashboard.optionPageEndedEarly': '选项分页在总数到达前结束',
  };
  assert.equal(
    localizeOptionLoadError('option page limit exceeded', (key) => zh[key]),
    '选项超过分页上限，无法继续加载',
  );
  assert.equal(
    localizeOptionLoadError('option page ended before count', (key) => zh[key]),
    '选项分页在总数到达前结束',
  );
});
