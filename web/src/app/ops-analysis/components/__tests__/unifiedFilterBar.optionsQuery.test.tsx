import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import UnifiedFilterBar from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterBar';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

const { getSourceDataByApiId } = vi.hoisted(() => ({
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList: vi.fn(async () => []),
    getSourceDataByApiId,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === 'common.search') return '搜索';
      if (key === 'common.reset') return '重置';
      if (key === 'paramInput.dynamic.upstreamRequired') return '请先选择上游';
      return key;
    },
  }),
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: () => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  getSourceDataByApiId.mockReset();
  vi.useRealTimers();
});

const room: UnifiedFilterDefinition = {
  id: 'room',
  key: 'room_id',
  name: '机房',
  type: 'string',
  order: 0,
  enabled: true,
};

const device: UnifiedFilterDefinition = {
  id: 'device',
  key: 'device_id',
  name: '设备',
  type: 'string',
  order: 1,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      queryParams: { room_id: { ref: 'room' } },
    },
  },
};

const area: UnifiedFilterDefinition = {
  id: 'area',
  key: 'area_id',
  name: '分区',
  type: 'string',
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'radio',
    optionsSource: {
      type: 'static',
      staticItems: [
        { label: '一区', value: 'a1' },
        { label: '二区', value: 'a2' },
      ],
    },
  },
};

const rack: UnifiedFilterDefinition = {
  id: 'rack',
  key: 'rack_id',
  name: '机柜',
  type: 'string',
  order: 1,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 10,
      valueField: 'id',
      labelField: 'name',
      queryParams: { area_id: { ref: 'area' } },
    },
  },
};

describe('UnifiedFilterBar options query', () => {
  it('keeps the text draft immediate, debounces option reloads, and still searches with the draft', async () => {
    vi.useFakeTimers();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'dev-1', name: '设备1' }],
      warnings: [],
    });
    const onSearch = vi.fn();
    render(
      <UnifiedFilterBar
        definitions={[room, device]}
        values={{ room: '', device: null }}
        onSearch={onSearch}
      />,
    );

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: '东' } });
    fireEvent.change(input, { target: { value: '东区' } });
    expect(input).toHaveProperty('value', '东区');
    expect(getSourceDataByApiId).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /搜索/ }));
    expect(onSearch).toHaveBeenCalledWith({ room: '东区', device: null });
    expect(getSourceDataByApiId).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
    expect(getSourceDataByApiId).toHaveBeenCalledWith(9, { room_id: '东区' }, undefined);

    fireEvent.change(input, { target: { value: '' } });
    expect(input).toHaveProperty('value', '');
    expect(screen.getByText('请先选择上游')).not.toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
  });

  it('reloads downstream options as soon as an upstream radio is selected', async () => {
    vi.useFakeTimers();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'rack-1', name: '机柜1' }],
      warnings: [],
    });
    render(
      <UnifiedFilterBar
        definitions={[area, rack]}
        values={{ area: null, rack: null }}
      />,
    );

    expect(getSourceDataByApiId).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('radio', { name: '二区' }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
    expect(getSourceDataByApiId).toHaveBeenCalledWith(10, { area_id: 'a2' }, undefined);
  });
});
