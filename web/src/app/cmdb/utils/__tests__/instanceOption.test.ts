import { describe, expect, it } from 'vitest';

import { toCmdbInstanceOptions } from '@/app/cmdb/utils/instanceOption';

const HOST_UUID = '63e4a531-b6bb-43cc-9eae-8eb8a09f795e';

describe('CMDB 实例选项契约', () => {
  it('实例响应只提供 inst_uuid 时仍生成可选择的 UUID 选项', () => {
    expect(
      toCmdbInstanceOptions([
        {
          inst_uuid: HOST_UUID,
          inst_name: 'host-a',
        },
      ])
    ).toEqual([
      {
        label: 'host-a',
        value: HOST_UUID,
        origin: {
          inst_uuid: HOST_UUID,
          inst_name: 'host-a',
        },
      },
    ]);
  });

  it('缺少合法 inst_uuid 时不回退使用图 _id', () => {
    expect(
      toCmdbInstanceOptions([
        {
          _id: 7,
          inst_name: 'legacy-host',
        },
      ])
    ).toEqual([]);
  });
});
