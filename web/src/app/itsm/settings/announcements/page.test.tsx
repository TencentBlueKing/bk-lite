import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import Page from './page';

const api = vi.hoisted(() => ({ ready: true, listResources: vi.fn() }));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/itsm/components/itsm-list-table', () => ({ default: ({ dataSource }: { dataSource: { id: number; title: string }[] }) => <div>{dataSource.map(item => <span key={item.id}>{item.title}</span>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);

it('公告按实际启停状态分组，切换分组保留搜索条件', async () => {
  api.listResources.mockResolvedValue({items:[
    {id:1,title:'维护通知',is_enabled:true},
    {id:2,title:'历史通知',is_enabled:false},
  ]});
  render(<Page />); await screen.findByText('维护通知');
  fireEvent.click(screen.getByRole('tab',{name:'停用'}));
  expect(screen.queryByText('维护通知')).toBeNull();
  expect(screen.getByText('历史通知')).toBeTruthy();
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'维护'}});
  expect(screen.queryByText('历史通知')).toBeNull();
  fireEvent.click(screen.getByRole('tab',{name:'启用'}));
  expect(screen.getByText('维护通知')).toBeTruthy();
});
