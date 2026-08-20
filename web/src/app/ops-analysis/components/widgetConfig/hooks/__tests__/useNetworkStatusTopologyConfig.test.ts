import { describe, expect, it } from 'vitest';
import {
  collectSettledInstancePages,
  keepSelectedNetworkOptions,
  mapNetworkInstanceOptions,
} from '../useNetworkStatusTopologyConfig';

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
        name: 'Core switch',
        modelLabel: '',
      },
    ]);
  });

  it('shows the model name beside the device name', () => {
    expect(
      mapNetworkInstanceOptions(
        [{
          inst_uuid: '123e4567-e89b-42d3-a456-426614174000',
          inst_name: 'Core',
          model_id: 'switch',
        }],
        new Map([['switch', '交换机']]),
      ),
    ).toEqual([
      {
        label: 'Core · 交换机',
        value: '123e4567-e89b-42d3-a456-426614174000',
        name: 'Core',
        modelLabel: '交换机',
      },
    ]);
  });
});

describe('collectSettledInstancePages', () => {
  it('keeps fulfilled model pages when another model fails', () => {
    expect(
      collectSettledInstancePages([
        {
          status: 'fulfilled',
          value: {
            insts: [{ inst_uuid: '123e4567-e89b-42d3-a456-426614174000' }],
            count: 1,
          },
        },
        { status: 'rejected', reason: new Error('model denied') },
      ]),
    ).toEqual({
      insts: [{ inst_uuid: '123e4567-e89b-42d3-a456-426614174000' }],
      total: 1,
    });
  });
});

describe('keepSelectedNetworkOptions', () => {
  it('keeps already selected devices when the listed page changes models', () => {
    expect(
      keepSelectedNetworkOptions(
        ['switch-1', 'router-1'],
        [{ label: 'Core · 交换机', value: 'switch-1' }],
        [{ label: 'GW · 路由器', value: 'router-1' }],
      ),
    ).toEqual([
      { label: 'Core · 交换机', value: 'switch-1' },
      { label: 'GW · 路由器', value: 'router-1' },
    ]);
  });
});
