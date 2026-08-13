import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

test('topologyMap submit follows the ordinary datasource chart path', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: '关系拓扑',
      description: '通用实体关系',
      chartType: 'topologyMap',
      dataSource: 42,
    },
    chartType: 'topologyMap',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.deepEqual(result, {
    config: {
      name: '关系拓扑',
      description: '通用实体关系',
      chartType: 'topologyMap',
      dataSource: 42,
    },
  });
  assert.equal('sceneWidgetType' in result.config, false);
  assert.equal('networkStatusTopology' in result.config, false);
});
