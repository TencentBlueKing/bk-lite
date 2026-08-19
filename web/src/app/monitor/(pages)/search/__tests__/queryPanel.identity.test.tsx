import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import QueryPanel from '../queryPanel';
import { transformToFrontendFormat } from '../savedQueryDrawer';

const monitorApi = {
  getMonitorObject: vi.fn(),
  getMonitorPlugin: vi.fn(),
  getMonitorMetrics: vi.fn(),
  getMetricsGroup: vi.fn(),
  getInstanceList: vi.fn(),
};
const viewApi = { getMetricsInstanceQuery: vi.fn() };
let currentSearchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useSearchParams: () => currentSearchParams,
}));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (id: string) => id }),
}));
vi.mock('@/utils/request', () => ({ default: () => ({ isLoading: false }) }));
vi.mock('@/app/monitor/hooks', () => ({ useConditionList: () => [] }));
vi.mock('@/app/monitor/api', () => ({ default: () => monitorApi }));
vi.mock('@/app/monitor/api/view', () => ({ default: () => viewApi }));
vi.mock('../savedQueryDrawer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../savedQueryDrawer')>();
  const SavedQueryDrawerMock = React.forwardRef(() => null);
  SavedQueryDrawerMock.displayName = 'SavedQueryDrawerMock';
  return {
    ...actual,
    default: SavedQueryDrawerMock,
  };
});
vi.mock('../saveQueryModal', () => {
  const SaveQueryModalMock = React.forwardRef(() => null);
  SaveQueryModalMock.displayName = 'SaveQueryModalMock';
  return { default: SaveQueryModalMock };
});

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  currentSearchParams = new URLSearchParams();
  monitorApi.getMonitorObject.mockResolvedValue([
    { id: 12, name: 'host', display_name: '主机', description: '', type: 'os' },
  ]);
  monitorApi.getMonitorPlugin.mockResolvedValue([
    { id: 279, name: 'telegraf', display_name: 'Telegraf' },
    { id: 280, name: 'remote', display_name: '远程采集' },
  ]);
  monitorApi.getMonitorMetrics.mockResolvedValue({ count: 0, items: [] });
  monitorApi.getMetricsGroup.mockResolvedValue({ count: 0, items: [] });
  monitorApi.getInstanceList.mockResolvedValue([]);
  viewApi.getMetricsInstanceQuery.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('监控搜索实体 ID 与下拉选项保持同一类型', () => {
  it('手工选择对象和插件后仍展示名称', async () => {
    const user = userEvent.setup();
    const { container } = render(<QueryPanel onSearch={vi.fn()} />);

    await waitFor(() => expect(monitorApi.getMonitorObject).toHaveBeenCalled());
    const selects = container.querySelectorAll('.ant-select-selector');
    await user.click(selects[0]);
    await user.click(await screen.findByText('主机'));
    expect(selects[0].textContent).toContain('主机');
    expect(selects[0].textContent).not.toBe('12');

    await waitFor(() => expect(monitorApi.getMonitorPlugin).toHaveBeenCalledWith(
      expect.objectContaining({ monitor_object_id: 12 }),
    ));
    const refreshedSelects = container.querySelectorAll('.ant-select-selector');
    await user.click(refreshedSelects[1]);
    await user.click(await screen.findByText('Telegraf'));
    expect(refreshedSelects[1].textContent).toContain('Telegraf');
    expect(refreshedSelects[1].textContent).not.toBe('279');
  });

  it('URL 回填插件时展示名称而不是 ID', async () => {
    currentSearchParams = new URLSearchParams('monitor_object=12&plugin_id=279');
    const { container } = render(<QueryPanel onSearch={vi.fn()} />);

    await waitFor(() => {
      const selects = container.querySelectorAll('.ant-select-selector');
      expect(selects[1]?.textContent).toContain('Telegraf');
    });
  });

  it('兼容历史保存查询中的数字字符串 ID', () => {
    const [group] = transformToFrontendFormat([
      {
        id: 'saved-1',
        name: '历史查询',
        object: '12',
        plugin: '279',
        instance_ids: [],
        metric: '301',
        aggregation: 'AVG',
        conditions: [],
      },
    ]);

    expect(group.object).toBe(12);
    expect(group.plugin).toBe(279);
    expect(group.metric).toBe(301);
  });
});
