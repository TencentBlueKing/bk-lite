import { describe, expect, it } from 'vitest';
import { mapNetworkInstanceOptions } from '../useNetworkStatusTopologyConfig';

describe('mapNetworkInstanceOptions', () => {
  it('only maps instances with a valid inst_uuid', () => {
    expect(
      mapNetworkInstanceOptions([
        {
          inst_uuid: '123e4567-e89b-42d3-a456-426614174000',
          inst_name: 'Core switch',
        },
        { inst_name: 'Missing UUID' },
        { inst_uuid: 'undefined', inst_name: 'String undefined' },
        { inst_uuid: 'legacy-id', inst_name: 'Legacy ID' },
        {
          inst_uuid: '123e4567-e89b-12d3-a456-426614174001',
          inst_name: 'UUID v1',
        },
        {
          inst_uuid: '123E4567-E89B-42D3-A456-426614174001',
          inst_name: 'Uppercase UUID',
        },
        { _id: '123e4567-e89b-42d3-a456-426614174002', inst_name: 'Old fallback' },
      ]),
    ).toEqual([
      {
        label: 'Core switch',
        value: '123e4567-e89b-42d3-a456-426614174000',
      },
    ]);
  });
});
