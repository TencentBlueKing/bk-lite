import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDataFetchSignature } from '../widgetConfigFormState';
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

test('single submit stores style and leaves data fields in place', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'single',
    values: {
      name: '在线数',
      chartType: 'single',
      compare: false,
      descriptionField: 'note',
      singleStyle: {
        showIcon: true,
        iconSource: 'builtin',
        iconKey: 'cc-host',
        iconImage: 'data:image/png;base64,abc',
        iconPosition: 'left',
        iconSize: 'medium',
        align: 'left',
      },
    },
  });

  assert.equal(result.config?.descriptionField, 'note');
  assert.deepEqual(result.config?.singleStyle, {
    showIcon: true,
    iconKey: 'cc-host',
    align: 'left',
  });
});

test('single submit omits untouched default style', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'single',
    values: {
      name: '在线数',
      chartType: 'single',
      compare: false,
      singleStyle: {
        showIcon: false,
        iconPosition: 'left',
        iconSize: 'medium',
      },
    },
  });

  assert.equal(result.config?.singleStyle, undefined);
});

test('screen data submit does not overwrite a stored single style', () => {
  const result = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'single',
    includeSingleStyle: false,
    values: {
      name: '在线数',
      chartType: 'single',
      compare: false,
      descriptionField: 'note',
      singleStyle: {
        showIcon: true,
        iconSource: 'upload',
        iconKey: 'cc-host',
        iconImage: 'data:image/png;base64,abc',
        align: 'right',
      },
    },
  });
  assert.equal(result.config && 'singleStyle' in result.config, false);
  const stored = {
    chartType: 'single',
    descriptionField: 'old',
    singleStyle: { showIcon: true, iconKey: 'cc-host', align: 'center' },
  };
  const merged = mergeScreenWidgetValueConfig(stored, result.config || {}, 'single');

  assert.deepEqual(merged.singleStyle, stored.singleStyle);
  assert.equal(merged.descriptionField, 'note');
});

test('switching chart type drops single style and clearing it removes the stored object', () => {
  const stored = {
    chartType: 'single',
    singleStyle: { showIcon: true, iconKey: 'cc-host' },
  };
  const asLine = mergeSanitizedWidgetValueConfig(stored, { chartType: 'line' }, 'line');
  assert.equal('singleStyle' in asLine, false);

  const cleared = mergeSanitizedWidgetValueConfig(
    stored,
    { chartType: 'single', singleStyle: undefined },
    'single',
  );
  assert.equal('singleStyle' in cleared, false);

  const kept = mergeSanitizedWidgetValueConfig(
    stored,
    { chartType: 'single', singleStyle: { showIcon: true, iconPosition: 'right' } },
    'single',
  );
  assert.equal(kept.singleStyle?.iconPosition, 'right');
});

test('style changes do not alter the data fetch signature', () => {
  const base = {
    name: '在线数',
    chartType: 'single',
    dataSource: 1,
    compare: false,
  };
  assert.equal(
    buildDataFetchSignature(base),
    buildDataFetchSignature({
      ...base,
      singleStyle: { showIcon: true, iconKey: 'cc-host', align: 'center' },
    }),
  );
});
