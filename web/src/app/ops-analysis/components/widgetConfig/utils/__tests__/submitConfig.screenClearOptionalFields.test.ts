import assert from 'node:assert/strict';
import test from 'node:test';
import type { ValueConfig, WidgetConfig } from '@/app/ops-analysis/types/dashBoard';
import { resolveSingleDescriptionText } from '@/app/ops-analysis/utils/singleDescription';
import { applyOpenedValueConfigToFormValues } from '../widgetConfigFormState';
import {
  buildWidgetSubmitConfig,
  mergeSanitizedWidgetValueConfig,
  mergeScreenWidgetValueConfig,
} from '../submitConfig';

const baseInput = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: ['value'],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

const mergeLikeScreen = (
  existing: ValueConfig,
  submitted: WidgetConfig,
  chartType: string,
): ValueConfig => mergeScreenWidgetValueConfig(existing, submitted, chartType);

const persisted = (valueConfig: ValueConfig) =>
  JSON.parse(JSON.stringify(valueConfig)) as ValueConfig;

test('screen save drops a cleared single descriptionField', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      descriptionField: '   ',
      compare: false,
    },
    chartType: 'single',
  });
  assert.equal(submitted.error, undefined);
  assert.ok(submitted.config);

  const merged = mergeLikeScreen(
    {
      chartType: 'single',
      selectedFields: ['value'],
      descriptionField: 'note',
      dataSource: 7,
    },
    submitted.config,
    'single',
  );
  const saved = persisted(merged);

  assert.equal('descriptionField' in saved, false);
  assert.equal(
    resolveSingleDescriptionText({ note: '仍显示的说明' }, saved.descriptionField),
    undefined,
  );

  const reopened = applyOpenedValueConfigToFormValues(
    { name: '总体健康分', chartType: 'single' },
    saved,
    undefined,
  );
  assert.equal(reopened.descriptionField, undefined);
});

test('screen save keeps a selected single descriptionField', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      descriptionField: 'health_note',
      compare: false,
    },
    chartType: 'single',
  });
  const merged = mergeLikeScreen(
    {
      chartType: 'single',
      selectedFields: ['value'],
      descriptionField: 'note',
    },
    submitted.config!,
    'single',
  );

  assert.equal(persisted(merged).descriptionField, 'health_note');
});

test('dashboard merge already clears an omitted single descriptionField on save', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      descriptionField: '',
      compare: false,
    },
    chartType: 'single',
  });
  const merged = mergeSanitizedWidgetValueConfig(
    {
      chartType: 'single',
      selectedFields: ['value'],
      descriptionField: 'note',
    },
    {
      chartType: 'single',
      selectedFields: ['value'],
      descriptionField: submitted.config?.descriptionField,
    },
    'single',
  );

  assert.equal('descriptionField' in persisted(merged), false);
  assert.equal(
    resolveSingleDescriptionText({ note: '说明' }, merged.descriptionField),
    undefined,
  );
});

test('screen save drops pie dimension and value when both are cleared', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'pie',
    values: {
      name: '饼图',
      chartType: 'pie',
      dimensionField: '  ',
      valueField: '',
    },
  });
  assert.equal(submitted.error, undefined);

  const saved = persisted(mergeLikeScreen(
    {
      chartType: 'pie',
      dimensionField: 'host',
      valueField: 'count',
    },
    submitted.config!,
    'pie',
  ));

  assert.equal('dimensionField' in saved, false);
  assert.equal('valueField' in saved, false);
});

test('screen save of a line chart drops leftover pie dimension fields', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'line',
    values: {
      name: '折线',
      chartType: 'line',
      dimensionField: 'host',
      valueField: 'count',
    },
  });
  assert.equal(submitted.error, undefined);
  const saved = persisted(mergeLikeScreen(
    {
      chartType: 'line',
      dimensionField: 'host',
      valueField: 'count',
    },
    submitted.config!,
    'line',
  ));

  assert.equal('dimensionField' in saved, false);
  assert.equal('valueField' in saved, false);
});

test('screen save drops nodeGraph port after leaving service mode', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'nodeGraph',
    values: {
      name: '通信关系图',
      chartType: 'nodeGraph',
      nodeGraphIdentityMode: 'ip',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
      nodeGraphTargetPortField: 'dst_port',
    },
  });
  assert.equal(submitted.error, undefined);

  const saved = persisted(mergeLikeScreen(
    {
      chartType: 'nodeGraph',
      nodeGraphIdentityMode: 'service',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
      nodeGraphTargetPortField: 'dst_port',
    },
    submitted.config!,
    'nodeGraph',
  ));

  assert.equal(saved.nodeGraphIdentityMode, 'ip');
  assert.equal('nodeGraphTargetPortField' in saved, false);
});

