import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import ComponentSelector from '@/app/ops-analysis/components/widgetSelector';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const getDataSourceBriefList = vi.hoisted(() => vi.fn());
const getTagList = vi.hoisted(() => vi.fn());

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceBriefList,
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

const source = (id: number, name: string) => ({
  id,
  name,
  desc: `${name}说明`,
  chart_type: ['line'],
  hasAuth: true,
} as unknown as DatasourceItem);

const regionSource = source(1, '云区域资源分布');
const reportSource = source(2, '报表列表');
const staleSource = source(3, '过期搜索结果');

const briefList = (params?: { search?: string }) => {
  if (params?.search) {
    return [regionSource];
  }
  return [regionSource, reportSource];
};

beforeEach(() => {
  getTagList.mockResolvedValue([{ id: 11, name: 'CMDB' }]);
  getDataSourceBriefList.mockImplementation(async (params?: { search?: string }) => briefList(params));
});

const renderSelector = (visible: boolean) => render(
  <ComponentSelector visible={visible} onCancel={vi.fn()} />,
);

describe('ComponentSelector 搜索重开', () => {
  it('再次打开时关键字已清空，列表回到未搜索结果', async () => {
    const user = userEvent.setup();
    const view = renderSelector(true);

    await screen.findByText('报表列表');
    expect(getDataSourceBriefList).toHaveBeenCalledTimes(1);

    const input = screen.getByPlaceholderText('common.search');
    await user.type(input, '区域{Enter}');

    await waitFor(() => {
      expect(getDataSourceBriefList).toHaveBeenLastCalledWith({
        tags: 11,
        search: '区域',
        page_size: -1,
      });
    });
    expect(screen.queryByText('报表列表')).toBeNull();
    expect(screen.getByText('云区域资源分布')).toBeTruthy();

    view.rerender(<ComponentSelector visible={false} onCancel={vi.fn()} />);
    view.rerender(<ComponentSelector visible onCancel={vi.fn()} />);

    expect((screen.getByPlaceholderText('common.search') as HTMLInputElement).value).toBe('');
    expect(screen.queryByText('云区域资源分布')).toBeNull();
    await screen.findByText('报表列表');
    expect(screen.getByText('云区域资源分布')).toBeTruthy();
    expect(getDataSourceBriefList).toHaveBeenLastCalledWith({
      tags: 11,
      search: undefined,
      page_size: -1,
    });
  });

  it('没有搜索时再次打开沿用已加载列表', async () => {
    const view = renderSelector(true);

    await screen.findByText('报表列表');
    expect(getDataSourceBriefList).toHaveBeenCalledTimes(1);

    view.rerender(<ComponentSelector visible={false} onCancel={vi.fn()} />);
    view.rerender(<ComponentSelector visible onCancel={vi.fn()} />);

    expect(screen.getByText('报表列表')).toBeTruthy();
    expect(getDataSourceBriefList).toHaveBeenCalledTimes(1);
  });

  it('关闭后才返回的搜索结果不会盖过重开后的列表', async () => {
    let resolveSearch: ((rows: DatasourceItem[]) => void) | undefined;
    getDataSourceBriefList.mockImplementation((params?: { search?: string }) => {
      if (params?.search) {
        return new Promise<DatasourceItem[]>((resolve) => {
          resolveSearch = resolve;
        });
      }
      return Promise.resolve([regionSource, reportSource]);
    });

    const user = userEvent.setup();
    const view = renderSelector(true);

    await screen.findByText('报表列表');
    await user.type(screen.getByPlaceholderText('common.search'), '区域{Enter}');
    await waitFor(() => {
      expect(resolveSearch).toEqual(expect.any(Function));
    });

    view.rerender(<ComponentSelector visible={false} onCancel={vi.fn()} />);
    await act(async () => {
      resolveSearch?.([staleSource]);
    });
    expect(screen.queryByText('过期搜索结果')).toBeNull();
    view.rerender(<ComponentSelector visible onCancel={vi.fn()} />);

    await screen.findByText('报表列表');
    expect(screen.queryByText('过期搜索结果')).toBeNull();
  });
});
