import assert from 'node:assert/strict';
import test from 'node:test';
import { applyTopNValueConfig, buildValueConfig } from '../namespaceUtils';

test('topology topN save drops ranking fields and relative bar settings', () => {
  const config = applyTopNValueConfig(
    {
      topNLabelField: 'name',
      topNValueField: 'value',
      barMode: 'absolute',
      barMax: 100,
    },
    {
      topNScalarFields: [{ field: ' avg_cpu ', label: ' CPU ' }, { field: ' ' }],
      barMode: 'relative',
      barMax: 100,
    },
  );

  assert.deepEqual(config.topNScalarFields, [{ field: 'avg_cpu', label: 'CPU' }]);
  assert.equal('topNLabelField' in config, false);
  assert.equal('topNValueField' in config, false);
  assert.equal('barMode' in config, false);
  assert.equal('barMax' in config, false);
});

test('topology topN build keeps label ranking and an absolute full score', () => {
  const config = buildValueConfig({
    name: '主机',
    chartType: 'topN',
    topNLabelField: 'name',
    topNValueField: 'value',
    topNScalarFields: [],
    barMode: 'absolute',
    barMax: 100,
  });

  assert.equal(config.topNLabelField, 'name');
  assert.equal(config.topNValueField, 'value');
  assert.equal('topNScalarFields' in config, false);
  assert.equal(config.barMode, 'absolute');
  assert.equal(config.barMax, 100);
});

test('absolute mode without a positive full score omits barMax', () => {
  const config = applyTopNValueConfig(
    { barMode: 'absolute', barMax: 80 },
    { barMode: 'absolute', barMax: 0 },
  );

  assert.equal(config.barMode, 'absolute');
  assert.equal('barMax' in config, false);
});
