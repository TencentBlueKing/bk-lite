import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';
import {
  buildCardListFieldOptions,
  resolveCardListOptionalOpenState,
  resolveCardListOptionalSummaries,
} from '../cardListSettingsModel';

const fields = [
  { key: 'name', title: '名称', value_type: 'string' as const },
  { key: 'summary', title: '摘要', value_type: 'string' as const },
  { key: 'severity', title: '', value_type: 'string' as const },
];

const summaryCopy = {
  none: '不显示',
  index: '序号',
  field: '字段',
  unconfigured: '未配置',
  firstLine: '第一行',
  secondLine: '第二行',
};

const submit = (cardList: Record<string, unknown>) =>
  buildWidgetSubmitConfig({
    chartType: 'cardList',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
    values: {
      name: '卡片列表',
      chartType: 'cardList',
      cardList,
    },
  });

test('field options prefer schema label and keep key for search', () => {
  const options = buildCardListFieldOptions(fields);
  assert.deepEqual(options[0], {
    value: 'name',
    label: 'name (名称)',
    previewLabel: '名称',
    key: 'name',
    searchText: 'name 名称',
  });
  assert.equal(options[2]?.label, 'severity');
  assert.equal(options[2]?.previewLabel, 'severity');
});

test('default optional groups stay closed', () => {
  assert.deepEqual(
    resolveCardListOptionalOpenState({
      leading: { type: 'none' },
      layout: 'list',
    }),
    { leading: false, badge: false, trailing: false },
  );
});

test('edit restore opens optional groups from persisted fields', () => {
  assert.deepEqual(
    resolveCardListOptionalOpenState({
      titleField: 'name',
      leading: { type: 'field', field: 'severity' },
      badgeField: 'severity',
      trailingSecondaryField: 'owner',
      layout: 'grid',
    }),
    { leading: true, badge: true, trailing: true },
  );
});

test('optional summaries follow the current draft and prefer display names', () => {
  const options = buildCardListFieldOptions(fields);
  assert.deepEqual(
    resolveCardListOptionalSummaries(
      { leading: { type: 'none' } },
      options,
      summaryCopy,
    ),
    { leading: '不显示', badge: '未配置', trailing: '未配置' },
  );
  assert.deepEqual(
    resolveCardListOptionalSummaries(
      {
        leading: { type: 'index' },
        badgeField: 'severity',
        trailingPrimaryField: 'name',
        trailingSecondaryField: 'summary',
      },
      options,
      summaryCopy,
    ),
    {
      leading: '序号',
      badge: 'severity',
      trailing: '名称 · 摘要',
    },
  );
  assert.equal(
    resolveCardListOptionalSummaries(
      { leading: { type: 'field', field: 'name' } },
      options,
      summaryCopy,
    ).leading,
    '字段 · 名称',
  );
  assert.equal(
    resolveCardListOptionalSummaries(
      { leading: { type: 'field', field: '  ' } },
      options,
      summaryCopy,
    ).leading,
    '字段 · 未配置',
  );
  assert.equal(
    resolveCardListOptionalSummaries(
      { trailingSecondaryField: 'owner' },
      options,
      summaryCopy,
    ).trailing,
    '第二行 · owner',
  );
});

test('clearing optional selects and leading none omits them on submit', () => {
  const cleared = submit({
    titleField: 'name',
    leading: { type: 'none', field: 'severity' },
    badgeField: '  ',
    trailingPrimaryField: '',
    trailingSecondaryField: undefined,
    layout: 'list',
  });

  assert.equal(cleared.error, undefined);
  assert.deepEqual(cleared.config?.cardList, { titleField: 'name' });
});

test('switching leading field back to none does not persist the old field', () => {
  const result = submit({
    titleField: 'name',
    leading: { type: 'none', field: 'severity' },
  });
  assert.equal(result.error, undefined);
  assert.equal('leading' in (result.config?.cardList || {}), false);
});
