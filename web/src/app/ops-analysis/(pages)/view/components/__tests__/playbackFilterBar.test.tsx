import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import UnifiedFilterBar from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterBar';
import { ROOM3D_FILTER_ID, ROOM3D_FILTER_INPUT_CONFIG } from '@/app/ops-analysis/utils/room3DScreenFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import ViewWorkspace from '../viewWorkspace';

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
    t: (key: string) => key,
  }),
}));

vi.mock('@/components/ellipsis-with-tooltip', () => ({
  default: ({ text }: { text: string }) => <span>{text}</span>,
}));

vi.mock('@/components/source-origin-badge', () => ({
  default: () => <span>内置</span>,
}));

const canvas = {
  id: '1',
  data_id: '106',
  name: '运维总览',
  type: 'dashboard' as const,
};

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

const builtinRoom: UnifiedFilterDefinition = {
  id: ROOM3D_FILTER_ID,
  key: 'server_room_id',
  name: '机房',
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
  inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
};

const playbackShell = (filterBar: React.ReactNode) => (
  <ViewWorkspace
    selectedItem={canvas}
    titleFallback="画布"
    emptyDescription="空"
    filterBarVisible={false}
    filterBar={filterBar}
  >
    <div>canvas</div>
  </ViewWorkspace>
);

const hiddenShell = (label: string) => {
  const shell = screen.getByText(label).closest('[aria-hidden="true"]');
  expect(shell).toBeTruthy();
  expect(shell?.className).toContain('hidden');
  expect(shell?.hasAttribute('inert')).toBe(true);
  expect(document.querySelector('.ant-select-dropdown')).toBeNull();
  return shell;
};

describe('playback filter bar', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    getDataSourceList.mockReset();
    getSourceDataByApiId.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('stays invisible while writing the dynamic option default', async () => {
    const onSearch = vi.fn();
    const onApplyInitial = vi.fn();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'dev-2', name: '设备2' }],
      warnings: [],
    });

    render(playbackShell(
      <UnifiedFilterBar
        definitions={[room, device]}
        values={{
          [room.id]: 'room-1',
          [device.id]: 'missing',
        }}
        onSearch={onSearch}
        onApplyInitial={onApplyInitial}
      />,
    ));

    await waitFor(() => {
      expect(onApplyInitial).toHaveBeenCalled();
    });
    expect(onApplyInitial.mock.calls.at(-1)?.[0]?.[device.id]).toBeNull();
    expect(onSearch).not.toHaveBeenCalled();
    hiddenShell('设备:');
    expect(screen.getByText('canvas')).toBeTruthy();
  });

  it('stays invisible when builtin room options arrive without searching', async () => {
    const onSearch = vi.fn();
    getDataSourceList.mockResolvedValue({
      items: [
        { id: 17, name: 'CMDB 机房列表（选项）', rest_api: 'cmdb/get_room_list' },
      ],
    });
    getSourceDataByApiId.mockResolvedValue({
      data: {
        items: [
          { inst_uuid: 'room-b', inst_name: '二号机房', _id: 2 },
          { inst_uuid: 'room-a', inst_name: '一号机房', _id: 1 },
        ],
      },
      warnings: [],
    });

    render(playbackShell(
      <UnifiedFilterBar
        definitions={[builtinRoom]}
        values={{}}
        onSearch={onSearch}
      />,
    ));

    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalled();
    });
    expect(await screen.findByText('机房:')).toBeTruthy();
    expect(onSearch).not.toHaveBeenCalled();
    hiddenShell('机房:');
  });

  it('leaves a visible filter bar interactive', () => {
    render(
      <ViewWorkspace
        selectedItem={canvas}
        titleFallback="画布"
        emptyDescription="空"
        filterBar={<div>筛选条</div>}
      >
        <div>canvas</div>
      </ViewWorkspace>,
    );

    const shell = screen.getByText('筛选条').parentElement;
    expect(shell?.className).not.toContain('hidden');
    expect(shell?.hasAttribute('inert')).toBe(false);
    expect(shell?.getAttribute('aria-hidden')).toBeNull();
  });
});
