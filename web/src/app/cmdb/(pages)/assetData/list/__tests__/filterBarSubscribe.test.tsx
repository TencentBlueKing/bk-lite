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
