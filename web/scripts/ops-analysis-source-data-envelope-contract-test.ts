import assert from 'node:assert/strict';
import { parseSourceDataResponse } from '../src/app/ops-analysis/utils/sourceDataResponse';
import { fetchWidgetData } from '../src/app/ops-analysis/utils/widgetDataTransform';
import { fetchCompareData } from '../src/app/ops-analysis/utils/compareQuery';
import { createParamInputOptionsLoader } from '../src/app/ops-analysis/utils/paramInputOptionsLoader';
import { extractDataSourceItems } from '../src/app/ops-analysis/utils/paramInputConfigUtils';
import { extractFirstRecordFromSourceData } from '../src/app/ops-analysis/components/widgetConfig/utils/columnProbing';
import { buildTreeData } from '../src/app/ops-analysis/(pages)/view/topology/utils/dataTreeUtils';

async function main() {
  const collisionPayload = {
    data: { foo: 'business-data' },
    warnings: ['business-warning'],
  };

  const transportResponse = {
    data: collisionPayload,
    warnings: [],
  };

  assert.deepEqual(parseSourceDataResponse(transportResponse), transportResponse);

  const getSourceDataByApiId = async () => parseSourceDataResponse(transportResponse);

  const widgetData = await fetchWidgetData({
    config: { dataSource: 1 },
    dataSource: { params: [] },
    getSourceDataByApiId,
  });
  assert.deepEqual(widgetData, collisionPayload);

  let comparisonRequests = 0;
  const comparison = await fetchCompareData({
    dataSourceId: 1,
    getSourceDataByApiId: async () => {
      comparisonRequests += 1;
      return parseSourceDataResponse(transportResponse);
    },
    config: {
      dataSource: 1,
      compare: true,
      dataSourceParams: [
        {
          name: 'period',
          alias_name: 'Period',
          type: 'dateRange',
          filterType: 'params',
          value: {
            rangeType: 'custom',
            startDate: '2026-08-01',
            endDate: '2026-08-07',
          },
        },
      ],
    },
    dataSource: { params: [] },
  });
  assert.deepEqual(comparison.currentData, collisionPayload);
  assert.deepEqual(comparison.baselineData, collisionPayload);
  assert.equal(comparisonRequests, 2);

  const singleProbe = buildTreeData(collisionPayload);
  assert.deepEqual(singleProbe.map((node) => node.key), ['data', 'warnings']);

  assert.deepEqual(
    extractFirstRecordFromSourceData({ items: [collisionPayload] }),
    collisionPayload,
  );

  const optionsLoader = createParamInputOptionsLoader({
    getDataSourceList: async () => [{ id: 1, rest_api: 'demo/options' }],
    getSourceDataByApiId: async () =>
      parseSourceDataResponse({
        data: { items: [{ id: 7, label: 'seven' }] },
        warnings: [],
      }),
  });
  const optionsResult = await optionsLoader.load({
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'demo/options' },
      valueField: 'id',
      labelField: 'label',
    },
  }).promise;
  assert.deepEqual(optionsResult, {
    status: 'success',
    options: [{ value: 7, label: 'seven' }],
  });
  assert.deepEqual(
    extractDataSourceItems(
      parseSourceDataResponse({
        data: { items: [{ id: 8 }] },
        warnings: [],
      }).data,
    ),
    [{ id: 8 }],
  );

  for (const businessPayload of [
    [{ id: 1 }],
    { items: [{ id: 1 }] },
    { foo: 'bar' },
    {},
    { data: { foo: 'business-data' } },
    { warnings: ['business-warning'] },
    collisionPayload,
  ]) {
    const parsed = parseSourceDataResponse({ data: businessPayload, warnings: [] });
    assert.deepEqual(parsed.data, businessPayload);
  }

  console.log('ops analysis source data envelope contract tests passed');
}

void main();
