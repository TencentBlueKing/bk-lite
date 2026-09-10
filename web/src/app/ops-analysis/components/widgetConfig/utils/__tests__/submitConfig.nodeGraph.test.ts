import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

const base = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

test('nodeGraph submit persists mapping, service port, and unit conversion', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
    chartType: 'nodeGraph',
    values: {
      name: '通信关系图',
      chartType: 'nodeGraph',
      dataSource: 57,
      nodeGraphIdentityMode: 'service',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
      nodeGraphTargetPortField: 'dst_port',
      unitId: 'bps',
      conversionFactor: 8,
      decimalPlaces: 1,
    },
  });
  assert.equal(result.error, undefined);
  assert.equal(result.config?.chartType, 'nodeGraph');
  assert.equal(result.config?.nodeGraphIdentityMode, 'service');
  assert.equal(result.config?.nodeGraphSourceField, 'src');
  assert.equal(result.config?.nodeGraphTargetField, 'dst');
  assert.equal(result.config?.nodeGraphValueField, 'value');
  assert.equal(result.config?.nodeGraphTargetPortField, 'dst_port');
  assert.equal(result.config?.unitId, 'bps');
  assert.equal(result.config?.conversionFactor, 8);
  assert.equal(result.config?.decimalPlaces, 1);
  assert.equal('sceneWidgetType' in (result.config || {}), false);
});

test('nodeGraph ip mode omits destination port', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
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
  assert.equal(result.config?.nodeGraphIdentityMode, 'ip');
  assert.equal('nodeGraphTargetPortField' in (result.config || {}), false);
});
