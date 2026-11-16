import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Tables from './tables/page';
import Dictionaries from './dictionaries/page';
import Forms from './page';
const api = vi.hoisted(() => ({ ready: true, listResources: vi.fn(), listDataTables: vi.fn(), listDictionaries: vi.fn(), listForms: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/itsm/components/itsm-list-table', () => ({ default: ({ dataSource }: { dataSource: { id: number; name: string }[] }) => <div role="table">{dataSource.map(item => <span key={item.id}>{item.name}</span>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  Object.values(api).forEach(value => { if (typeof value === 'function') value.mockResolvedValue({ items: [{ id: 1, name: '设备申请', key: 'device', kind: 'http', config: { url: 'https://example.com' } }, { id: 2, name: '账号申请', key: 'account', kind: 'table', config: {} }] }); });
});
it.each([[Tables, '搜索数据表'], [Dictionaries, '搜索数据字典'], [Forms, '搜索表单']] as const)('%s 支持表格上方搜索和清空', async (Page, label) => {
  render(<Page />);
  await screen.findByText('设备申请');
  const search = screen.getByRole('textbox', { name: label });
  fireEvent.change(search, { target: { value: '账号' } });
  expect(screen.queryByText('设备申请')).toBeNull();
  expect(screen.getByText('账号申请')).toBeTruthy();
  fireEvent.change(search, { target: { value: '' } });
  expect(screen.getByText('设备申请')).toBeTruthy();
});
