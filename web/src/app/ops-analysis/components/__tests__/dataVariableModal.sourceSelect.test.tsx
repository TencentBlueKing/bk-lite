import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import DataVariableModal from '@/app/ops-analysis/components/dataVariableModal';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const getDataSourceBriefList = vi.hoisted(() => vi.fn());
const getSourceDataByApiId = vi.hoisted(() => vi.fn());
const getTagList = vi.hoisted(() => vi.fn());

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceBriefList,
    getSourceDataByApiId,
  }),
}));

vi.mock('@/app/ops-analysis/api/namespace', () => ({
  useNamespaceApi: () => ({
    getTagList,
  }),
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
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
  vi.clearAllMocks();
});

const source = (
  id: number,
  name: string,
  chartType: DatasourceItem['chart_type'],
  hasAuth = true,
): DatasourceItem => ({
  id,
  name,
  rest_api: `api/${id}`,
  desc: name,
  params: [],
  chart_type: chartType,
  namespaces: [],
  hasAuth,
} as DatasourceItem);

describe('data variable source select', () => {
  it('picks a chartless source from the data source dialog', async () => {
    const mapping = source(9, 'CMDB 实例监控ID映射', []);
    const chart = source(3, '监控实例数量统计', ['single']);
    const locked = source(4, '未授权查询', ['table'], false);
    getTagList.mockResolvedValue([{ id: 1, name: 'CMDB' }]);
    getDataSourceBriefList.mockResolvedValue([mapping, chart, locked]);

    render(
      <DataVariableModal
        open
        variables={[{
          id: 'dv_1',
          name: '监控实例',
          dataSourceId: 0,
          valueField: '',
          params: {},
        }]}
        dataSources={[]}
        filters={[]}
        filterValues={{}}
        widgetConfigs={[]}
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(getDataSourceBriefList).toHaveBeenCalledWith({ page_size: -1 });
    });

    const user = userEvent.setup();
    fireEvent.click(screen.getByRole('button', { name: 'common.edit' }));
    const dataSourceItem = screen.getByText('dashboard.dataSource').closest('.ant-form-item');
    expect(dataSourceItem).toBeTruthy();
    fireEvent.click(within(dataSourceItem as HTMLElement).getByRole('textbox'));

    expect((await screen.findAllByText('CMDB 实例监控ID映射')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('监控实例数量统计').length).toBeGreaterThan(0);
    expect(screen.getAllByText('未授权查询').length).toBeGreaterThan(0);

    await user.click(screen.getAllByText('未授权查询')[0]);
    expect((within(dataSourceItem as HTMLElement).getByRole('textbox') as HTMLInputElement).value).toBe('');

    await user.click(screen.getAllByText('CMDB 实例监控ID映射')[0]);
    expect((within(dataSourceItem as HTMLElement).getByRole('textbox') as HTMLInputElement).value)
      .toBe('CMDB 实例监控ID映射（api/9）');
  }, 15000);
});
