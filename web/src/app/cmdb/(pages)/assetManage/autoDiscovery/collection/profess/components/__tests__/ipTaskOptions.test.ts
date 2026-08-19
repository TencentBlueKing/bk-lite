import { describe, expect, it } from 'vitest';

import { toIpTaskSubnetOptions } from '../ipTaskOptions';

describe('IP 发现子网选项', () => {
  it('接口只返回 inst_uuid 时，每个子网仍有唯一的选中值', () => {
    const options = toIpTaskSubnetOptions([
      {
        inst_uuid: '63e4a531-b6bb-43cc-9eae-8eb8a09f795e',
        inst_name: 'zw1',
        prefixlen: 24,
      },
      {
        inst_uuid: '29eeec60-0ab4-451f-8060-9c97a440dabc',
        inst_name: 'zw2',
        prefixlen: 24,
      },
    ]);

    expect(options.map(({ label, value }) => ({ label, value }))).toEqual([
      {
        label: 'zw1',
        value: '63e4a531-b6bb-43cc-9eae-8eb8a09f795e',
      },
      {
        label: 'zw2',
        value: '29eeec60-0ab4-451f-8060-9c97a440dabc',
      },
    ]);
    expect(new Set(options.map((option) => option.value))).toHaveLength(
      options.length
    );
  });
});
