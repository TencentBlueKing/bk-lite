import { describe, expect, it } from 'vitest';
import type { DatasourceItem, InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import { scanDataSourceFilterParams } from '@/app/ops-analysis/utils/scanUnifiedFilterParams';

const roomSource = (restApi = 'cmdb/get_room_list'): InputControlConfig => ({
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceRef: { type: 'rest_api', value: restApi },
    valueField: 'inst_uuid',
    labelField: 'inst_name',
  },
});

const source = (
  id: number,
  name: string,
  params: DatasourceItem['params'],
): DatasourceItem => ({
  id,
  name,
  rest_api: name,
  desc: '',
  params: params ?? [],
  chart_type: ['single'],
  namespaces: [],
} as DatasourceItem);

const layout = (ids: number[]) => ids.map((id) => ({
  valueConfig: { dataSource: id },
}));

describe('scan unified filter params', () => {
  it('keeps one room filter when heterogeneous sources share cmdb/get_room_list', () => {
    const scanned = scanDataSourceFilterParams(layout([1, 2, 3]), [
      source(1, 'room-a', [{
        name: 'server_room_id',
        alias_name: '机房',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: roomSource(),
      }]),
      source(2, 'room-b', [{
        name: 'server_room_id',
        alias_name: '机房',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: roomSource(),
      }]),
      source(3, 'room-c', [{
        name: 'server_room_id',
        alias_name: '机房',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: roomSource(),
      }]),
    ]);

    expect(scanned).toHaveLength(1);
    expect(scanned[0]?.id).toBe('server_room_id__string');
    expect(scanned[0]?.componentCount).toBe(3);
  });

  it('merges different option universes into the name and type row and keeps the stored config', () => {
    const storedConfig = roomSource();
    const stored: UnifiedFilterDefinition[] = [{
      id: 'server_room_id__string',
      key: 'server_room_id',
      name: '机房',
      type: 'string',
      defaultValue: null,
      order: 0,
      enabled: true,
      inputConfig: storedConfig,
    }];
    const scanned = scanDataSourceFilterParams(layout([1, 2]), [
      source(1, '验收·级联指标图', [{
        name: 'server_room_id',
        alias_name: '机房',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: roomSource('demo/accept_metrics'),
      }]),
      source(2, 'demo/accept_metrics_b', [{
        name: 'server_room_id',
        alias_name: '机房',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: roomSource('demo/accept_metrics_b'),
      }]),
    ], stored);

    expect(scanned).toHaveLength(1);
    expect(scanned[0]?.id).toBe('server_room_id__string');
    expect(scanned[0]?.componentCount).toBe(2);
    expect(scanned[0]?.suggestedName).toBe('机房');
    expect(scanned[0]?.suggestedName).not.toContain('·');
    expect(scanned[0]?.sampleInputConfig).toEqual(storedConfig);
  });

  it('keeps the first scanned config when no definition is stored yet', () => {
    const first = roomSource('cmdb/devices');
    const scanned = scanDataSourceFilterParams(layout([1, 2]), [
      source(1, 'cmdb/devices', [{
        name: 'device_id', alias_name: '设备', type: 'string', filterType: 'filter', value: null,
        inputConfig: first,
      }]),
      source(2, 'monitor/devices', [{
        name: 'device_id', alias_name: '设备', type: 'string', filterType: 'filter', value: null,
        inputConfig: roomSource('monitor/devices'),
      }]),
    ]);
    expect(scanned.map((item) => item.id)).toEqual(['device_id__string']);
    expect(scanned[0]?.sampleInputConfig).toEqual(first);
    expect(scanned[0]?.suggestedName).toBe('设备');
  });

  it('still merges different option sources that reference the same upstream', () => {
    const withRef = (restApi: string): InputControlConfig => ({
      control: 'select',
      optionsSource: {
        type: 'dynamic',
        sourceRef: { type: 'rest_api', value: restApi },
        valueField: 'id',
        labelField: 'name',
        queryParams: { room_id: { ref: 'server_room_id' } },
      },
    });
    const scanned = scanDataSourceFilterParams(layout([1, 2]), [
      source(1, 'cmdb/devices', [{
        name: 'device_id', alias_name: '设备', type: 'string', filterType: 'filter', value: null,
        inputConfig: withRef('cmdb/devices'),
      }]),
      source(2, 'monitor/devices', [{
        name: 'device_id', alias_name: '设备', type: 'string', filterType: 'filter', value: null,
        inputConfig: withRef('monitor/devices'),
      }]),
    ]);
    expect(scanned).toHaveLength(1);
    expect(scanned[0]?.id).toBe('device_id__string');
    const kept = scanned[0]?.sampleInputConfig;
    expect(kept && kept.control === 'select' && kept.optionsSource.type === 'dynamic'
      ? kept.optionsSource.sourceRef?.value
      : undefined).toBe('cmdb/devices');
  });

  it('still merges time range and organization by name and type only', () => {
    const scanned = scanDataSourceFilterParams(layout([1, 2]), [
      source(1, 'a', [
        { name: 'time', alias_name: '时间', type: 'timeRange', filterType: 'filter', value: 15 },
        {
          name: 'organization', alias_name: '组织', type: 'string', filterType: 'filter', value: null,
          inputConfig: { control: 'organization' },
        },
      ]),
      source(2, 'b', [
        { name: 'time', alias_name: '时间', type: 'timeRange', filterType: 'filter', value: 60 },
        {
          name: 'organization', alias_name: '组织', type: 'string', filterType: 'filter', value: null,
          inputMode: 'organization',
        },
      ]),
    ]);
    expect(scanned.map((item) => item.id).sort()).toEqual(['organization__string', 'time__timeRange']);
    expect(scanned.every((item) => item.componentCount === 2)).toBe(true);
  });

  it('feeds a chart only the filter row whose option source matches its parameter', () => {
    const room = roomSource();
    const other = roomSource('monitor/get_rooms');
    const definitions: UnifiedFilterDefinition[] = [
      {
        id: 'server_room_id__string',
        key: 'server_room_id',
        name: '机房',
        type: 'string',
        defaultValue: null,
        order: 0,
        enabled: true,
        inputConfig: room,
      },
      {
        id: 'server_room_id__string__abcd1234',
        key: 'server_room_id',
        name: '机房 · monitor',
        type: 'string',
        defaultValue: null,
        order: 1,
        enabled: true,
        inputConfig: other,
      },
    ];
    const params = processDataSourceParams({
      sourceParams: [{
        name: 'server_room_id',
        alias_name: '机房',
        type: 'string',
        filterType: 'filter',
        value: 'local-default',
        inputConfig: other,
      }],
      unifiedFilterValues: {
        'server_room_id__string': 'room-a',
        'server_room_id__string__abcd1234': 'room-b',
      },
      filterBindings: {
        'server_room_id__string': true,
        'server_room_id__string__abcd1234': true,
      },
      filterDefinitions: definitions,
    });
    expect(params.server_room_id).toBe('room-b');
  });
});
