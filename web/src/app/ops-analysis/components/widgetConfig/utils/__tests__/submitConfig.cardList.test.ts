import assert from 'node:assert/strict';
import test from 'node:test';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  buildWidgetSubmitConfig,
  mergeSanitizedWidgetValueConfig,
  omitForeignChartTypeFields,
} from '../submitConfig';

const baseInput = {
  chartType: 'cardList',
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: ['health_score'],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [
    {
      id: 'col-1',
      key: 'alarm_name',
      title: '告警',
      visible: true,
      order: 0,
    },
  ],
  filterFields: [],
  actions: [],
};

test('cardList submit persists mapped slots and drops foreign chart fields', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      dataSource: 7,
      descriptionField: 'should-not-leak',
      selectedFields: ['health_score'],
      eventTimeline: { sortOrder: 'desc' },
      radar: { min: 0, max: 100, indicators: [{ key: 'cpu' }] },
      cardList: {
        titleField: ' alarm_name ',
        descriptionField: ' summary ',
        leading: { type: 'none', field: 'ignored' },
        badgeField: 'severity',
        trailingPrimaryField: 'duration',
        trailingSecondaryField: '  ',
        layout: 'list',
      },
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.cardList, {
    titleField: 'alarm_name',
    descriptionField: 'summary',
    badgeField: 'severity',
    trailingPrimaryField: 'duration',
  });
  assert.equal('descriptionField' in (result.config || {}), false);
  assert.equal('selectedFields' in (result.config || {}), false);
  assert.equal('eventTimeline' in (result.config || {}), false);
  assert.equal('radar' in (result.config || {}), false);
  assert.equal('tableConfig' in (result.config || {}), false);
  assert.equal('layout' in (result.config?.cardList || {}), false);
});

test('cardList submit keeps index leading and grid layout', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        leading: { type: 'index', field: 'nope' },
        layout: 'grid',
      },
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.cardList, {
    titleField: 'title',
    leading: { type: 'index' },
    layout: 'grid',
  });
});

test('cardList submit keeps field leading when field is present', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        leading: { type: 'field', field: '  seq  ' },
      },
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.cardList?.leading, {
    type: 'field',
    field: 'seq',
  });
});

test('cardList submit persists leading and badge accent styles', () => {
  const mappings = [
    {
      type: 'value' as const,
      value: 'P1',
      result: { text: '紧急', color: '#ff0000' },
    },
  ];
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        leading: {
          type: 'index',
          style: {
            displayType: 'text',
            valueMappings: mappings,
          },
        },
        badgeField: 'severity',
        badgeStyle: {
          displayType: 'colorBackground',
          valueMappings: mappings,
        },
      },
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.cardList?.leading, {
    type: 'index',
    style: { valueMappings: mappings },
  });
  assert.deepEqual(result.config?.cardList?.badgeStyle, {
    displayType: 'colorBackground',
    valueMappings: mappings,
  });
});

test('cardList submit drops badgeStyle when badge field is empty', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        badgeField: '  ',
        badgeStyle: {
          displayType: 'colorBackground',
          valueMappings: [
            {
              type: 'value',
              value: 'P1',
              result: { color: '#f00' },
            },
          ],
        },
      },
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.cardList, { titleField: 'title' });
});

test('cardList submit fails when title is missing', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: '   ',
      },
    },
  });

  assert.equal(result.error, 'cardListTitleRequired');
  assert.equal(result.config, undefined);
});

test('cardList submit fails when field leading has empty field', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        leading: { type: 'field', field: '  ' },
      },
    },
  });

  assert.equal(result.error, 'cardListLeadingFieldRequired');
  assert.equal(result.config, undefined);
});

