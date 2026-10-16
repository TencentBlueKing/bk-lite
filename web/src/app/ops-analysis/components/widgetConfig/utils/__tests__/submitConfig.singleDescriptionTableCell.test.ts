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
};

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
      {
        id: 'c3',
        key: '__actions__',
        title: '操作',
        visible: true,
        order: 2,
        columnType: 'actions',
      },
    ],
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.tableConfig?.columns?.length, 2);
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

test('table submit drops leftover action columns and keeps a title-only link', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    values: {
      name: '主机表',
      chartType: 'table',
      interaction: {
        kind: 'data',
        name: '查看',
        url: '/ops/host',
        openMode: 'sameTab',
      },
    },
    chartType: 'table',
    displayColumns: [
      {
        id: 'c1',
        key: 'host',
        title: '主机',
        visible: true,
        order: 0,
      },
      {
        id: 'c2',
        key: '__actions__',
        title: '操作',
        visible: true,
        order: 1,
        columnType: 'actions',
      },
    ],
  });
  assert.equal(result.error, undefined);
  assert.deepEqual(
    result.config?.tableConfig?.columns?.map((column) => column.columnType),
    [undefined],
  );
  assert.equal(result.config?.tableConfig?.columns?.[0]?.key, 'host');

  const text = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '说明',
      chartType: 'text',
      interaction: {
        kind: 'data',
        name: '详情',
        url: '/ops/text',
        openMode: 'newTab',
      },
    },
    chartType: 'text',
  });
  assert.equal(text.config?.interaction?.kind, 'title');
  assert.equal(text.config?.interaction?.url, '/ops/text');

  const cleared = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '折线',
      chartType: 'line',
      interaction: {
        kind: 'none',
        name: '详情',
        url: '/ops',
        openMode: 'newTab',
      },
    },
    chartType: 'line',
  });
  assert.equal(cleared.error, undefined);
  assert.equal(cleared.config?.interaction, undefined);
  assert.equal('actions' in (cleared.config ?? {}), false);
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
    width: 180,
  });
});
