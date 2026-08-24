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
});