test('cardList chart type drops foreign persisted fields on screen merge', () => {
  const sanitized = omitForeignChartTypeFields(
    {
      chartType: 'cardList',
      cardList: { titleField: 'title' },
      tableConfig: { columns: [] },
      actions: [{ columnKey: 'op', text: '打开' }],
      eventTimeline: { sortOrder: 'desc' },
      radar: { min: 0, max: 100, indicators: [] },
      selectedFields: ['cpu'],
      descriptionField: 'note',
      topNLabelField: 'name',
      topNValueField: 'value',
    },
    'cardList',
  );

  assert.deepEqual(sanitized.cardList, { titleField: 'title' });
  assert.equal('tableConfig' in sanitized, false);
  assert.equal('actions' in sanitized, false);
  assert.equal('eventTimeline' in sanitized, false);
  assert.equal('radar' in sanitized, false);
  assert.equal('selectedFields' in sanitized, false);
  assert.equal('descriptionField' in sanitized, false);
});

test('cardList submit still omits list layout and empty optional slots', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        leading: { type: 'none' },
        badgeField: undefined,
        trailingPrimaryField: undefined,
        trailingSecondaryField: undefined,
        layout: 'list',
      },
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.cardList, { titleField: 'title' });
});

test('leaving cardList drops persisted cardList config', () => {
  const sanitized = omitForeignChartTypeFields(
    {
      chartType: 'table',
      cardList: { titleField: 'title' },
      tableConfig: { columns: [] },
    },
    'table',
  );

  assert.equal('cardList' in sanitized, false);
  assert.deepEqual(sanitized.tableConfig, { columns: [] });
});

test('dashboard edit merge drops foreign chart fields when switching to cardList', () => {
  const existing: ValueConfig = {
    dataSource: 1,
    chartType: 'radar',
    filterBindings: { region: true },
    radar: { min: 0, max: 100, indicators: [{ key: 'cpu' }] },
    eventTimeline: { sortOrder: 'desc' },
    tableConfig: { columns: [] },
    selectedFields: ['cpu'],
  };
  const submitted: ValueConfig = {
    dataSource: 1,
    chartType: 'cardList',
    filterBindings: { region: true },
    cardList: { titleField: 'name' },
    tableConfig: undefined,
    selectedFields: undefined,
    radar: undefined,
    eventTimeline: undefined,
  };

  const persisted = mergeSanitizedWidgetValueConfig(
    existing,
    submitted,
    'cardList',
  );

  assert.equal(persisted.chartType, 'cardList');
  assert.deepEqual(persisted.cardList, { titleField: 'name' });
  assert.equal(persisted.dataSource, 1);
  assert.deepEqual(persisted.filterBindings, { region: true });
  assert.equal('radar' in persisted, false);
  assert.equal('eventTimeline' in persisted, false);
  assert.equal('tableConfig' in persisted, false);
  assert.equal('selectedFields' in persisted, false);
});

test('dashboard edit merge drops cardList when switching to another chart type', () => {
  const existing: ValueConfig = {
    dataSource: 3,
    chartType: 'cardList',
    cardList: {
      titleField: 'name',
      badgeField: 'severity',
      layout: 'grid',
    },
    filterBindings: { env: true },
  };

  const toRadar = mergeSanitizedWidgetValueConfig(
    existing,
    {
      dataSource: 3,
      chartType: 'radar',
      filterBindings: { env: true },
      radar: { min: 0, max: 100, indicators: [{ key: 'cpu' }] },
      cardList: undefined,
    },
    'radar',
  );
  assert.equal(toRadar.chartType, 'radar');
  assert.deepEqual(toRadar.radar, {
    min: 0,
    max: 100,
    indicators: [{ key: 'cpu' }],
  });
  assert.equal(toRadar.dataSource, 3);
  assert.deepEqual(toRadar.filterBindings, { env: true });
  assert.equal('cardList' in toRadar, false);

  const toTable = mergeSanitizedWidgetValueConfig(
    existing,
    {
      dataSource: 3,
      chartType: 'table',
      filterBindings: { env: true },
      tableConfig: {
        columns: [{ key: 'name', title: '名称', visible: true, order: 0 }],
      },
      cardList: undefined,
    },
    'table',
  );
  assert.equal(toTable.chartType, 'table');
  assert.deepEqual(toTable.tableConfig, {
    columns: [{ key: 'name', title: '名称', visible: true, order: 0 }],
  });
  assert.equal('cardList' in toTable, false);
});
