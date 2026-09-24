import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

const baseInput = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [] as string[],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

test('line submit omits untouched dimension and value fields', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'line',
    values: {
      name: '折线',
      chartType: 'line',
    },
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.dimensionField, undefined);
  assert.equal(result.config?.valueField, undefined);
});

test('bar submit persists dimension and value after the user selects them', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'bar',
    values: {
      name: '柱状',
      chartType: 'bar',
      dimensionField: 'src_ip',
      valueField: 'value',
    },
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.dimensionField, 'src_ip');
  assert.equal(result.config?.valueField, 'value');
});

test('line submit rejects a dimension without a value', () => {
  const saved = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'line',
    values: {
      name: '折线',
      chartType: 'line',
      dimensionField: 'src_ip',
    },
  });
  const preview = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'line',
    values: {
      name: '折线',
      chartType: 'line',
      dimensionField: 'src_ip',
    },
    forPreview: true,
  });

  assert.equal(saved.error, 'chartRoleFieldPairRequired');
  assert.equal(saved.config, undefined);
  assert.equal(preview.error, undefined);
  assert.equal(preview.config?.dimensionField, 'src_ip');
  assert.equal(preview.config?.valueField, undefined);
});

test('pie submit allows saving without field roles', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'pie',
    values: {
      name: '饼图',
      chartType: 'pie',
    },
  });

  assert.equal(result.error, undefined);
});

test('multi value submit rejects missing roles and allows them for preview', () => {
  const values = {
    name: '多值',
    chartType: 'multiValue',
  };
  const saved = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'multiValue',
    values,
  });
  const preview = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'multiValue',
    values,
    forPreview: true,
  });

  assert.equal(saved.error, 'chartRoleFieldsRequired');
  assert.equal(saved.config, undefined);
  assert.equal(preview.error, undefined);
});

test('multi value submit persists both roles', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'multiValue',
    values: {
      name: '多值',
      chartType: 'multiValue',
      multiValueLabelField: 'host',
      multiValueValueField: 'status',
    },
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.multiValueLabelField, 'host');
  assert.equal(result.config?.multiValueValueField, 'status');
});

test('event timeline submit requires time and title and keeps optional roles empty', () => {
  const missing = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'eventTimeline',
    values: {
      name: '事件',
      chartType: 'eventTimeline',
      eventTimeline: { sortOrder: 'asc' },
    },
  });
  const saved = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'eventTimeline',
    values: {
      name: '事件',
      chartType: 'eventTimeline',
      eventTimeline: {
        sortOrder: 'asc',
        timeField: 'occurred_at',
        titleField: 'headline',
        descriptionField: 'note',
      },
    },
  });

  assert.equal(missing.error, 'chartRoleFieldsRequired');
  assert.equal(saved.error, undefined);
  assert.deepEqual(saved.config?.eventTimeline, {
    sortOrder: 'asc',
    timeField: 'occurred_at',
    titleField: 'headline',
    descriptionField: 'note',
  });
});

test('radar array roles are required only when indicators are empty', () => {
  const missing = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'radar',
    values: {
      name: '雷达',
      chartType: 'radar',
      radar: { min: 0, max: 100, indicators: [] },
    },
  });
  const withIndicators = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'radar',
    values: {
      name: '雷达',
      chartType: 'radar',
      radar: {
        min: 0,
        max: 100,
        indicators: [{ key: 'cpu', label: 'CPU' }],
      },
    },
  });
  const arrayMode = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'radar',
    values: {
      name: '雷达',
      chartType: 'radar',
      radar: {
        min: 0,
        max: 100,
        indicators: [],
        arrayNameField: 'metric',
        arrayValueField: 'reading',
      },
    },
  });

  assert.equal(missing.error, 'chartRoleFieldsRequired');
  assert.equal(withIndicators.error, undefined);
  assert.equal(arrayMode.error, undefined);
  assert.equal(arrayMode.config?.radar?.arrayNameField, 'metric');
  assert.equal(arrayMode.config?.radar?.arrayValueField, 'reading');
});
