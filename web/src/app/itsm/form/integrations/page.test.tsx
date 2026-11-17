import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page from './page';
import type { IntegrationItem } from './helpers';
const api = vi.hoisted(() => ({ ready: true, listIntegrations: vi.fn(), integrationCatalog: vi.fn(), getIntegration: vi.fn(), saveIntegration: vi.fn(), testIntegration: vi.fn(), retryDelivery: vi.fn() }));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/app/system-manager/(pages)/settings/openapi-docs/OpenApiDocsDetail', () => ({ default: () => <div>平台参数文档</div> }));
vi.mock('../../components/itsm-list-table', () => ({ default: ({ dataSource, columns }: { dataSource: IntegrationItem[]; columns: { key: string; dataIndex?: keyof IntegrationItem; render?: (v: unknown, row: IntegrationItem) => React.ReactNode }[] }) => <div>{dataSource.map(row => <div key={row.id}>{columns.map(column => <span key={column.key}>{column.render ? column.render(undefined, row) : String(row[column.dataIndex!] || '')}</span>)}</div>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
const item: IntegrationItem = { id: 1, name: '查询工单', kind: 'api', is_enabled: true, config: { path: 'itsm/query', method: 'POST' }, updated_by: 'owner' };
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  api.listIntegrations.mockResolvedValue({ items: [item], can_add: true, can_edit: true });
  api.integrationCatalog.mockResolvedValue({ services: [] });
  api.getIntegration.mockResolvedValue({ ...item, runs: [], deliveries: [] });
  api.testIntegration.mockResolvedValue({ status: 'done', code: '', duration_ms: 1, output: { count: 2 } });
});
it('按名称筛选并隔离不同类型', async () => {
  render(<Page />); await screen.findByText('查询工单');
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索集成' }), { target: { value: '不存在' } });
  expect(screen.queryByText('查询工单')).toBeNull();
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索集成' }), { target: { value: '' } });
  fireEvent.click(screen.getByRole('tab', { name: /Python 脚本/ }));
  expect(screen.queryByText('查询工单')).toBeNull();
  expect(screen.getByRole('button', { name: '新建' })).toBeTruthy();
});
it('只读用户不能新增或执行', async () => {
  api.listIntegrations.mockResolvedValue({ items: [item], can_add: false, can_edit: false });
  render(<Page />); await screen.findByText('查询工单');
  expect(screen.queryByRole('button', { name: '新建' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '记录' }));
  const run = await screen.findByRole('button', { name: /执行测试/ });
  expect((run as HTMLButtonElement).disabled).toBe(true);
});
it('调试提交 JSON 参数并显示结果', async () => {
  render(<Page />); await screen.findByText('查询工单');
  fireEvent.click(screen.getByRole('button', { name: '调试 / 记录' }));
  const input = await screen.findByRole('textbox', { name: '调试参数' });
  fireEvent.change(input, { target: { value: '{"q":"申请"}' } });
  fireEvent.click(screen.getByRole('button', { name: /执行测试/ }));
  await waitFor(() => expect(api.testIntegration).toHaveBeenCalledWith(1, { q: '申请' }));
  await screen.findByText(/"count": 2/);
});

it('外部 API 配置入口与平台网关分开', async () => {
  render(<Page />); await screen.findByText('查询工单');
  fireEvent.click(screen.getByRole('button', { name: '新建' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'API 来源' }));
  fireEvent.click(await screen.findByText('外部 API', { selector: '.ant-select-item-option-content' }));
  fireEvent.change(screen.getByRole('textbox', { name: '集成名称' }), { target: { value: '外部查询' } });
  fireEvent.change(screen.getByRole('textbox', { name: '外部 API 地址' }), { target: { value: 'https://api.example.com/items' } });
  fireEvent.click(screen.getByRole('button', { name: /确\s*定|OK/ }));
  await waitFor(() => expect(api.saveIntegration).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ transport: 'external', method: 'GET', url: 'https://api.example.com/items' }) }), undefined));
});
