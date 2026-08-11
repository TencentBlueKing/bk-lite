import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

const baseInput = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: ['health_score'],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
} as const;

test('single submit persists optional descriptionField', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      descriptionField: 'health_note',
      compare: false,
    },
    chartType: 'single',
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.descriptionField, 'health_note');
});

test('single submit omits blank descriptionField', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      descriptionField: '   ',
      compare: false,
    },
    chartType: 'single',
  });

  assert.equal(result.error, undefined);
  assert.equal('descriptionField' in (result.config || {}), false);
});

test('table submit persists column cell style fields', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    values: {
      name: '健康矩阵',
      chartType: 'table',
    },
    chartType: 'table',
    displayColumns: [
      {
        id: 'c1',
        key: 'health_set',
        title: '健康集',
        visible: true,
        order: 0,
        cellType: 'colorBackground',
        valueMappings: [
          {
            type: 'value',
            value: '正常',
            result: { color: '#67a567' },
          },
        ],
        cellThresholdColors: [{ value: '80', color: '#fd666d' }],
      },
      {
        id: 'c2',
        key: 'node',
        title: '节点',
        visible: true,
        order: 1,
      },
    ],
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.tableConfig?.columns?.[0], {
    key: 'health_set',
    title: '健康集',
    visible: true,
    order: 0,
    columnType: undefined,
    cellType: 'colorBackground',
    valueMappings: [
      {
        type: 'value',
        value: '正常',
        result: { color: '#67a567' },
      },
    ],
    cellThresholdColors: [{ value: '80', color: '#fd666d' }],
  });
  assert.equal(
    'cellType' in (result.config?.tableConfig?.columns?.[1] || {}),
    false,
  );
  assert.equal(
    'valueMappings' in (result.config?.tableConfig?.columns?.[1] || {}),
    false,
  );
});

test('eventTable submit strips table-only cell style fields and keeps column config', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    values: {
      name: '事件列表',
      chartType: 'eventTable',
    },
    chartType: 'eventTable',
    displayColumns: [
      {
        id: 'c1',
        key: 'status',
        title: '状态',
        visible: true,
        order: 0,
        width: 180,
        columnType: 'data',
        cellType: 'colorBackground',
        valueMappings: [
          {
            type: 'value',
            value: 'failed',
            result: { text: '失败', color: '#fd666d' },
          },
        ],
        cellThresholdColors: [{ value: '80', color: '#fd666d' }],
      },
    ],
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.tableConfig?.columns?.[0], {
    key: 'status',
    title: '状态',
    visible: true,
    order: 0,
    columnType: 'data',
  });
});
