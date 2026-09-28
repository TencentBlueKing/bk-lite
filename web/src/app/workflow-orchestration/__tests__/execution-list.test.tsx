import './test-mocks';

import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { StrictMode } from 'react';
import { vi } from 'vitest';

import { ExecutionListPage } from '../components/execution-list-page';

const mocks = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  return { get, post, push: vi.fn(), replace: vi.fn(), searchParams: '', api: { get, post, patch: vi.fn() } };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  useSearchParams: () => new URLSearchParams(mocks.searchParams),
}));

vi.mock('@/utils/request', () => ({
  default: () => mocks.api,
}));

const execution = {
  id: 'execution-1', workflow: 1, workflow_name: '生产变更前置检查', workflow_deleted: false,
  workflow_enabled: true, workflow_version: 3, conductor_workflow_id: null,
  status: 'WAITING_APPROVAL', trigger_type: 'FORM', trigger_id: 'trigger-1', mode: 'PRODUCTION',
  has_warnings: false, warning_count: 0,
  input: {}, output: {}, tasks: [], definition_snapshot: { tasks: [] }, resource_snapshot: {},
  target_snapshot: { fields: {}, unique_total: 0 }, atom_executions: [], artifacts: [],
  pending_approval_count: 1, actionable_approval_ids: ['approval-1'], waiting_node_summary: '确认范围',
  error_message: '', termination_reason: '', failed_stage: '', parent_execution: null,
  started_by: 'alice', created_at: '2026-09-02T01:00:00Z', finished_at: null,
  duration_ms: null, updated_at: '2026-09-02T01:00:00Z',
  permission: ['View'],
};

const approvalNode = {
  reference: 'approve_release', name: '确认生产目标范围', task_type: 'HUMAN', task_name: 'approval',
  parent_reference: null, branch_label: null, depth: 0, state: 'ACTIONABLE',
  state_counts: { ACTIONABLE: 1 }, instance_count: 1, actionable_interaction_ids: ['approval-1'], latest_finished_at: null,
};

function page(initialExecutionId?: string, initialNodeReference?: string, initialInstanceId?: string) {
  return <IntlProvider locale="zh-CN" messages={{ 'common.confirm': '确定', 'common.cancel': '取消', 'common.selectAll': '全选', 'common.selected': '已选', 'common.items': '项', 'common.clear': '清除', 'common.total': '共' }}><App><ExecutionListPage initialExecutionId={initialExecutionId} initialNodeReference={initialNodeReference} initialInstanceId={initialInstanceId} /></App></IntlProvider>;
}

