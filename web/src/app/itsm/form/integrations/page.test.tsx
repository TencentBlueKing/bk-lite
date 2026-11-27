import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page from './page';
import Workspace from './workspace';
const router=vi.hoisted(()=>({push:vi.fn(),replace:vi.fn()}));
vi.mock('next/navigation',()=>({useRouter:()=>router}));
import type { IntegrationItem } from './helpers';
const api = vi.hoisted(() => ({ ready: true, listIntegrations: vi.fn(), integrationJobCatalog: vi.fn(), integrationCatalog: vi.fn(), getIntegration: vi.fn(), saveIntegration: vi.fn(), testIntegration: vi.fn(), retryDelivery: vi.fn(), reconcileDelivery: vi.fn() }));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/app/system-manager/(pages)/settings/openapi-docs/OpenApiDocsDetail', () => ({ default: () => <div>平台参数文档</div> }));
vi.mock('../../components/itsm-list-table', () => ({ default: ({ dataSource, columns }: { dataSource: IntegrationItem[]; columns: { key: string; dataIndex?: keyof IntegrationItem; render?: (v: unknown, row: IntegrationItem) => React.ReactNode }[] }) => <div>{dataSource.map(row => <div key={row.id}>{columns.map(column => <span key={column.key}>{column.render ? column.render(column.dataIndex ? row[column.dataIndex] : undefined, row) : String(row[column.dataIndex!] || '')}</span>)}</div>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
const item: IntegrationItem = { id: 1, name: '查询工单', kind: 'api', is_enabled: true, config: { path: 'itsm/query', method: 'POST' }, updated_by: 'owner' };
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear(); api.saveIntegration.mockResolvedValue({id:2});
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
  expect(screen.getByRole('link', { name: '查询工单' }).getAttribute('href')).toBe('/itsm/form/integrations/1/configure');
  fireEvent.click(screen.getByRole('button', { name: '记录' }));
  expect(router.push).toHaveBeenCalledWith('/itsm/form/integrations/1/records');cleanup();render(<Workspace integrationId="1" mode="records" />);
  const run = await screen.findByRole('button', { name: /执行测试/ });
  expect((run as HTMLButtonElement).disabled).toBe(true);
});
it('调试提交 JSON 参数并显示结果', async () => {
  render(<Page />); await screen.findByText('查询工单');
  fireEvent.click(screen.getByRole('button', { name: '调试 / 记录' }));
  expect(router.push).toHaveBeenCalledWith('/itsm/form/integrations/1/records');cleanup();render(<Workspace integrationId="1" mode="records" />);
  const input = await screen.findByRole('textbox', { name: '调试参数' });
  fireEvent.change(input, { target: { value: '{"q":"申请"}' } });
  fireEvent.click(screen.getByRole('button', { name: /执行测试/ }));
  await waitFor(() => expect(api.testIntegration).toHaveBeenCalledWith(1, { q: '申请' }));
  await screen.findByText(/"count": 2/);
});

it('外部 API 配置入口与平台网关分开', async () => {
  render(<Page />); await screen.findByText('查询工单');
  fireEvent.click(screen.getByRole('button', { name: '新建' }));
  expect(router.push).toHaveBeenCalledWith('/itsm/form/integrations/new-api/configure');cleanup();render(<Workspace integrationId="new-api" />);
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'API 来源' }));
  fireEvent.click(await screen.findByText('外部 API', { selector: '.ant-select-item-option-content' }));
  fireEvent.change(screen.getByRole('textbox', { name: '集成名称' }), { target: { value: '外部查询' } });
  fireEvent.change(screen.getByRole('textbox', { name: '外部 API 地址' }), { target: { value: 'https://api.example.com/items' } });
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(api.saveIntegration).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ transport: 'external', method: 'GET', url: 'https://api.example.com/items' }) }), undefined));
});