test('screen save keeps nodeGraph port while identity stays service', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'nodeGraph',
    values: {
      name: '通信关系图',
      chartType: 'nodeGraph',
      nodeGraphIdentityMode: 'service',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
      nodeGraphTargetPortField: 'dst_port',
    },
  });
  const saved = persisted(mergeLikeScreen(
    {
      chartType: 'nodeGraph',
      nodeGraphIdentityMode: 'service',
      nodeGraphTargetPortField: 'old_port',
    },
    submitted.config!,
    'nodeGraph',
  ));

  assert.equal(saved.nodeGraphTargetPortField, 'dst_port');
});

test('screen save clears interaction, unit, and value mappings that the submit writes explicitly', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      compare: false,
      unit: '',
      valueMappings: [],
      interaction: {
        kind: 'none',
        name: '详情',
        url: '/ops',
        openMode: 'newTab',
      },
    },
    chartType: 'single',
  });
  assert.equal(submitted.error, undefined);

  const saved = persisted(mergeLikeScreen(
    {
      chartType: 'single',
      selectedFields: ['value'],
      unit: '分',
      valueMappings: [{ type: 'value', value: '1', result: { text: '一' } }],
      interaction: {
        kind: 'title',
        name: '详情',
        url: '/ops/old',
        openMode: 'sameTab',
      },
    },
    submitted.config!,
    'single',
  ));

  assert.equal(saved.unit ?? '', '');
  assert.deepEqual(saved.valueMappings ?? [], []);
  assert.equal('interaction' in saved, false);
});

test('screen save keeps a chart theme the data form does not edit', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: '总体健康分',
      chartType: 'single',
      descriptionField: 'health_note',
      compare: false,
    },
    chartType: 'single',
  });
  const saved = persisted(mergeLikeScreen(
    {
      chartType: 'single',
      selectedFields: ['value'],
      chartThemeMode: 'screen-dark',
      descriptionField: 'note',
    },
    submitted.config!,
    'single',
  ));

  assert.equal(saved.chartThemeMode, 'screen-dark');
  assert.equal(saved.descriptionField, 'health_note');
});

test('screen save replaces event timeline and card list objects, so cleared slots do not stick', () => {
  const timeline = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'eventTimeline',
    values: {
      name: '事件时间线',
      chartType: 'eventTimeline',
      eventTimeline: {
        sortOrder: 'desc',
        timeField: 'time',
        titleField: 'title',
        descriptionField: '',
      },
    },
  });
  const timelineSaved = persisted(mergeLikeScreen(
    {
      chartType: 'eventTimeline',
      eventTimeline: {
        sortOrder: 'desc',
        timeField: 'time',
        titleField: 'title',
        descriptionField: 'detail',
      },
    },
    timeline.config!,
    'eventTimeline',
  ));
  assert.equal(timelineSaved.eventTimeline?.descriptionField, undefined);

  const cards = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'cardList',
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        descriptionField: '   ',
      },
    },
  });
  const cardsSaved = persisted(mergeLikeScreen(
    {
      chartType: 'cardList',
      cardList: {
        titleField: 'title',
        descriptionField: 'summary',
      },
    },
    cards.config!,
    'cardList',
  ));
  assert.equal(cardsSaved.cardList?.descriptionField, undefined);

  const radar = buildWidgetSubmitConfig({
    ...baseInput,
    selectedFields: [],
    chartType: 'radar',
    values: {
      name: '雷达图',
      chartType: 'radar',
      radar: {
        min: 0,
        max: 100,
        indicators: [{ key: 'cpu', label: 'CPU' }],
        arrayNameField: '',
        arrayValueField: ' ',
      },
    },
  });
  const radarSaved = persisted(mergeLikeScreen(
    {
      chartType: 'radar',
      radar: {
        min: 0,
        max: 100,
        indicators: [{ key: 'cpu' }],
        arrayNameField: 'name',
        arrayValueField: 'value',
      },
    },
    radar.config!,
    'radar',
  ));
  assert.equal(radarSaved.radar?.arrayNameField, undefined);
  assert.equal(radarSaved.radar?.arrayValueField, undefined);
});
