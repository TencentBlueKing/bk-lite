import assert from 'node:assert/strict';
import { describe, it, vi } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import type { SourceDataRequestOptions } from '@/app/ops-analysis/api/dataSource';
import { createParamInputOptionsLoader } from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';

const dynamicConfig: InputControlConfig = {
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceId: 7,
    valueField: 'id',
    labelField: 'name',
  },
  componentSwitch: true,
};

const asSourceData = (data: unknown) => ({ data, warnings: undefined });

type GetSourceDataByApiId = (
  id: number,
  params?: unknown,
  options?: SourceDataRequestOptions,
) => Promise<ReturnType<typeof asSourceData>>;

describe('paramInputOptionsLoader runtime errors', () => {
  it('preserves business errorMessage when options request fails', async () => {
    const loader = createParamInputOptionsLoader({
      getDataSourceList: async () => [],
      getSourceDataByApiId: async () => {
        throw new HandledRequestError('未找到可用命名空间');
      },
    });

    assert.deepEqual(await loader.load(dynamicConfig).promise, {
      status: 'error',
      options: [],
      errorMessage: '未找到可用命名空间',
    });
  });

  it('passes suppressErrorNotification only when loader option enables it', async () => {
    const getSourceDataByApiId = vi.fn<GetSourceDataByApiId>(
      async () => asSourceData([{ id: 1, name: 'A' }]),
    );
    const suppressed = createParamInputOptionsLoader(
      {
        getDataSourceList: async () => [],
        getSourceDataByApiId,
      },
      () => ({ suppressErrorNotification: true }),
    );
    const normal = createParamInputOptionsLoader({
      getDataSourceList: async () => [],
      getSourceDataByApiId,
    });

    await suppressed.load(dynamicConfig).promise;
    assert.deepEqual(getSourceDataByApiId.mock.calls[0]?.[2], {
      suppressErrorNotification: true,
    });

    getSourceDataByApiId.mockClear();
    await normal.load({
      ...dynamicConfig,
      optionsSource: {
        type: 'dynamic',
        sourceId: 8,
        valueField: 'id',
        labelField: 'name',
      },
    }).promise;
    assert.equal(getSourceDataByApiId.mock.calls[0]?.[2], undefined);
  });

  it('invalidates an unfinished options load when its owner leaves the activation window', async () => {
    let resolveOptions!: (value: ReturnType<typeof asSourceData>) => void;
    const loader = createParamInputOptionsLoader({
      getDataSourceList: async () => [],
      getSourceDataByApiId: () => new Promise((resolve) => {
        resolveOptions = resolve;
      }),
    });

    const first = loader.load(dynamicConfig);
    loader.reset();
    resolveOptions(asSourceData([{ id: 1, name: 'stale' }]));
    assert.equal(await first.promise, null);

    const second = loader.load(dynamicConfig);
    assert.notEqual(second, first);
  });

  it('resolves sourceRef from knownDataSources without listing the catalog', async () => {
    const getDataSourceList = vi.fn(async () => {
      throw new Error('catalog must not be called');
    });
    const getSourceDataByApiId = vi.fn<GetSourceDataByApiId>(
      async () => asSourceData([{ inst_uuid: 'room-1', inst_name: '机房A' }]),
    );
    const loader = createParamInputOptionsLoader(
      {
        getDataSourceList,
        getSourceDataByApiId,
      },
      () => ({
        knownDataSources: [{ id: 42, rest_api: 'cmdb/get_room_list' }],
      }),
    );

    assert.deepEqual(
      await loader.load({
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'cmdb/get_room_list' },
          valueField: 'inst_uuid',
          labelField: 'inst_name',
        },
      }).promise,
      {
        status: 'success',
        options: [{ value: 'room-1', label: '机房A' }],
      },
    );
    assert.equal(getDataSourceList.mock.calls.length, 0);
    assert.equal(getSourceDataByApiId.mock.calls[0]?.[0], 42);
  });

  it('resolves cmdb/get_room_list from the catalog and maps inst_uuid/inst_name', async () => {
    const getDataSourceList = vi.fn(async () => ({
      items: [
        { id: 17, name: 'CMDB 机房列表（选项）', rest_api: 'cmdb/get_room_list' },
      ],
    }));
    const getSourceDataByApiId = vi.fn<GetSourceDataByApiId>(async () => asSourceData({
      items: [
        { inst_uuid: 'room-1', inst_name: '一号机房', _id: 1 },
        { id: 'legacy', name: '旧字段不会成为选项' },
      ],
    }));
    const loader = createParamInputOptionsLoader({
      getDataSourceList,
      getSourceDataByApiId,
    });

    assert.deepEqual(
      await loader.load({
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'cmdb/get_room_list' },
          valueField: 'inst_uuid',
          labelField: 'inst_name',
        },
      }).promise,
      {
        status: 'success',
        options: [{ value: 'room-1', label: '一号机房' }],
      },
    );
    assert.deepEqual(getDataSourceList.mock.calls[0]?.[0], { page_size: -1 });
    assert.equal(getSourceDataByApiId.mock.calls[0]?.[0], 17);
  });

  it('sends resolved query params and skips the request when upstream is empty', async () => {
    const getSourceDataByApiId = vi.fn<GetSourceDataByApiId>(
      async () => asSourceData([{ id: 'dev-1', name: '设备1' }]),
    );
    const loader = createParamInputOptionsLoader({
      getDataSourceList: async () => [],
      getSourceDataByApiId,
    });
    const config: InputControlConfig = {
      control: 'select',
      optionsSource: {
        type: 'dynamic',
        sourceId: 9,
        valueField: 'id',
        labelField: 'name',
        queryParams: { room_id: { ref: 'server_room_id' } },
      },
    };

    const blocked = loader.load(config, { blocked: true });
    assert.equal(blocked.sync, true);
    assert.deepEqual(blocked.initial, { status: 'blocked', options: [] });
    assert.deepEqual(await blocked.promise, { status: 'blocked', options: [] });
    assert.equal(getSourceDataByApiId.mock.calls.length, 0);

    loader.reset();
    assert.deepEqual(await loader.load(config, { resolvedParams: { room_id: 'room-1' } }).promise, {
      status: 'success',
      options: [{ value: 'dev-1', label: '设备1' }],
    });
    assert.deepEqual(getSourceDataByApiId.mock.calls[0]?.[1], { room_id: 'room-1' });
  });

  it('maps a room list returned directly as data, matching get_source_data', async () => {
    const loader = createParamInputOptionsLoader({
      getDataSourceList: async () => ({
        items: [{ id: 17, rest_api: 'cmdb/get_room_list' }],
      }),
      getSourceDataByApiId: async () => asSourceData([
        { inst_uuid: 'room-1', inst_name: '一号机房', _id: 1 },
      ]),
    });

    assert.deepEqual(
      await loader.load({
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'cmdb/get_room_list' },
          valueField: 'inst_uuid',
          labelField: 'inst_name',
        },
      }).promise,
      {
        status: 'success',
        options: [{ value: 'room-1', label: '一号机房' }],
      },
    );
  });
});
