import assert from 'node:assert/strict';
import test from 'node:test';
import { applyTopNValueConfig, buildValueConfig } from '../namespaceUtils';

test('topology topN save keeps label ranking and drops scalar rows and bar scale', () => {
  const config = applyTopNValueConfig(
    {
      topNLabelField: 'old',
      topNValueField: 'count',
      topNScalarFields: [{ field: 'avg_cpu', label: 'CPU' }],
      barMode: 'absolute',
      barMax: 100,
    },
    {
      topNLabelField: 'name',
      topNValueField: 'value',
    },
  );

  assert.equal(config.topNLabelField, 'name');
  assert.equal(config.topNValueField, 'value');
  assert.equal('topNScalarFields' in config, false);
  assert.equal('barMode' in config, false);
  assert.equal('barMax' in config, false);
});

test('topology topN build keeps label ranking and omits bar scale', () => {
  const config = buildValueConfig({
    name: '主机',
    chartType: 'topN',
    topNLabelField: 'name',
    topNValueField: 'value',
    topNScalarFields: [{ field: 'avg_cpu', label: 'CPU' }],
    barMode: 'absolute',
    barMax: 100,
  });

  assert.equal(config.topNLabelField, 'name');
  assert.equal(config.topNValueField, 'value');
  assert.equal('topNScalarFields' in config, false);
  assert.equal('barMode' in config, false);
  assert.equal('barMax' in config, false);
});
