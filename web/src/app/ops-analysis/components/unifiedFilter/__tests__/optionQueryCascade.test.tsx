import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import UnifiedFilterBar from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterBar';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { APPLICATION_TOPOLOGY_FILTER_ID } from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';

const { getDataSourceList, getSourceDataByApiId } = vi.hoisted(() => ({
  getDataSourceList: vi.fn(),
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList,
    getSourceDataByApiId,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === 'paramInput.dynamic.upstreamRequired') return '请先选择上游';
      if (key === 'paramInput.dynamic.invalidUpstream') return '查询入参无法对应到唯一的上游筛选';
      return key;
    },
  }),
}));

const room: UnifiedFilterDefinition = {
  id: 'site_id__string',
  key: 'site_id',
  name: '机房',
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: [{ label: '一号机房', value: 'room-1' }],
    },
  },
};

const device: UnifiedFilterDefinition = {
  id: 'device_id__string',
  key: 'device_id',
  name: '设备',
  type: 'string',
  defaultValue: 'missing',
  order: 1,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      queryParams: { room_id: { ref: 'site_id' } },
    },
  },
};

describe('option query cascade', () => {
  afterEach(() => {
    cleanup();
    getSourceDataByApiId.mockReset();
  });

  it('reloads downstream options from the draft and writes the first correction without searching', async () => {
    const onSearch = vi.fn();
    const onApplyInitial = vi.fn();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'dev-2', name: '设备2' }],
      warnings: [],
    });

    render(
      <UnifiedFilterBar
        definitions={[room, device]}
        values={{
          [room.id]: 'room-1',
          [device.id]: 'missing',
        }}
        onSearch={onSearch}
        onApplyInitial={onApplyInitial}
      />,
    );

    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledWith(9, { room_id: 'room-1' }, undefined);
    });
    await waitFor(() => {
      expect(onApplyInitial).toHaveBeenCalled();
    });
    expect(onSearch).not.toHaveBeenCalled();
    expect(onApplyInitial.mock.calls.at(-1)?.[0]?.[device.id]).toBeNull();
    expect(screen.queryByText('请先选择上游')).toBeNull();
  });

  it('does not request downstream options while the upstream draft is empty', async () => {
    const onSearch = vi.fn();
    render(
      <UnifiedFilterBar
        definitions={[room, device]}
        values={{
          [room.id]: null,
          [device.id]: 'dev-2',
        }}
        onSearch={onSearch}
      />,
    );

    expect(await screen.findByText('请先选择上游')).not.toBeNull();
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
    expect(onSearch).not.toHaveBeenCalled();
  });

  it('uses the draft of the filter id when several rows share a name', async () => {
    const roomOptions = (value: string): UnifiedFilterDefinition['inputConfig'] => ({
      control: 'select',
      optionsSource: { type: 'static', staticItems: [{ label: value, value }] },
    });
    const roomA: UnifiedFilterDefinition = {
      ...room,
      id: 'site_id__string__11111111',
      name: '机房 A',
      inputConfig: roomOptions('room-a'),
    };
    const roomB: UnifiedFilterDefinition = {
      ...room,
      id: 'site_id__string__22222222',
      name: '机房 B',
      order: 1,
      inputConfig: roomOptions('room-b'),
    };
    const byId: UnifiedFilterDefinition = {
      ...device,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceId: 9,
          valueField: 'id',
          labelField: 'name',
          queryParams: { room_id: { ref: roomB.id } },
        },
      },
    };
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'dev-2', name: '设备2' }],
      warnings: [],
    });
    render(
      <UnifiedFilterBar
        definitions={[roomA, roomB, byId]}
        values={{
          [roomA.id]: 'room-a',
          [roomB.id]: 'room-b',
          [byId.id]: null,
        }}
        onSearch={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledWith(9, { room_id: 'room-b' }, undefined);
    });
  });

  it('does not request options when a bare name matches more than one row', async () => {
    const roomA: UnifiedFilterDefinition = {
      ...room,
      id: 'site_id__string__11111111',
    };
    const roomB: UnifiedFilterDefinition = {
      ...room,
      id: 'site_id__string__22222222',
      order: 1,
    };
    render(
      <UnifiedFilterBar
        definitions={[roomA, roomB, device]}
        values={{
          [roomA.id]: 'room-a',
          [roomB.id]: 'room-b',
          [device.id]: 'dev-2',
        }}
        onSearch={vi.fn()}
      />,
    );
    expect(await screen.findByText('查询入参无法对应到唯一的上游筛选')).not.toBeNull();
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
  });

  it('does not search when an application system filter opens', async () => {
    const onSearch = vi.fn();
    const onApplyInitial = vi.fn();
    const system: UnifiedFilterDefinition = {
      id: APPLICATION_TOPOLOGY_FILTER_ID,
      key: 'application_system_id',
      name: '应用系统',
      type: 'string',
      defaultValue: null,
      order: 0,
      enabled: true,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'static',
          staticItems: [{ label: '系统A', value: 'sys-a' }],
        },
      },
    };
    render(
      <UnifiedFilterBar
        definitions={[system]}
        values={{ [system.id]: 'missing' }}
        onSearch={onSearch}
        onApplyInitial={onApplyInitial}
      />,
    );
    await waitFor(() => {
      expect(onApplyInitial).toHaveBeenCalled();
    });
    expect(onSearch).not.toHaveBeenCalled();
    expect(onApplyInitial.mock.calls.at(-1)?.[0]?.[system.id]).toBeNull();
  });

  it('does not auto-search a split server_room_id row', async () => {
    const onSearch = vi.fn();
    const onApplyInitial = vi.fn();
    const splitRoom: UnifiedFilterDefinition = {
      id: 'server_room_id__string__abcd1234',
      key: 'server_room_id',
      name: '机房 · 监控',
      type: 'string',
      defaultValue: null,
      order: 0,
      enabled: true,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'static',
          staticItems: [{ label: '二号机房', value: 'room-b' }],
        },
      },
    };
    render(
      <UnifiedFilterBar
        definitions={[splitRoom]}
        values={{ [splitRoom.id]: 'missing' }}
        onSearch={onSearch}
        onApplyInitial={onApplyInitial}
      />,
    );
    await waitFor(() => {
      expect(onApplyInitial).toHaveBeenCalled();
    });
    expect(onSearch).not.toHaveBeenCalled();
    expect(onApplyInitial.mock.calls.at(-1)?.[0]?.[splitRoom.id]).toBeNull();
  });
});
