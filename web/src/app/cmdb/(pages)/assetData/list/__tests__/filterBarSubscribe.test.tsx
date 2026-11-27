import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import FilterBar from '../filterBar';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (id: string) =>
      ({
        'FilterBar.filterItems': '检索项',
        'FilterBar.clearConditions': '清空条件',
        'FilterBar.saveFilters': '收藏条件',
        'FilterBar.exact': '精确',
        'subscription.subscribe': '订阅',
      })[id] ?? id,
  }),
}));

vi.mock('@/app/cmdb/api/userConfig', () => ({
  useSavedFiltersApi: () => ({ saveFilters: vi.fn() }),
}));

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: () => ({
    matches: false,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }),
});

afterEach(() => {
  cleanup();
  useAssetDataStore.setState({ query_list: [] });
});

it('映射字段的检索标签显示选项名', () => {
  useAssetDataStore.setState({
    query_list: [
      { field: 'os_type', type: 'list_any[]', value: [1] },
      { field: 'cloud', type: 'int=', value: 0 },
      { field: 'org', type: 'list[]', value: [2] },
    ],
  });
  render(
    <FilterBar
      attrList={[
        {
          attr_id: 'os_type',
          attr_name: '操作系统类型',
          attr_type: 'enum',
          is_required: false,
          editable: true,
          option: [{ id: '1', name: 'Linux' }],
        },
        {
          attr_id: 'cloud',
          attr_name: '云区域',
          attr_type: 'int',
          is_required: false,
          editable: true,
          option: { min_value: '', max_value: '' },
        },
        {
          attr_id: 'org',
          attr_name: '组织',
          attr_type: 'organization',
          is_required: false,
          editable: true,
          option: [],
        },
      ]}
      proxyOptions={[{ proxy_id: '0', proxy_name: 'default' }]}
      groups={[{ id: 2, name: '研发' }]}
    />,
  );

  expect(screen.getByText('Linux')).toBeTruthy();
  expect(screen.getByText('default')).toBeTruthy();
  expect(screen.getByText('研发')).toBeTruthy();
  expect(screen.queryByText('1')).toBeNull();
});

it('keeps subscribe hidden until a filter condition exists', () => {
  render(<FilterBar onSubscribe={vi.fn()} />);
  expect(screen.queryByRole('button', { name: '订阅' })).toBeNull();
});

it('places subscribe to the right of save and opens rule creation for the current filters', () => {
  useAssetDataStore.setState({
    query_list: [{ field: 'bk_name', type: 'str=', value: 'web' }],
  });
  const onSubscribe = vi.fn();
  render(<FilterBar onSubscribe={onSubscribe} />);

  const save = screen.getByRole('button', { name: /收藏条件/ });
  const subscribe = screen.getByRole('button', { name: '订阅' });
  expect(save.compareDocumentPosition(subscribe) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  fireEvent.click(subscribe);
  expect(onSubscribe).toHaveBeenCalledOnce();
});
