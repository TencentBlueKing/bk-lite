import { describe, expect, it } from 'vitest';

import {
  DATA_VARIABLE_ROW_LIMIT,
  collectVariableIds,
  substituteDataVariableUpstream,
  columnBlockReasonKey,
  executionOrder,
  extractValueColumn,
  readDataVariables,
  resolveParamRecord,
  runDataVariables,
  validateDataVariables,
  widgetQueryToDataVariable,
  type DataVariable,
} from '@/app/ops-analysis/utils/dataVariable';
import { buildCompareRequestParams, fetchCompareData } from '@/app/ops-analysis/utils/compareQuery';
import { processDataSourceParams, widgetDataVariableBlockReason } from '@/app/ops-analysis/utils/widgetDataTransform';

const variable = (patch: Partial<DataVariable> & Pick<DataVariable, 'id'>): DataVariable => ({
  name: patch.id,
  dataSourceId: 1,
  valueField: 'inst_uuid',
  params: {},
  ...patch,
});

describe('data variables', () => {
  it('reads a stored variable and ignores a row without an id', () => {
    expect(readDataVariables([
      {
        id: 'dv_1',
        name: ' 云区域主机 ',
        dataSourceId: 8,
        valueField: 'inst_uuid',
        params: { model_id: 'host' },
        filterBindings: { cloud: true, stale: 'yes' },
        paramInputs: { instance_ids: { control: 'dataVariable', dataVariableId: 'dv_region' } },
      },
      { name: '缺 id' },
    ])).toEqual([{
      id: 'dv_1',
      name: '云区域主机',
      dataSourceId: 8,
      valueField: 'inst_uuid',
      params: { model_id: 'host' },
      filterBindings: { cloud: true },
      paramInputs: { instance_ids: { control: 'dataVariable', dataVariableId: 'dv_region' } },
    }]);
  });

  it('extracts a value column from an array or an items envelope and drops empty cells', () => {
    expect(extractValueColumn([
      { inst_uuid: 'a' },
      { inst_uuid: '' },
      { inst_uuid: null },
      { inst_uuid: 'b' },
    ], 'inst_uuid')).toEqual({ status: 'ready', values: ['a', 'b'] });
    expect(extractValueColumn({
      items: [{ end_uuid: 'x' }],
      count: 1,
    }, 'end_uuid')).toEqual({ status: 'ready', values: ['x'] });
  });

  it('flattens string arrays into the value column and keeps scalar cells', () => {
    expect(extractValueColumn([
      { inst_uuids: ['a', '', 'b'] },
      { inst_uuids: 'c' },
      { inst_uuids: [] },
      { inst_uuids: ['d'] },
    ], 'inst_uuids')).toEqual({ status: 'ready', values: ['a', 'b', 'c', 'd'] });
    expect(extractValueColumn([{ id: 3 }], 'id')).toEqual({ status: 'ready', values: [3] });
  });

  it('blocks a string-array cell that contains a nested value', () => {
    expect(extractValueColumn([
      { inst_uuids: ['a'] },
      { inst_uuids: [['b']] },
    ], 'inst_uuids')).toEqual({ status: 'blocked', reason: 'cell' });
    expect(extractValueColumn([{ inst_uuids: [{ id: 'a' }] }], 'inst_uuids')).toEqual({
      status: 'blocked',
      reason: 'cell',
    });
    expect(columnBlockReasonKey('cell')).toBe('dataVariable.reasonCell');
  });

  it('blocks a column that is not a row list, misses the field, is empty, or exceeds the cap', () => {
    expect(extractValueColumn({ instance_count: 3 }, 'instance_count').status).toBe('blocked');
    expect(extractValueColumn({ data: [{ id: 1 }] }, 'id').status).toBe('blocked');
    expect(extractValueColumn([{ name: 'host' }], 'inst_uuid')).toEqual({
      status: 'blocked',
      reason: 'missing-field',
    });
    expect(extractValueColumn([
      { name: 'host' },
      { inst_uuid: 'a' },
      null,
      { inst_uuid: '' },
      { inst_uuid: 'b' },
    ], 'inst_uuid')).toEqual({ status: 'ready', values: ['a', 'b'] });
    expect(extractValueColumn([], 'inst_uuid')).toEqual({ status: 'blocked', reason: 'empty' });
    expect(extractValueColumn([{ inst_uuid: '' }], 'inst_uuid')).toEqual({
      status: 'blocked',
      reason: 'empty',
    });
    const tooMany = Array.from({ length: DATA_VARIABLE_ROW_LIMIT + 1 }, (_, index) => ({ id: index }));
    expect(extractValueColumn(tooMany, 'id').status).toBe('blocked');
  });

  it('passes a whole column and blocks an empty upstream or an empty header filter', () => {
    expect(resolveParamRecord({
      instance_ids: { dataVariableId: 'hosts' },
      level: '',
    }, {
      hosts: { status: 'ready', values: ['a', 'b'] },
    })).toEqual({ blocked: false, params: { instance_ids: ['a', 'b'] } });

    expect(resolveParamRecord({
      instance_ids: { dataVariableId: 'hosts' },
    }, {
      hosts: { status: 'blocked', reason: 'empty' },
    })).toEqual({ blocked: true, reason: 'empty' });
    expect(resolveParamRecord({
      instance_ids: { dataVariableId: 'missing' },
    }, {}).blocked).toBe(true);
  });

  it('rejects duplicate names, cycles, and a chain longer than three variables', () => {
    expect(validateDataVariables([
      variable({ id: 'a', name: '主机' }),
      variable({ id: 'b', name: '主机' }),
    ]).some((issue) => issue.code === 'duplicate-name')).toBe(true);

    expect(validateDataVariables([
      variable({ id: 'a', params: { id: { dataVariableId: 'b' } } }),
      variable({ id: 'b', params: { id: { dataVariableId: 'a' } } }),
    ]).some((issue) => issue.code === 'cycle')).toBe(true);

    const deep = validateDataVariables([
      variable({ id: 'a' }),
      variable({ id: 'b', params: { id: { dataVariableId: 'a' } } }),
      variable({ id: 'c', params: { id: { dataVariableId: 'b' } } }),
      variable({ id: 'd', params: { id: { dataVariableId: 'c' } } }),
    ]);
    expect(deep.some((issue) => issue.code === 'too-deep' && issue.id === 'd')).toBe(true);
    expect(deep.some((issue) => issue.code === 'too-deep' && issue.id === 'c')).toBe(false);
  });

  it('runs each used variable once, upstream first, and skips an unused variable', async () => {
    const calls: string[] = [];
    const variables = [
      variable({ id: 'assets', params: { ids: { dataVariableId: 'hosts' } }, valueField: 'end_uuid' }),
      variable({ id: 'hosts', valueField: 'inst_uuid' }),
      variable({ id: 'unused' }),
    ];
    const run = await runDataVariables({
      variables,
      roots: ['assets'],
      fetchRows: async (_variable, params) => {
        calls.push(JSON.stringify(params));
        if (!('ids' in params)) return [{ inst_uuid: 'h1' }];
        return [{ end_uuid: 'a1' }];
      },
    });
    expect(executionOrder(variables, ['assets'])).toEqual(['hosts', 'assets']);
    expect(calls).toEqual(['{}', '{"ids":["h1"]}']);
    expect(run.columns.assets).toEqual({ status: 'ready', values: ['a1'] });
    expect(run.columns.unused).toBeUndefined();
    expect(collectVariableIds({ widget: { instance_ids: { dataVariableId: 'assets' } } })).toEqual(['assets']);
  });

  it('copies a widget query into a data variable without keeping the form object', () => {
    const params = { cloud_region_ids: ['sh'], model_asst_ids: ['mysql_run_host'] };
    const created = widgetQueryToDataVariable({
      name: ' 腾讯团体系 ',
      valueField: ' value ',
      dataSourceId: 12,
      params,
      filterBindings: { region: true, stale: false },
      paramInputs: {
        model_asst_ids: {
          control: 'select',
          multiple: true,
          optionsSource: { type: 'static', staticItems: [] },
        },
        ignored: { control: 'dataVariable', dataVariableId: '' },
      },
    });
    params.cloud_region_ids.push('gz');
    expect(created.id.startsWith('dv_')).toBe(true);
    expect(created.name).toBe('腾讯团体系');
    expect(created.valueField).toBe('value');
    expect(created.dataSourceId).toBe(12);
    expect(created.params).toEqual({
      cloud_region_ids: ['sh'],
      model_asst_ids: ['mysql_run_host'],
    });
    expect(created.filterBindings).toEqual({ region: true, stale: false });
    expect(created.paramInputs).toEqual({
      model_asst_ids: {
        control: 'select',
        multiple: true,
        optionsSource: { type: 'static', staticItems: [] },
      },
    });
  });

  it('reports why a widget cannot use a blocked value column', () => {
    const reason = widgetDataVariableBlockReason({
      config: {
        dataSourceParams: [
          { name: 'ids', type: 'string', value: { dataVariableId: 'dv_1' } },
        ],
      },
      dataVariableColumns: {
        dv_1: { status: 'blocked', reason: 'empty' },
      },
    });
    expect(reason).toBe('empty');
    expect(columnBlockReasonKey('empty')).toBe('dataVariable.reasonEmpty');
    expect(columnBlockReasonKey('request')).toBe('dataVariable.reasonRequest');
  });

  it('replaces a variable reference with its value column', () => {
    const ref = { dataVariableId: 'dv_map' };
    expect(substituteDataVariableUpstream('east', undefined)).toBe('east');
    expect(substituteDataVariableUpstream(ref, undefined)).toBeUndefined();
    expect(substituteDataVariableUpstream(ref, {
      dv_map: { status: 'blocked', reason: 'upstream' },
    })).toBeUndefined();
    expect(substituteDataVariableUpstream(ref, {
      dv_map: { status: 'ready', values: ['17', '18'] },
    })).toEqual(['17', '18']);
  });

  it('puts the value column into the widget request', async () => {
    const config = {
      chartType: 'single',
      dataSourceParams: [
        { name: 'monitor_object_id', type: 'string', filterType: 'params', value: 17 },
        {
          name: 'instance_ids',
          type: 'string',
          filterType: 'params',
          value: { dataVariableId: 'dv_map' },
        },
      ],
    };
    const unresolved = buildCompareRequestParams({ config });
    expect(unresolved.currentParams).toBeNull();

    const resolved = buildCompareRequestParams({
      config,
      dataVariableColumns: {
        dv_map: { status: 'ready', values: ['m1', 'm2'] },
      },
    });
    expect(resolved.currentParams).toEqual({
      monitor_object_id: 17,
      instance_ids: ['m1', 'm2'],
    });

    const calls: unknown[] = [];
    const blocked = await fetchCompareData({
      dataSourceId: 9,
      config,
      getSourceDataByApiId: async (_id, params) => {
        calls.push(params);
        return { data: { alert_count: 0 } };
      },
    });
    expect(calls).toEqual([]);
    expect(blocked.currentData).toBeNull();

    const sent = await fetchCompareData({
      dataSourceId: 9,
      config,
      dataVariableColumns: {
        dv_map: { status: 'ready', values: ['m1', 'm2'] },
      },
      getSourceDataByApiId: async (_id, params) => {
        calls.push(params);
        return { data: { alert_count: 2 } };
      },
    });
    expect(calls).toEqual([{
      monitor_object_id: 17,
      instance_ids: ['m1', 'm2'],
    }]);
    expect(sent.currentData).toEqual({ alert_count: 2 });
  });

  it('sends the resolved column for a param that has no filter type', () => {
    const ref = { dataVariableId: 'dv_1' };
    const request = processDataSourceParams({
      sourceParams: [{ name: 'ids', type: 'string', value: ref }],
      userParams: { ids: ['a', 'b'] },
      preserveArrayNames: new Set(['ids']),
    });
    expect(request.ids).toEqual(['a', 'b']);

    const fixed = processDataSourceParams({
      sourceParams: [{ name: 'ids', type: 'string', filterType: 'fixed', value: 'host' }],
      userParams: { ids: ['a', 'b'] },
    });
    expect(fixed.ids).toBe('host');
  });
});