it('列表不预加载网关目录，调试页仅加载一次所需目录', async () => {
  render(<Page />); await screen.findByText('查询工单');
  expect(api.integrationCatalog).not.toHaveBeenCalled();
  cleanup(); render(<Workspace integrationId="1" mode="records" />);
  await screen.findByRole('textbox', { name: '调试参数' });
  await waitFor(() => expect(api.integrationCatalog).toHaveBeenCalledTimes(1));
});
it('Python 调试不读取无关的网关目录', async () => {
  api.getIntegration.mockResolvedValue({ ...item, kind: 'python', config: { script: '' }, runs: [], deliveries: [] });
  render(<Workspace integrationId="1" mode="records" />);
  await screen.findByRole('textbox', { name: '调试参数' });
  expect(api.integrationCatalog).not.toHaveBeenCalled();
});

it('未知投递必须核对接收结果', async () => {
  api.getIntegration.mockResolvedValue({
    ...item, kind: 'todo', deliveries: [{ id: 42, task_id: 10, status: 'unknown', code: '', attempts: 2, event_key: 'stable-event-id' }],
  });
  render(<Workspace integrationId="1" mode="records" />);
  fireEvent.click(await screen.findByRole('tab', { name: '待办投递' }));
  expect(await screen.findByRole('button', { name: '已核对，接收方已收到' })).toBeTruthy();
  expect(screen.getByRole('button', { name: '已核对，接收方未收到，重新投递' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: '重试' })).toBeNull();
  api.reconcileDelivery.mockResolvedValue({ status: 'done' });
  fireEvent.click(screen.getByRole('button', { name: '已核对，接收方已收到' }));
  expect(api.reconcileDelivery).toHaveBeenCalledWith(1, 42, 2, true);
});

it('作业平台按需加载真实目录、参数和目标数量，仅提供原生入口', async () => {
  api.integrationJobCatalog.mockResolvedValue({
    can_execute: true, scripts: [{ id: 3, name: '资源只读核验', description: '逐台核对规格', params: [{ name: 'size_id', label: '规格', description: '申请的计算配置', type: 'enum', options: ['2C4G'], is_required: true }] }],
    targets: [{ id: 4, name: '本地隔离容器' }],
  });
  render(<Page />);
  await screen.findByText('查询工单');
  expect(api.integrationJobCatalog).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('tab', { name: '作业平台' }));
  expect(await screen.findByText('资源只读核验')).toBeTruthy();
  expect(screen.getByText('逐台核对规格')).toBeTruthy();
  expect(screen.getByText(/可选执行目标.*1/)).toBeTruthy();
  expect(screen.getByText('本地隔离容器')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /查看参数/ }));
  expect(screen.getByText('size_id')).toBeTruthy();
  expect(screen.getByText('申请的计算配置')).toBeTruthy();
  expect(screen.getByText('枚举')).toBeTruthy();
  expect(screen.getByText('2C4G')).toBeTruthy();
  expect(screen.getByRole('link', { name: '测试作业' }).getAttribute('href')).toBe('/job/execution/quick-exec?script_id=3&mode=test');
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.getByRole('link', { name: '脚本库' }).getAttribute('href')).toBe('/job/template/script-library');
  expect(screen.getByRole('link', { name: '执行记录' }).getAttribute('href')).toBe('/job/execution/job-record');
  expect(screen.queryByRole('button', { name: '新建' })).toBeNull();
  expect(screen.queryByRole('button', { name: /调试|执行/ })).toBeNull();
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索作业' }), { target: { value: '不匹配' } });
  expect(screen.queryByText('资源只读核验')).toBeNull();
  expect(api.integrationJobCatalog).toHaveBeenCalledTimes(1);
});

it('查看目录权限不授予测试作业入口', async () => {
  api.integrationJobCatalog.mockResolvedValue({ can_execute: false, scripts: [{id: 9, name: '只读目录', params: []}], targets: [] });
  render(<Page />);
  fireEvent.click(await screen.findByRole('tab', {name: '作业平台'}));
  await screen.findByText('只读目录');
  expect(screen.queryByRole('link', {name: '测试作业'})).toBeNull();
});
