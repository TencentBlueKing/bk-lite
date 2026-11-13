import assert from 'node:assert/strict';
import test from 'node:test';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { extractComparableValue } from '@/app/ops-analysis/utils/compareQuery';
import { localizeOptionLoadError } from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import { narrowInputConfigForQueryObject } from '@/app/ops-analysis/utils/queryObjectOptions';
import { parseTableLikeData } from '@/app/ops-analysis/utils/tableLikeData';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';

const category = {
  structure: 'category',
  status: 'ok',
  items: [
    { name: 'Linux', value: 3 },
    { name: 'Windows', value: 0 },
  ],
  unit: '个',
  aggregation: '按 os_type 计数',
};

const emptyCategory = {
  structure: 'category',
  status: 'empty',
  items: [],
  unit: '个',
  aggregation: '按 os_type 计数',
};

test('category envelope renders on bar and pie without field mapping', () => {
  const bar = ChartDataTransformer.transformToLineBarData(category);
  const pie = ChartDataTransformer.transformToPieData(category);
  assert.deepEqual(bar.categories, ['Linux', 'Windows']);
  assert.deepEqual(bar.values, [3, 0]);
  assert.equal(ChartDataTransformer.validateLineBarData(category, '数据格式不匹配').isValid, true);
  assert.equal(ChartDataTransformer.validatePieData(category, '数据格式不匹配').isValid, true);
  assert.deepEqual(pie.map((item) => item.value), [3, 0]);
});

test('legal empty category and table envelopes stay empty instead of format errors', () => {
  assert.equal(ChartDataTransformer.isStructurallyEmpty(emptyCategory), true);
  assert.equal(ChartDataTransformer.validateLineBarData(emptyCategory, '数据格式不匹配').isValid, true);
  assert.equal(ChartDataTransformer.validatePieData(emptyCategory, '数据格式不匹配').isValid, true);
  assert.deepEqual(ChartDataTransformer.transformToLineBarData(emptyCategory).categories, []);
  const table = parseTableLikeData({
    structure: 'table',
    status: 'empty',
    items: [],
    count: 0,
    page: 1,
    page_size: 20,
  }, { current: 1, pageSize: 20 });
  assert.deepEqual(table.rows, []);
  assert.equal(table.pagination.total, 0);
});

test('metric series keeps missing points null and treats all-missing as empty', () => {
  const partial = {
    structure: 'series',
    status: 'ok',
    series: {
      host: [
        { name: '2026-01-01T00:00:00+00:00', value: 1 },
        { name: '2026-01-01T00:01:00+00:00', value: null, status: 'missing' },
        { name: '2026-01-01T00:02:00+00:00', value: 0 },
      ],
    },
  };
  const chart = ChartDataTransformer.transformToLineBarData(partial);
  const points = chart.series?.[0]?.data ?? [];
  assert.deepEqual(points.filter((value) => value === null), [null]);
  assert.deepEqual(points.filter((value) => value === 0), [0]);
  assert.deepEqual(points.filter((value) => value === 1), [1]);
  assert.equal(ChartDataTransformer.validateLineBarData(partial, '数据格式不匹配').isValid, true);

  const missing = {
    structure: 'series',
    status: 'missing',
    series: {},
    unit: '%',
    aggregation: 'avg',
  };
  assert.equal(ChartDataTransformer.validateLineBarData(missing, '数据格式不匹配').isValid, true);
  assert.deepEqual(ChartDataTransformer.transformToLineBarData(missing).categories, []);
});

test('role-bound tables keep a missing measure null', () => {
  const chart = ChartDataTransformer.transformToLineBarData({
    structure: 'table',
    status: 'missing',
    fields: [
      { key: 'instance_name', role: 'dimension' },
      { key: 'value', role: 'measure' },
    ],
    items: [{ instance_name: 'host', value: null, status: 'missing' }],
  });
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
      status: 'ok',
      value: 0,
      unit: '个',
      aggregation,
    };
    assert.equal(extractComparableValue(payload), 0);
    assert.equal(ChartDataTransformer.isStructurallyEmpty(payload), false);
    assert.equal(Object.keys(payload).includes('title'), false);
  }
  const missing = {
    structure: 'value',
    status: 'empty',
    value: null,
    unit: '',
    aggregation: 'sum(cpu)',
  };
  assert.equal(extractComparableValue(missing), null);
  assert.equal(ChartDataTransformer.isStructurallyEmpty(missing), true);
});

test('single value reads the value envelope and keeps zero distinct from empty', () => {
  assert.equal(extractComparableValue({
    structure: 'value',
    status: 'ok',
    value: 0,
    unit: '个',
    aggregation: '实例计数',
  }), 0);
  assert.equal(extractComparableValue({
    structure: 'value',
    status: 'empty',
    value: null,
    unit: '',
    aggregation: 'sum(cpu)',
  }), null);
});

test('option load errors and query-object dropdowns are narrowed in Chinese', () => {
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

  const config: InputControlConfig = {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: [
        { label: '级别', value: 'level' },
        { label: '来源名称', value: 'source_name', query_objects: ['alert'] },
        { label: '来源标识', value: 'source_id', query_objects: ['event'] },
      ],
    },
  };
  const alertOptions = narrowInputConfigForQueryObject(config, 'alert');
  const eventOptions = narrowInputConfigForQueryObject(config, 'event');
  assert.ok(alertOptions && alertOptions.control === 'select' && alertOptions.optionsSource.type === 'static');
  assert.ok(eventOptions && eventOptions.control === 'select' && eventOptions.optionsSource.type === 'static');
  if (alertOptions?.control === 'select' && alertOptions.optionsSource.type === 'static') {
    assert.deepEqual(alertOptions.optionsSource.staticItems.map((item) => item.value), ['level', 'source_name']);
  }
  if (eventOptions?.control === 'select' && eventOptions.optionsSource.type === 'static') {
    assert.deepEqual(eventOptions.optionsSource.staticItems.map((item) => item.value), ['level', 'source_id']);
  }
});
