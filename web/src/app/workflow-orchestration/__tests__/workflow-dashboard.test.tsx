import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { StrictMode } from 'react';
import { vi } from 'vitest';

import { WorkflowDashboardPage } from '../components/workflow-dashboard-page';

const mocks = vi.hoisted(() => ({ get: vi.fn(), push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/utils/request', () => ({ default: () => ({ get: mocks.get }) }));

describe('编排中心首页', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.push.mockReset();
    mocks.get.mockResolvedValue({
      kpis: {
        workflow_total: 12,
        published_workflows: 8,
        enabled_workflows: 8,
        draft_workflows: 4,
        today_executions: 86,
        success_rate: 94.2,
        running_executions: 2,
        queued_executions: 1,
        failed_executions: 3,
        pending_approvals: 1,
      },
      trend: [],
      status_distribution: [{ status: 'SUCCEEDED', label: '成功', count: 73 }],
      recent_executions: [{
        id: 'execution-recent-1', workflow: 1, workflow_name: '主机健康巡检', workflow_deleted: false,
        workflow_version: 1, status: 'SUCCEEDED', trigger_type: 'FORM', started_by: 'admin',
        created_at: '2026-09-08T00:00:00Z', duration_ms: 1200, permission: ['View'],
      }],
      pending_approvals: [{
        id: 'approval-1', execution: 'execution-1', workflow_name: '生产变更前置检查', workflow_version: 3,
        execution_started_by: '赵明', task_reference: 'approve_release', title: '确认生产目标范围', due_at: null, created_at: '2026-09-08T00:00:00Z',
      }],
    });
  });

  it('还原运行指标、趋势分布、最近执行和待审批，不展示首页说明与新建流程', async () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App><WorkflowDashboardPage /></App></IntlProvider>);

    expect(await screen.findByText('我的待审批')).not.toBeNull();
    expect(screen.getByText('生产变更前置检查')).not.toBeNull();
    expect(screen.getByText('近 7 天执行趋势')).not.toBeNull();
    expect(screen.getByText('执行状态分布')).not.toBeNull();
    expect(screen.getByText('排队中 1')).not.toBeNull();
    expect(screen.getByText('快捷操作')).not.toBeNull();
    expect(screen.getAllByRole('button', { name: '查看并处理' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: '新建流程' })).toBeNull();
    expect(screen.queryByText('关注需要处理的流程运行、审批和发布工作。')).toBeNull();

    const metrics = screen.getByRole('region', { name: '编排运行指标' });
    expect(metrics.className).toContain('grid-cols-6');
    expect(metrics.className).toContain('gap-3');
    expect(metrics.className).not.toContain('md:grid-cols-3');
    expect(metrics.className).not.toContain('xl:grid-cols-6');
    for (const card of within(metrics).getAllByRole('button')) {
      expect(card.className).toContain('w-full');
      expect(card.className).toContain('h-full');
    }

    for (const row of [screen.getByTestId('dashboard-overview-row'), screen.getByTestId('dashboard-detail-row')]) {
      expect(row.className).toContain('grid-cols-3');
      expect(row.className).not.toContain('xl:grid-cols-3');
    }
    expect(screen.getByTestId('dashboard-trend-card').className).toContain('col-span-2');
    expect(screen.getByTestId('dashboard-recent-card').className).toContain('col-span-2');

    const detailRow = screen.getByTestId('dashboard-detail-row');
    expect(detailRow.className).toContain('h-[328px]');
    expect(screen.getByTestId('dashboard-recent-card').className).toContain('h-full');
    expect(screen.getByTestId('dashboard-pending-card').className).toContain('h-full');
    expect(screen.getByTestId('dashboard-pending-list').className).toContain('overflow-y-auto');
    const quickActionsRow = screen.getByTestId('dashboard-quick-actions-row');
    expect(screen.getByTestId('dashboard-quick-actions-grid').className).toContain('grid-cols-3');
    expect(quickActionsRow.nextElementSibling).toBe(screen.getByTestId('dashboard-overview-row'));
  });

  it('KPI 卡片在首页数据加载完成前展示骨架屏', async () => {
    const payload = {
      kpis: {
        workflow_total: 12,
        published_workflows: 8,
        enabled_workflows: 8,
        draft_workflows: 4,
        today_executions: 86,
        success_rate: 94.2,
        running_executions: 2,
        queued_executions: 1,
        failed_executions: 3,
        pending_approvals: 1,
      },
      trend: [],
      status_distribution: [{ status: 'SUCCEEDED', label: '成功', count: 73 }],
      recent_executions: [],
      pending_approvals: [],
    };
    let resolveDashboard: ((value: unknown) => void) | undefined;
    mocks.get.mockImplementation(() => new Promise((resolve) => {
      resolveDashboard = resolve;
    }));

    render(<IntlProvider locale="zh-CN" messages={{}}><App><WorkflowDashboardPage /></App></IntlProvider>);

    const metrics = screen.getByRole('region', { name: '编排运行指标' });
    expect(within(metrics).getAllByTestId('dashboard-metric-skeleton')).toHaveLength(6);
    expect(within(metrics).queryByRole('button', { name: /已发布流程/ })).toBeNull();

    resolveDashboard?.(payload);
    await waitFor(() => expect(within(metrics).queryAllByTestId('dashboard-metric-skeleton')).toHaveLength(0));
    expect(within(metrics).getByRole('button', { name: /已发布流程/ })).not.toBeNull();
  });

  it('严格模式初始化时首页接口只请求一次', async () => {
    render(<StrictMode><IntlProvider locale="zh-CN" messages={{}}><App><WorkflowDashboardPage /></App></IntlProvider></StrictMode>);

    await screen.findByText('我的待审批');
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
  });

  it('最近执行按流程名筛选，待审批统一跳转到待我审批页签', async () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App><WorkflowDashboardPage /></App></IntlProvider>);

    fireEvent.click(await screen.findByRole('button', { name: '详情' }));
    fireEvent.click(screen.getByRole('button', { name: '查看并处理' }));

    expect(mocks.push).toHaveBeenCalledTimes(2);
    const destinations = mocks.push.mock.calls.map(([href]) => new URL(href, 'http://localhost'));
    expect(destinations[0].pathname).toBe('/workflow-orchestration/executions');
    expect(destinations[0].searchParams.get('query')).toBe('主机健康巡检');
    expect(destinations[1].pathname).toBe('/workflow-orchestration/executions');
    expect(destinations[1].searchParams.get('scope')).toBe('mine');
    expect(screen.queryByText('执行详情')).toBeNull();
  });

  it('待我审批指标跳转个人待办筛选', async () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App><WorkflowDashboardPage /></App></IntlProvider>);

    const metrics = await screen.findByRole('region', { name: '编排运行指标' });
    fireEvent.click(within(metrics).getByRole('button', { name: /待我审批/ }));

    expect(mocks.push).toHaveBeenCalledWith('/workflow-orchestration/executions?scope=mine');
  });
});
