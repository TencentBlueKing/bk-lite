import './test-mocks';

import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { StrictMode } from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkflowListPage } from '../components/workflow-list-page';
import { createDefaultWorkflowName } from '../lib/workflow-draft';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get, post: mocks.post, del: mocks.del }),
}));

const workflow = {
  id: 1,
  name: '这是一个用于验证单行省略效果的超长流程名称',
  description: '这是一段超过普通表格单元格展示宽度的流程说明',
  status: 'PUBLISHED',
  current_version: 3,
  enabled: true,
  has_draft: true,
  draft_revision: 4,
  draft_base_version: 3,
  definition: { name: 'workflow_1', schemaVersion: 2, version: 3, tasks: [] },
  canvas_metadata: {},
  engine_name: 'workflow_1',
  trigger_summary: ['FORM', 'SCHEDULE'],
  recent_execution_status: null,
  recent_execution_at: null,
  created_by: 'admin',
  updated_by: 'admin',
  created_at: '2026-09-08T08:00:00Z',
  updated_at: '2026-09-08T09:00:00Z',
};

function renderPage() {
  return render(
    <IntlProvider locale="zh-CN" messages={{ 'common.total': '共', 'common.items': '项' }}>
      <App><WorkflowListPage /></App>
    </IntlProvider>,
  );
}

