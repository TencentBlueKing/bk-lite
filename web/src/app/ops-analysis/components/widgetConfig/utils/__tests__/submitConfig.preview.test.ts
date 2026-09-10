import assert from 'node:assert/strict';
import test from 'node:test';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  buildWidgetDraftConfig,
  buildWidgetSubmitConfig,
} from '../submitConfig';

const baseInput = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

const switchParam = (name: string): ParamItem => ({
  name,
  alias_name: name,
  type: 'string',
  filterType: 'params',
  value: 'a',
  inputConfig: {
    control: 'select',
    componentSwitch: true,
    optionsSource: { type: 'static', staticItems: [] },
  },
});

test('preview draft skips cardList title required that blocks save', () => {
  const input = {
    ...baseInput,
    chartType: 'cardList',
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: { titleField: '   ' },
    },
  };

  const saved = buildWidgetSubmitConfig(input);
  assert.equal(saved.error, 'cardListTitleRequired');
  assert.equal(saved.config, undefined);

  const draft = buildWidgetDraftConfig(input);
  assert.ok(draft);
  assert.equal(draft.chartType, 'cardList');
  assert.equal('cardList' in draft, false);
});

test('preview draft skips empty leading field that blocks save', () => {
  const input = {
    ...baseInput,
    chartType: 'cardList',
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList: { titleField: 'title', leading: { type: 'field' as const, field: '  ' } },
    },
  };

  const saved = buildWidgetSubmitConfig(input);
  assert.equal(saved.error, 'cardListLeadingFieldRequired');
  assert.equal(saved.config, undefined);

  const draft = buildWidgetDraftConfig(input);
  assert.ok(draft);
  assert.deepEqual(draft.cardList, { titleField: 'title' });
});

test('preview draft skips duplicate table keys that block save', () => {
  const input = {
    ...baseInput,
    chartType: 'table',
    values: {
      name: '表格',
      chartType: 'table',
    },
    displayColumns: [
      { id: 'a', key: 'cpu', title: 'CPU', visible: true, order: 0 },
      { id: 'b', key: 'cpu', title: 'CPU 2', visible: true, order: 1 },
    ],
  };

  const saved = buildWidgetSubmitConfig(input);
  assert.equal(saved.error, 'duplicateFieldKey');
  assert.equal(saved.config, undefined);

  const draft = buildWidgetDraftConfig(input);
  assert.ok(draft);
  assert.equal(draft.tableConfig?.columns?.length, 2);
});

test('preview draft skips hidden-only columns that block save', () => {
  const input = {
    ...baseInput,
    chartType: 'table',
    values: {
      name: '表格',
      chartType: 'table',
    },
    displayColumns: [
      { id: 'a', key: 'cpu', title: 'CPU', visible: false, order: 0 },
    ],
  };

  const saved = buildWidgetSubmitConfig(input);
  assert.equal(saved.error, 'atLeastOneVisibleColumn');
  assert.equal(saved.config, undefined);

  const draft = buildWidgetDraftConfig(input);
  assert.ok(draft);
  assert.equal(draft.tableConfig?.columns?.[0]?.visible, false);
});

test('preview draft skips multiple componentSwitch params that block save', () => {
  const input = {
    ...baseInput,
    chartType: 'topN',
    values: {
      name: 'TopN',
      chartType: 'topN',
      dataSourceParams: [switchParam('room'), switchParam('cluster')],
    },
  };

  const saved = buildWidgetSubmitConfig(input);
  assert.equal(saved.error, 'multipleComponentSwitchParams');
  assert.equal(saved.config, undefined);

  const draft = buildWidgetDraftConfig(input);
  assert.ok(draft);
  assert.equal(draft.chartType, 'topN');
});

test('preview draft still carries filter bindings', () => {
  const draft = buildWidgetDraftConfig({
    ...baseInput,
    chartType: 'line',
    filterBindings: { instance_ids__string: true },
    values: {
      name: '折线',
      chartType: 'line',
      dataSource: 9,
    },
  });

  assert.deepEqual(draft?.filterBindings, { instance_ids__string: true });
});