function renderPage(initialExecutionId?: string, initialNodeReference?: string, initialInstanceId?: string) {
  return render(page(initialExecutionId, initialNodeReference, initialInstanceId));
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

describe('执行记录统一详情入口', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset(); mocks.post.mockReset(); mocks.push.mockReset(); mocks.replace.mockReset(); mocks.searchParams = '';
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve(execution);
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [approvalNode], default_node_reference: 'approve_release' });
      if (url.includes('/nodes/approve_release/')) return Promise.resolve({
        node: approvalNode, instances: [{ id: 'approval-1', label: '第 1 次', state: 'ACTIONABLE' }],
        selected_instance_id: 'approval-1', execution_info: { status: 'WAITING_APPROVAL', started_at: execution.created_at },
        inputs: {}, outputs: {}, system_context: {}, error: null, audit_events: [], artifacts: [], control: {}, technical: {},
        interaction: { id: 'approval-1', type: 'APPROVAL', status: 'PENDING', title: '确认生产目标范围', description: '核对目标范围', public_context: { target_scope: '生产环境' }, candidate_users: ['alice'], can_act: true, operator: '', decision: '', comment: '', created_at: execution.created_at, due_at: null, handled_at: null },
      });
      return Promise.resolve({ count: 1, items: [execution] });
    });
  });

  it('全部执行与待我审批使用页签，全部列表的审批入口直接打开详情抽屉', async () => {
    const { container } = renderPage();
    const viewButton = await screen.findByRole('button', { name: '审批' });
    expect(screen.getByRole('tab', { name: '全部执行' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: '待我审批' }).getAttribute('aria-selected')).toBe('false');
    expect(screen.queryByText(/待我审批\s*\(/)).toBeNull();
    expect(screen.queryByText('所有流程共用一份执行记录；从某条流程进入时会自动带上流程筛选。')).toBeNull();
    expect(screen.getByTestId('workflow-table-panel').className).not.toContain('border');
    expect(screen.getByTestId('workflow-table-scroll-region').className).toContain('overflow-hidden');
    expect(container.querySelector('main')?.className).toContain('flex-1');
    expect(container.querySelector('main')?.className).toContain('h-full');
    expect(container.querySelector('main')?.className).toContain('p-4');
    expect(container.querySelector('main')?.className).not.toContain('h-[calc(100vh-64px)]');
    expect(screen.getByPlaceholderText('搜索流程名称').closest('.ant-input-search')?.className).toContain('w-[220px]');
    expect(screen.queryByPlaceholderText('状态')).toBeNull();
    expect(screen.queryByPlaceholderText('触发器')).toBeNull();
    expect(screen.getByRole('columnheader', { name: /^状态/ }).querySelector('.ant-table-filter-trigger')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /^触发器/ }).querySelector('.ant-table-filter-trigger')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /^模式/ }).querySelector('.ant-table-filter-trigger')).not.toBeNull();
    expect(screen.queryByText('全部流程')).toBeNull();
    expect(screen.queryByRole('button', { name: '暂停' })).toBeNull();
    expect(screen.queryByRole('button', { name: '终止' })).toBeNull();
    expect(screen.queryByRole('button', { name: '通过' })).toBeNull();
    expect(viewButton.querySelector('.anticon')).toBeNull();
    fireEvent.click(viewButton);
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(screen.getByRole('tab', { name: '全部执行' }).getAttribute('aria-selected')).toBe('true');
    expect(await screen.findByText('执行详情')).not.toBeNull();
  });

  it('系统发起人显示为双语映射文案', async () => {
    mocks.get.mockImplementation((url: string) => {
      if (String(url).includes('/executions/?')) {
        return Promise.resolve({
          count: 1,
          items: [{ ...execution, started_by: 'workflow-scheduler', trigger_type: 'SCHEDULE', status: 'SUCCEEDED', actionable_approval_ids: [] }],
        });
      }
      return Promise.resolve({ count: 0, items: [] });
    });
    renderPage();
    expect(await screen.findByText('定时调度')).not.toBeNull();
    expect(screen.queryByText('workflow-scheduler')).toBeNull();
    expect(screen.getByText('定时')).not.toBeNull();
  });

  it('待我审批页签写入路由并请求个人可处理的执行', async () => {
    renderPage();
    const mineTab = await screen.findByRole('tab', { name: '待我审批' });
    expect(mineTab.getAttribute('aria-selected')).toBe('false');
    mocks.get.mockClear();

    fireEvent.click(mineTab);

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('mine=1'),
      expect.anything(),
    ));
    expect(mocks.replace).toHaveBeenCalledWith('/workflow-orchestration/executions?scope=mine');
    expect(mineTab.getAttribute('aria-selected')).toBe('true');
    expect(mocks.get.mock.calls.some(([url]) => String(url).includes('/pending-count/'))).toBe(false);
  });

  it('顶部通知在当前页改变 scope 时也会切换到待我审批', async () => {
    const result = renderPage();
    await screen.findByRole('button', { name: '审批' });
    mocks.get.mockClear();

    mocks.searchParams = 'scope=mine';
    result.rerender(page());

    await waitFor(() => expect(screen.getByRole('tab', { name: '待我审批' }).getAttribute('aria-selected')).toBe('true'));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('mine=1'), expect.anything()));
  });

  it('触发器表头筛选使用服务端列表查询', async () => {
    renderPage();
    await screen.findByRole('button', { name: '审批' });
    mocks.get.mockClear();

    const filterTrigger = screen.getByRole('columnheader', { name: /^触发器/ }).querySelector<HTMLElement>('.ant-table-filter-trigger');
    expect(filterTrigger).not.toBeNull();
    fireEvent.click(filterTrigger!);

    const dropdown = await waitFor(() => {
      const element = document.querySelector<HTMLElement>('.ant-table-filter-dropdown');
      expect(element).not.toBeNull();
      return element!;
    });
    fireEvent.click(within(dropdown).getByText('表单'));
    fireEvent.click(within(dropdown).getByRole('button', { name: /OK|确定/ }));

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('trigger_type=FORM'),
      expect.anything(),
    ));
  });

  it('模式表头筛选使用服务端列表查询', async () => {
    renderPage();
    await screen.findByRole('button', { name: '审批' });
    mocks.get.mockClear();

    const filterTrigger = screen.getByRole('columnheader', { name: /^模式/ }).querySelector<HTMLElement>('.ant-table-filter-trigger');
    expect(filterTrigger).not.toBeNull();
    fireEvent.click(filterTrigger!);

    const dropdown = await waitFor(() => {
      const element = document.querySelector<HTMLElement>('.ant-table-filter-dropdown');
      expect(element).not.toBeNull();
      return element!;
    });
    fireEvent.click(within(dropdown).getByText('调试'));
    fireEvent.click(within(dropdown).getByRole('button', { name: /OK|确定/ }));

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('mode=DEBUG'),
      expect.anything(),
    ));
  });

  it('待我审批页签内点击审批打开详情抽屉', async () => {
    mocks.searchParams = 'scope=mine';
    const { container } = renderPage();
    const viewButton = await screen.findByRole('button', { name: '审批' });
    const initialListRequests = mocks.get.mock.calls.filter(([url]) => String(url).includes('/executions/?')).length;

    fireEvent.click(viewButton);
    await screen.findByText('执行详情');

    expect(mocks.replace).not.toHaveBeenCalled();
    expect(mocks.get.mock.calls.filter(([url]) => String(url).endsWith('/executions/execution-1/'))).toHaveLength(1);
    expect(mocks.get.mock.calls.filter(([url]) => String(url).endsWith('/executions/execution-1/nodes/'))).toHaveLength(1);

    const closeButton = container.ownerDocument.querySelector<HTMLButtonElement>('.ant-drawer-close');
    expect(closeButton).not.toBeNull();
    fireEvent.click(closeButton!);

    await waitFor(() => expect(screen.queryByText('执行详情')).toBeNull());
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.get.mock.calls.filter(([url]) => String(url).includes('/executions/?'))).toHaveLength(initialListRequests);

    fireEvent.click(viewButton);
    await screen.findByText('执行详情');
    expect(mocks.get.mock.calls.filter(([url]) => String(url).endsWith('/executions/execution-1/'))).toHaveLength(2);
    expect(mocks.get.mock.calls.filter(([url]) => String(url).endsWith('/executions/execution-1/nodes/'))).toHaveLength(2);
    expect(mocks.get.mock.calls.filter(([url]) => String(url).includes('/executions/?'))).toHaveLength(initialListRequests);
  });

  it('详情抽屉定位审批节点，并将终止和审批放在详情上下文', async () => {
    renderPage('execution-1', 'approve_release', 'approval-1');
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      '/workflow_orchestration/api/executions/execution-1/nodes/approve_release/?instance_id=approval-1',
      expect.anything(),
    ));
    expect(await screen.findByText('执行详情')).not.toBeNull();
    expect(await screen.findAllByText('确认生产目标范围')).not.toHaveLength(0);
    const approvalNodeButton = screen.getByRole('button', { name: '查看节点 确认生产目标范围' });
    expect(approvalNodeButton.getAttribute('aria-current')).toBe('step');
    expect(await screen.findByRole('button', { name: '通过审批' })).not.toBeNull();
    const approvalActions = screen.getByTestId('approval-actions');
    expect(approvalActions.className).toContain('mt-1');
    expect(screen.getByRole('button', { name: '通过审批' }).closest('[data-instance-permissions]')).not.toBeNull();
    expect(screen.getByText('审批上下文')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /终止/ }));
    const terminateReason = await screen.findByPlaceholderText('请输入终止原因');
    const terminateModal = terminateReason.closest('.ant-modal-content');
    expect((terminateModal?.querySelector('.ant-modal-footer') as HTMLElement | null)?.style.marginTop).toBe('20px');
    expect(screen.queryByRole('button', { name: '暂停' })).toBeNull();
  });

  it('左侧切换流程节点，右侧只展示当前节点且不暴露技术信息', async () => {
    const finishNode = {
      ...approvalNode,
      reference: 'finish_release',
      name: '结束发布',
      task_type: 'SIMPLE',
      task_name: 'release',
      state: 'SUCCESS',
      state_counts: { SUCCESS: 1 },
      actionable_interaction_ids: [],
      latest_finished_at: '2026-09-02T01:01:00Z',
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve({ ...execution, status: 'SUCCEEDED' });
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [approvalNode, finishNode], default_node_reference: 'approve_release' });
      if (url.includes('/nodes/approve_release/')) return Promise.resolve({
        node: { ...approvalNode, state: 'SUCCESS' }, instances: [], selected_instance_id: null,
        execution_info: { status: 'SUCCEEDED' }, inputs: { first_input: true }, outputs: { first_result: '审批已完成' },
        system_context: {}, error: null, audit_events: [], artifacts: [], control: {}, interaction: null,
        technical: { workflow_id: 'internal-secret' },
      });
      if (url.includes('/nodes/finish_release/')) return Promise.resolve({
        node: finishNode, instances: [], selected_instance_id: null,
        execution_info: { status: 'SUCCEEDED' }, inputs: {}, outputs: { second_result: '流程已结束' },
        system_context: {}, error: null, audit_events: [], artifacts: [], control: {}, interaction: null,
        technical: { execution_id: 'internal-execution-id' },
      });
      return Promise.resolve({ count: 1, items: [{ ...execution, status: 'SUCCEEDED' }] });
    });

    renderPage('execution-1');

    expect(await screen.findByText('流程节点')).not.toBeNull();
    const firstOutput = await screen.findByText(/first_result/);
    expect(firstOutput.closest('pre')?.className).not.toContain('max-h-64');
    expect(firstOutput.closest('pre')?.className).toContain('w-full');
    expect(firstOutput.closest('pre')?.className).toContain('max-w-full');
    expect(screen.getByTestId('execution-detail-content').className).toContain('min-w-0');
    expect(screen.getByTestId('execution-detail-content').className).toContain('overflow-hidden');
    expect(screen.getByRole('region', { name: '节点详情' }).className).toContain('overflow-x-hidden');
    expect(screen.queryByText('技术信息')).toBeNull();
    expect(screen.queryByText(/internal-secret/)).toBeNull();
    expect(screen.queryByText('approve_release')).toBeNull();
    expect(screen.getAllByText('状态').length).toBeGreaterThan(0);
    expect(screen.getAllByText('成功').length).toBeGreaterThan(0);
    expect(screen.getAllByText('表单').length).toBeGreaterThan(0);

    const finishNodeButton = screen.getByRole('button', { name: '查看节点 结束发布' });
    fireEvent.click(finishNodeButton);

    expect(await screen.findByText(/second_result/)).not.toBeNull();
    await waitFor(() => expect(screen.queryByText(/first_result/)).toBeNull());
    expect(finishNodeButton.getAttribute('aria-current')).toBe('step');
    expect(screen.queryByText(/internal-execution-id/)).toBeNull();
    expect(screen.queryByText('finish_release')).toBeNull();
  });

  it('执行详情隐藏引擎结束节点，且默认选中最后一个用户节点', async () => {
    const approvalDecisionNode = {
      ...approvalNode,
      reference: 'approval_decision',
      name: '审批结果',
      task_type: 'SWITCH',
      task_name: 'approval_decision',
      state: 'SUCCESS',
      actionable_interaction_ids: [],
    };
    const documentNode = {
      ...approvalNode,
      reference: 'document_render',
      name: '文档生成',
      task_type: 'SIMPLE',
      task_name: 'bklite_document_render',
      state: 'SUCCESS',
      actionable_interaction_ids: [],
    };
    const endNode = {
      ...documentNode,
      reference: '__end__',
      name: '结束',
      task_type: 'END',
      task_name: 'end',
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve({ ...execution, status: 'SUCCEEDED' });
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [approvalNode, approvalDecisionNode, documentNode, endNode], default_node_reference: '__end__' });
      if (url.includes('/nodes/document_render/')) return Promise.resolve({
        node: documentNode, instances: [], selected_instance_id: null,
        execution_info: { status: 'SUCCEEDED' }, inputs: {}, outputs: { artifact: { id: 'artifact-1' } },
        system_context: {}, error: null, audit_events: [], artifacts: [{
          id: 'artifact-1', format: 'xlsx', filename: 'inspection.xlsx', size: 1024,
          summary: {}, expires_at: '2026-10-01T00:00:00Z', download_url: '/download/artifact-1',
        }], control: {}, interaction: null, technical: {},
      });
      return Promise.resolve({ count: 1, items: [{ ...execution, status: 'SUCCEEDED' }] });
    });

    renderPage('execution-1');

    expect(await screen.findByRole('button', { name: '查看节点 文档生成' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: '查看节点 结束' })).toBeNull();
    expect(screen.queryByRole('button', { name: '查看节点 审批结果' })).toBeNull();
    expect(screen.getByText('2 / 2')).not.toBeNull();
    expect(screen.getByRole('button', { name: '查看节点 文档生成' }).getAttribute('aria-current')).toBe('step');
    expect(await screen.findByText('inspection.xlsx')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '预览' })).toBeNull();
    expect(screen.getByRole('button', { name: /下载/ })).not.toBeNull();
    expect(mocks.get).not.toHaveBeenCalledWith(expect.stringContaining('/nodes/__end__/'), expect.anything());
  });

  it('切换节点时取消旧请求、显示详情 loading 并在切回时重新请求', async () => {
    const firstNode = { ...approvalNode, state: 'SUCCESS', actionable_interaction_ids: [] };
    const finishNode = {
      ...firstNode,
      reference: 'finish_release',
      name: '结束发布',
      task_type: 'SIMPLE',
      task_name: 'release',
    };
    const firstRequest = deferred<Record<string, unknown>>();
    const finishRequest = deferred<Record<string, unknown>>();
    let firstSignal: AbortSignal | undefined;
    let firstRequestCount = 0;
    const detail = (node: typeof firstNode, outputs: Record<string, unknown>) => ({
      node, instances: [], selected_instance_id: null, execution_info: { status: 'SUCCEEDED' }, inputs: {}, outputs,
      system_context: {}, error: null, audit_events: [], artifacts: [], control: {}, interaction: null, technical: {},
    });
    mocks.get.mockImplementation((url: string, options?: { signal?: AbortSignal }) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve({ ...execution, status: 'SUCCEEDED' });
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [firstNode, finishNode], default_node_reference: 'approve_release' });
      if (url.includes('/nodes/approve_release/')) {
        firstRequestCount += 1;
        firstSignal = options?.signal;
        return firstRequestCount === 1 ? firstRequest.promise : Promise.resolve(detail(firstNode, { first_result: '已重新加载' }));
      }
      if (url.includes('/nodes/finish_release/')) return finishRequest.promise;
      return Promise.resolve({ count: 1, items: [{ ...execution, status: 'SUCCEEDED' }] });
    });

    renderPage('execution-1');
    const finishNodeButton = await screen.findByRole('button', { name: '查看节点 结束发布' });
    await waitFor(() => expect(firstSignal).toBeDefined());

    fireEvent.click(finishNodeButton);

    await waitFor(() => expect(firstSignal?.aborted).toBe(true));
    const detailRegion = screen.getByRole('region', { name: '节点详情' });
    expect(detailRegion.getAttribute('aria-busy')).toBe('true');

    await act(async () => { finishRequest.resolve(detail(finishNode, { second_result: '流程已结束' })); });
    expect(await within(detailRegion).findByText(/second_result/)).not.toBeNull();
    expect(detailRegion.getAttribute('aria-busy')).toBe('false');

    await act(async () => { firstRequest.resolve(detail(firstNode, { stale_result: '过期响应' })); });
    expect(within(detailRegion).queryByText(/stale_result/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '查看节点 确认生产目标范围' }));
    await waitFor(() => expect(firstRequestCount).toBe(2));
    expect(await within(detailRegion).findByText(/first_result/)).not.toBeNull();
  });

  it('关闭抽屉时取消未完成的节点详情请求', async () => {
    const pendingDetail = deferred<Record<string, unknown>>();
    let detailSignal: AbortSignal | undefined;
    mocks.get.mockImplementation((url: string, options?: { signal?: AbortSignal }) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve(execution);
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [approvalNode], default_node_reference: 'approve_release' });
      if (url.includes('/nodes/approve_release/')) {
        detailSignal = options?.signal;
        return pendingDetail.promise;
      }
      return Promise.resolve({ count: 1, items: [execution] });
    });

    const { container } = renderPage('execution-1');
    await screen.findByRole('button', { name: '查看节点 确认生产目标范围' });
    await waitFor(() => expect(detailSignal).toBeDefined());

    const closeButton = container.ownerDocument.querySelector<HTMLButtonElement>('.ant-drawer-close');
    fireEvent.click(closeButton!);

    await waitFor(() => expect(detailSignal?.aborted).toBe(true));
    await waitFor(() => expect(screen.queryByText('执行详情')).toBeNull());
  });

  it('首次进入抽屉时 loading 占满内容区并水平垂直居中', async () => {
    const pendingExecution = deferred<typeof execution>();
    const pendingNodes = deferred<{ nodes: typeof approvalNode[]; default_node_reference: string }>();
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/executions/execution-1/')) return pendingExecution.promise;
      if (url.endsWith('/executions/execution-1/nodes/')) return pendingNodes.promise;
      return Promise.resolve({ count: 1, items: [execution] });
    });

    renderPage('execution-1');

    const loadingRegion = await screen.findByTestId('execution-detail-initial-loading');
    expect(loadingRegion.className).toContain('h-full');
    expect(loadingRegion.className).toContain('w-full');
    expect(loadingRegion.className).toContain('flex-1');
    expect(loadingRegion.className).toContain('items-center');
    expect(loadingRegion.className).toContain('justify-center');
  });

  it('成功执行的非致命告警只在详情中补充说明', async () => {
    const warningNode = { ...approvalNode, state: 'WARNING', actionable_interaction_ids: [] };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve({ ...execution, status: 'SUCCEEDED', has_warnings: true, warning_count: 2 });
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [warningNode], default_node_reference: warningNode.reference });
      if (url.includes('/nodes/approve_release/')) return Promise.resolve({
        node: warningNode, instances: [], selected_instance_id: null, execution_info: { status: 'SUCCEEDED' }, inputs: {}, outputs: { warning_count: 2 },
        system_context: {}, error: null, audit_events: [], artifacts: [], control: {}, interaction: null, technical: {},
      });
      return Promise.resolve({ count: 1, items: [{ ...execution, status: 'SUCCEEDED', has_warnings: true, warning_count: 2 }] });
    });

    renderPage('execution-1');

    const executionSummary = await screen.findByRole('region', { name: '执行概要' });
    const nodeDetail = await screen.findByRole('region', { name: '节点详情' });
    expect(within(executionSummary).queryByText('执行完成，但该节点包含非致命告警')).toBeNull();
    expect(await within(nodeDetail).findByText('执行完成，但该节点包含非致命告警')).not.toBeNull();
    expect(within(nodeDetail).getByTestId('node-detail-content').className).toContain('gap-5');
    expect(within(nodeDetail).getByTestId('node-detail-alerts').className).toContain('gap-3');
    expect(within(nodeDetail).getByRole('region', { name: '输入详情' }).className).toContain('gap-3');
    expect(within(nodeDetail).getByRole('region', { name: '输出详情' }).className).toContain('gap-3');
    expect(within(nodeDetail).getByRole('button', { name: '折叠输入' }).getAttribute('aria-expanded')).toBe('true');
    const outputToggle = within(nodeDetail).getByRole('button', { name: '折叠输出' });
    expect(outputToggle.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(outputToggle);
    expect(within(nodeDetail).getByRole('button', { name: '展开输出' }).getAttribute('aria-expanded')).toBe('false');
    expect(within(nodeDetail).queryByText(/warning_count/)).toBeNull();
    fireEvent.click(within(nodeDetail).getByRole('button', { name: '展开输出' }));
    expect(within(nodeDetail).getByRole('button', { name: '折叠输出' }).getAttribute('aria-expanded')).toBe('true');
    expect(await within(nodeDetail).findByText(/warning_count/)).not.toBeNull();
    expect(screen.getAllByText('成功')).not.toHaveLength(0);
    expect(screen.queryByText('成功（有告警）')).toBeNull();
  });

  it('从流程筛选进入时，列表内打开详情不改写筛选路由', async () => {
    mocks.searchParams = 'query=主机健康巡检';
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/executions/execution-1/')) return Promise.resolve({ ...execution, status: 'SUCCEEDED', actionable_approval_ids: [] });
      if (url.endsWith('/executions/execution-1/nodes/')) return Promise.resolve({ nodes: [approvalNode], default_node_reference: 'approve_release' });
      return Promise.resolve({ count: 1, items: [{ ...execution, status: 'SUCCEEDED', actionable_approval_ids: [] }] });
    });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: '查看' }));
    expect(mocks.replace).not.toHaveBeenCalled();
    expect((screen.getByPlaceholderText('搜索流程名称') as HTMLInputElement).value).toBe('主机健康巡检');
  });

  it('流程名称只在提交搜索后交给列表接口筛选', async () => {
    renderPage();
    await screen.findByRole('button', { name: /审批|查看/ });
    mocks.get.mockClear();

    const search = screen.getByPlaceholderText('搜索流程名称');
    fireEvent.change(search, { target: { value: '健康巡检' } });
    expect(mocks.get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'search' }));

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('query=%E5%81%A5%E5%BA%B7%E5%B7%A1%E6%A3%80'),
      expect.anything(),
    ));
  });

  it('严格模式初始化时列表和详情接口均只请求一次', async () => {
    render(<StrictMode><IntlProvider locale="zh-CN" messages={{ 'common.confirm': '确定', 'common.cancel': '取消', 'common.selectAll': '全选', 'common.selected': '已选', 'common.items': '项', 'common.clear': '清除', 'common.total': '共' }}><App><ExecutionListPage initialExecutionId="execution-1" /></App></IntlProvider></StrictMode>);

    await screen.findByText('执行详情');
    await waitFor(() => {
      const urls = mocks.get.mock.calls.map(([url]) => url);
      expect(urls.filter((url) => url.includes('/executions/?'))).toHaveLength(1);
      expect(urls.filter((url) => url.includes('/workflows/?'))).toHaveLength(0);
      expect(urls.filter((url) => url.endsWith('/executions/execution-1/'))).toHaveLength(1);
      expect(urls.filter((url) => url.endsWith('/executions/execution-1/nodes/'))).toHaveLength(1);
      expect(urls.filter((url) => url.includes('/nodes/approve_release/'))).toHaveLength(1);
    });
  });
});