describe('流程列表', () => {
  it('按本地时间生成毫秒精度的默认流程名', () => {
    expect(createDefaultWorkflowName(new Date(2026, 8, 9, 10, 19, 10, 372))).toBe('流程20260909101910372');
  });

  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.del.mockReset();
    mocks.push.mockReset();
    mocks.get.mockResolvedValue({ count: 1, items: [workflow] });
  });

  it('只保留顶部名称搜索，表头承载状态和触发器筛选', async () => {
    const { container } = renderPage();

    const name = await screen.findByText(workflow.name);
    expect(name.className).toContain('whitespace-nowrap');
    expect(screen.queryByRole('columnheader', { name: '说明' })).toBeNull();
    expect(screen.queryByText(workflow.description)).toBeNull();
    expect(screen.getByRole('columnheader', { name: /^发布状态/ })).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /^启用状态/ })).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: '版本' })).not.toBeNull();
    expect(screen.getByText('v3 · 有未发布更改').className).toContain('whitespace-nowrap');
    expect(screen.getByTestId('workflow-table-panel').className).not.toContain('border');
    expect(screen.getByTestId('workflow-table-scroll-region').className).toContain('overflow-hidden');
    expect(container.querySelector('main')?.className).toContain('flex-1');
    expect(container.querySelector('main')?.className).toContain('h-full');
    expect(container.querySelector('main')?.className).toContain('p-4');
    expect(container.querySelector('main')?.className).not.toContain('h-[calc(100vh-64px)]');
    expect(screen.getByPlaceholderText('搜索流程名称').closest('.ant-input-search')?.className).toContain('w-[220px]');
    expect(screen.queryByPlaceholderText('流程状态')).toBeNull();
    expect(screen.queryByPlaceholderText('触发器')).toBeNull();
    expect(screen.getByRole('columnheader', { name: /^发布状态/ }).querySelector('.ant-table-filter-trigger')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /^启用状态/ }).querySelector('.ant-table-filter-trigger')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /^触发器/ }).querySelector('.ant-table-filter-trigger')).not.toBeNull();
  });

  it('行内展示高频的编辑和运行，更多菜单按使用频率排列', async () => {
    renderPage();
    await screen.findByText(workflow.name);

    expect(screen.queryByRole('button', { name: workflow.name })).toBeNull();
    expect(screen.getByRole('button', { name: /新建流程/ }).closest('[class*="gap-2"]')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '执行记录' })).toBeNull();
    const editButton = screen.getByRole('button', { name: /编辑/ });
    expect(editButton).not.toBeNull();
    expect(editButton.querySelector('.anticon')).toBeNull();
    expect(screen.getByRole('button', { name: '运行' })).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: `更多操作：${workflow.name}` }));

    const menu = document.querySelector('.ant-dropdown-menu');
    expect(menu).not.toBeNull();
    if (!menu) return;
    expect(within(menu as HTMLElement).getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['执行记录', '复制', '删除']);
    expect(within(menu as HTMLElement).queryByText('运行')).toBeNull();
    expect(menu.querySelector('.anticon')).toBeNull();
  });

  it('状态表头筛选使用服务端列表查询', async () => {
    renderPage();
    await screen.findByText(workflow.name);
    mocks.get.mockClear();

    const filterTrigger = screen.getByRole('columnheader', { name: /^发布状态/ }).querySelector<HTMLElement>('.ant-table-filter-trigger');
    expect(filterTrigger).not.toBeNull();
    fireEvent.click(filterTrigger!);

    const dropdown = await waitFor(() => {
      const element = document.querySelector<HTMLElement>('.ant-table-filter-dropdown');
      expect(element).not.toBeNull();
      return element!;
    });
    fireEvent.click(within(dropdown).getByText('已发布'));
    fireEvent.click(within(dropdown).getByRole('button', { name: /OK|确定/ }));

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('status=PUBLISHED'),
      expect.anything(),
    ));
  });

  it('启停状态使用独立开关并在变更前确认', async () => {
    mocks.post.mockResolvedValue({ ...workflow, enabled: false });
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getByRole('switch', { name: `启用状态：${workflow.name}` }));
    expect(await screen.findByText('停用该流程？')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /\s*停\s*用\s*/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/1/enabled/',
      { enabled: false },
    ));
  });

  it('非人工入口仍显示运行按钮但禁用', async () => {
    mocks.get.mockResolvedValue({ count: 1, items: [{ ...workflow, trigger_summary: ['WEBHOOK'] }] });
    renderPage();
    await screen.findByText(workflow.name);

    expect(screen.getByRole('button', { name: '运行' }).hasAttribute('disabled')).toBe(true);
  });

  it('点击运行先打开弹窗，再在弹窗内请求 launch-plan', async () => {
    mocks.get.mockImplementation((url: string) => {
      if (url.startsWith('/workflow_orchestration/api/workflows/?')) {
        return Promise.resolve({ count: 1, items: [workflow] });
      }
      if (url === '/workflow_orchestration/api/workflows/1/launch-plan/') {
        return Promise.resolve({
          workflow_id: 1,
          workflow_name: workflow.name,
          workflow_version: 3,
          input_schema: { type: 'object', properties: {} },
          ui_schema: {},
          target_fields: [],
          risk_summary: {},
          launch_token: 'token',
          expires_in_seconds: 900,
        });
      }
      return Promise.reject(new Error(`unexpected get: ${url}`));
    });
    renderPage();
    await screen.findByText(workflow.name);
    mocks.get.mockClear();

    fireEvent.click(screen.getByRole('button', { name: '运行' }));

    expect(await screen.findByText('运行流程 · 这是一个用于验证单行省略效果的超长流程名称')).not.toBeNull();
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/1/launch-plan/',
      expect.anything(),
    ));
  });

  it('严格模式初始化时列表接口只请求一次', async () => {
    render(
      <StrictMode>
        <IntlProvider locale="zh-CN" messages={{ 'common.total': '共', 'common.items': '项' }}>
          <App><WorkflowListPage /></App>
        </IntlProvider>
      </StrictMode>,
    );

    await screen.findByText(workflow.name);
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
  });

  it('新建流程不弹窗也不请求创建接口，直接携带默认名称进入空白画布', async () => {
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getByRole('button', { name: /新建流程/ }));

    expect(screen.queryByRole('dialog', { name: '新建流程' })).toBeNull();
    expect(mocks.post).not.toHaveBeenCalled();
    const target = mocks.push.mock.calls[0]?.[0] as string;
    expect(target).toMatch(/^\/workflow-orchestration\/workflows\/new\?mode=edit&name=/);
    expect(decodeURIComponent(target.split('name=')[1])).toMatch(/^流程\d{17}$/);
  });

  it('复制流程先填写名称，只有确认后才请求复制接口', async () => {
    const copied = { ...workflow, id: 2, name: '自定义副本' };
    mocks.post.mockResolvedValue(copied);
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getByRole('button', { name: `更多操作：${workflow.name}` }));
    const copyLabel = await screen.findByText('复制');
    fireEvent.click(copyLabel.closest('[role="menuitem"]')!);

    const nameInput = await screen.findByLabelText('流程名称');
    expect((nameInput as HTMLInputElement).value).toBe(`${workflow.name}（副本）`);
    const duplicateModal = nameInput.closest('.ant-modal-content');
    expect((duplicateModal?.querySelector('.ant-modal-footer') as HTMLElement | null)?.style.marginTop).toBe('20px');
    expect(mocks.post).not.toHaveBeenCalled();

    fireEvent.change(nameInput, { target: { value: copied.name } });
    fireEvent.click(screen.getByRole('button', { name: '确认复制' }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/workflow_orchestration/api/workflows/1/duplicate/', { name: copied.name }));
    expect(await screen.findByText('自定义副本')).not.toBeNull();
  });

  it('连续搜索时不逐字请求、取消旧请求并忽略晚到响应', async () => {
    renderPage();
    await screen.findByText(workflow.name);
    mocks.get.mockReset();
    const pending: Array<{
      config?: { signal?: AbortSignal };
      resolve: (value: { count: number; items: typeof workflow[] }) => void;
    }> = [];
    mocks.get.mockImplementation((_url: string, config?: { signal?: AbortSignal }) => new Promise((resolve) => {
      pending.push({ config, resolve });
    }));

    const search = screen.getByPlaceholderText('搜索流程名称');
    fireEvent.change(search, { target: { value: '旧条件' } });
    expect(mocks.get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'search' }));
    await waitFor(() => expect(pending).toHaveLength(1));

    fireEvent.change(search, { target: { value: '新条件' } });
    fireEvent.click(screen.getByRole('button', { name: 'search' }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[0].config?.signal?.aborted).toBe(true);

    const latest = { ...workflow, id: 2, name: '新条件流程' };
    await act(async () => pending[1].resolve({ count: 1, items: [latest] }));
    expect(await screen.findByText(latest.name)).not.toBeNull();

    await act(async () => pending[0].resolve({ count: 1, items: [{ ...workflow, id: 3, name: '旧条件流程' }] }));
    await waitFor(() => expect(screen.queryByText('旧条件流程')).toBeNull());
    expect(screen.getByText(latest.name)).not.toBeNull();
  });
});
