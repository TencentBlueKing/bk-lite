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
});
