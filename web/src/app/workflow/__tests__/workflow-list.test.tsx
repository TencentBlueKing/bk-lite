import './test-mocks';

import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { StrictMode } from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkflowListPage } from '../components/workflow-list-page';
import { createCopiedWorkflowName, createDefaultWorkflowName } from '../lib/workflow-draft';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get, post: mocks.post, patch: mocks.patch, del: mocks.del }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({
    selectedGroup: { id: '7', name: '当前组织' },
    flatGroups: [{ id: '7', name: '当前组织' }],
    groupTree: [],
  }),
}));

vi.mock('@/components/group-tree-select', () => ({
  default: ({
    id,
    value,
    onChange,
    disabled,
  }: {
    id?: string;
    value?: number[];
    onChange?: (value: number[]) => void;
    disabled?: boolean;
  }) => (
    <input
      id={id}
      aria-label="组织"
      disabled={disabled}
      value={Array.isArray(value) ? value.join(',') : ''}
      onChange={(event) => onChange?.(event.target.value.split(',').filter(Boolean).map(Number))}
    />
  ),
}));

const workflow = {
  id: 1,
  name: '这是一个用于验证单行省略效果的超长流程名称',
  description: '这是一段超过普通表格单元格展示宽度的流程说明',
  team: [7],
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
  it('新建默认名带到毫秒，复制默认名只带到日期', () => {
    const now = new Date(2026, 8, 9, 10, 19, 10, 372);
    expect(createDefaultWorkflowName(now)).toBe('流程20260909101910372');
    expect(createCopiedWorkflowName('主机巡检', now)).toBe('主机巡检20260909');
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
    mocks.patch.mockReset();
    mocks.del.mockReset();
    mocks.push.mockReset();
    mocks.get.mockResolvedValue({ count: 1, items: [workflow] });
  });

  it('只保留顶部名称搜索，表头承载状态筛选并展示描述和组织', async () => {
    const { container } = renderPage();

    const name = await screen.findByText(workflow.name);
    expect(name.className).toContain('whitespace-nowrap');
    expect(screen.getByRole('columnheader', { name: '描述' })).not.toBeNull();
    expect(screen.getByText(workflow.description).className).toContain('whitespace-nowrap');
    expect(screen.getByRole('columnheader', { name: '组织' })).not.toBeNull();
    expect(screen.getByText('当前组织')).not.toBeNull();
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
    expect(screen.queryByRole('columnheader', { name: /^是否内置/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /^触发器/ })).toBeNull();
    expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('is_builtin=false'), expect.anything());
  });

  it('行内展示高频的编辑和运行，更多菜单按使用频率排列', async () => {
    renderPage();
    await screen.findByText(workflow.name);

    expect(screen.queryByRole('button', { name: workflow.name })).toBeNull();
    expect(screen.getByRole('button', { name: /新建/ }).closest('[class*="gap-2"]')).not.toBeNull();
    expect(screen.getByRole('button', { name: /导出/ })).not.toBeNull();
    expect(screen.getByRole('button', { name: /导入/ })).not.toBeNull();
    expect(screen.queryByRole('button', { name: '执行记录' })).toBeNull();
    const editButton = screen.getByRole('button', { name: /编辑/ });
    expect(editButton).not.toBeNull();
    expect(editButton.querySelector('.anticon')).toBeNull();
    expect(screen.getByRole('button', { name: '运行' })).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: `更多操作：${workflow.name}` }));

    const menu = document.querySelector('.ant-dropdown-menu');
    expect(menu).not.toBeNull();
    if (!menu) return;
    expect(within(menu as HTMLElement).getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['执行记录', '复制', '基本信息', '删除']);
    expect(within(menu as HTMLElement).queryByText('运行')).toBeNull();
    expect(menu.querySelector('.anticon')).toBeNull();
  });

  it('导出走当前选中的流程', async () => {
    window.URL.createObjectURL = vi.fn(() => 'blob:workflow-pack');
    window.URL.revokeObjectURL = vi.fn();
    mocks.post.mockResolvedValue(new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])]));
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    const exportButton = screen.getByRole('button', { name: /导出/ }) as HTMLButtonElement;
    await waitFor(() => expect(exportButton.disabled).toBe(false));
    fireEvent.click(exportButton);

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow/api/workflows/export/',
      { ids: [workflow.id] },
      expect.objectContaining({ responseType: 'blob', suppressErrorNotification: true }),
    ));
    expect(await screen.findByText('已下载流程压缩包')).not.toBeNull();
  });

  it('部分导出下载成功的压缩包，并用弹窗列出失败', async () => {
    window.URL.createObjectURL = vi.fn(() => 'blob:workflow-pack');
    window.URL.revokeObjectURL = vi.fn();
    mocks.post.mockResolvedValue(new Blob([JSON.stringify({
      result: true,
      data: {
        exported: 1,
        failed: [{ name: '模板丢失', reason: '文档模板无法读取' }],
        pack: window.btoa('PK'),
      },
    })]));
    renderPage();
    await screen.findByText(workflow.name);
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    const exportButton = screen.getByRole('button', { name: /导出/ }) as HTMLButtonElement;
    await waitFor(() => expect(exportButton.disabled).toBe(false));
    fireEvent.click(exportButton);

    expect((await screen.findAllByText('导出结果')).length).toBeGreaterThan(0);
    expect(screen.getByText('已导出 1 条，失败 1 条')).not.toBeNull();
    expect(screen.getByText('模板丢失：文档模板无法读取')).not.toBeNull();
    expect(window.URL.createObjectURL).toHaveBeenCalled();
  });

  it('全部导出失败时只弹窗，不下载压缩包', async () => {
    window.URL.createObjectURL = vi.fn(() => 'blob:workflow-pack');
    mocks.post.mockRejectedValue({
      payload: new Blob([JSON.stringify({
        result: false,
        message: '没有可导出的流程',
        data: { exported: 0, failed: [{ name: '999', reason: '流程不存在或无权导出' }] },
      })]),
    });
    renderPage();
    await screen.findByText(workflow.name);
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    const exportButton = screen.getByRole('button', { name: /导出/ }) as HTMLButtonElement;
    await waitFor(() => expect(exportButton.disabled).toBe(false));
    fireEvent.click(exportButton);

    expect((await screen.findAllByText('导出结果')).length).toBeGreaterThan(0);
    expect(screen.getByText('已导出 0 条，失败 1 条')).not.toBeNull();
    expect(screen.getByText('999：流程不存在或无权导出')).not.toBeNull();
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('导入先选择组织和压缩包，确定后才提交', async () => {
    mocks.post.mockResolvedValue({ created: [], failed: [], rebind: [] });
    renderPage();
    await screen.findByText(workflow.name);
    fireEvent.click(screen.getByRole('button', { name: /导入/ }));
    const dialog = (await screen.findByText('流程压缩包')).closest('.ant-modal') as HTMLElement;
    const confirm = within(dialog).getByRole('button', { name: /确\s*定|OK/ }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(mocks.post).not.toHaveBeenCalled();

    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([0x50, 0x4b])], 'workflow-pack.zip', { type: 'application/zip' });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });
    await waitFor(() => expect(confirm.disabled).toBe(false));
    fireEvent.click(confirm);

    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
    const [url, body, config] = mocks.post.mock.calls[0];
    expect(url).toBe('/workflow/api/workflows/import/');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).getAll('team')).toEqual(['7']);
    expect((body as FormData).get('file')).toBeInstanceOf(File);
    expect(config).toEqual(expect.objectContaining({
      headers: { 'Content-Type': 'multipart/form-data' },
      suppressErrorNotification: true,
    }));
  });

  it('超过 200MB 的压缩包在选择时被拦住，不会提交', async () => {
    renderPage();
    await screen.findByText(workflow.name);
    fireEvent.click(screen.getByRole('button', { name: /导入/ }));
    const dialog = (await screen.findByText('流程压缩包')).closest('.ant-modal') as HTMLElement;
    const input = within(dialog).getByRole('button', { name: /选择压缩包/ }).querySelector('input[type="file"]')
      ?? dialog.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([1])], 'workflow-pack.zip', { type: 'application/zip' });
    Object.defineProperty(file, 'size', { value: 200 * 1024 * 1024 + 1 });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(await screen.findByText('流程压缩包不能超过 200MB')).not.toBeNull();
    expect((within(dialog).getByRole('button', { name: /确\s*定|OK/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.post).not.toHaveBeenCalled();
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

  it('表头筛选后翻页仍请求下一页并保留筛选', async () => {
    mocks.get.mockResolvedValue({ count: 40, items: [workflow] });
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
    mocks.get.mockClear();

    const pageTwo = document.querySelector<HTMLElement>('.ant-pagination-item-2');
    expect(pageTwo).not.toBeNull();
    fireEvent.click(pageTwo!);

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringMatching(/page=2.*status=PUBLISHED|status=PUBLISHED.*page=2/),
      expect.anything(),
    ));
  });

  it('流程市场只列出内置流程，查看进入只读，复制说明结果且不发布', async () => {
    const builtin = { ...workflow, is_builtin: true, name: 'Linux 主机巡检（Excel）' };
    const copied = { ...workflow, id: 2, name: '巡检副本', is_builtin: false, current_version: 0, enabled: false };
    mocks.get.mockResolvedValue({ count: 1, items: [builtin] });
    mocks.post.mockResolvedValue(copied);
    render(
      <IntlProvider locale="zh-CN" messages={{ 'common.total': '共', 'common.items': '项' }}>
        <App><WorkflowListPage catalog="market" /></App>
      </IntlProvider>,
    );
    await screen.findByText(builtin.name);

    expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('is_builtin=true'), expect.anything());
    expect(screen.queryByRole('button', { name: /新建/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /导出/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /导入/ })).toBeNull();
    expect(screen.queryByRole('button', { name: '运行' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /^启用状态/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /^发布状态/ })).toBeNull();
    expect(screen.getByRole('columnheader', { name: '描述' })).not.toBeNull();
    expect(screen.queryByRole('columnheader', { name: '组织' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /查看/ }));
    expect(mocks.push).toHaveBeenCalledWith('/workflow/market/1?mode=view');

    fireEvent.click(screen.getByRole('button', { name: '复制到流程' }));
    expect(screen.getByRole('columnheader', { name: '模版名称' })).not.toBeNull();
    expect(screen.queryByRole('columnheader', { name: '流程名称' })).toBeNull();
    expect(await screen.findByText('复制后出现在「流程」里，状态是纯草稿，不会发布，也不会改动这条内置流程。')).not.toBeNull();
    expect((screen.getByLabelText('流程名称') as HTMLInputElement).value).toMatch(/^Linux 主机巡检（Excel）\d{8}$/);
    fireEvent.change(screen.getByLabelText('流程名称'), { target: { value: copied.name } });
    fireEvent.click(screen.getByRole('button', { name: '确认复制' }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/workflow/api/workflows/1/duplicate/', {
      name: copied.name,
      description: builtin.description,
      team: [7],
    }));
    expect(await screen.findByText('已复制为新的纯草稿')).not.toBeNull();
    expect(screen.queryByText(copied.name)).toBeNull();
  });

  it('内置流程操作列展示查看并进入只读模式', async () => {
    mocks.get.mockResolvedValue({ count: 1, items: [{ ...workflow, is_builtin: true }] });
    renderPage();
    await screen.findByText(workflow.name);

    expect(screen.queryByRole('button', { name: /编辑/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /查看/ }));
    expect(mocks.push).toHaveBeenCalledWith('/workflow/workflows/1?mode=view');
  });

  it('启停状态使用独立开关并在变更前确认', async () => {
    mocks.post.mockResolvedValue({ ...workflow, enabled: false });
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getByRole('switch', { name: `启用状态：${workflow.name}` }));
    expect(await screen.findByText('停用该流程？')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /\s*停\s*用\s*/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow/api/workflows/1/enabled/',
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
      if (url.startsWith('/workflow/api/workflows/?')) {
        return Promise.resolve({ count: 1, items: [workflow] });
      }
      if (url === '/workflow/api/workflows/1/launch-plan/') {
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

    expect(await screen.findByText((_, element) => element?.classList.contains('ant-modal-title') === true && element.textContent === '运行流程 - 这是一个用于验证单行省略效果的超长流程名称')).not.toBeNull();
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      '/workflow/api/workflows/1/launch-plan/',
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

  it('新建流程先填写组织、名称和描述，确认后留在列表', async () => {
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getByRole('button', { name: /新建/ }));
    const dialog = (await screen.findByText('新建流程')).closest('.ant-modal') as HTMLElement;
    expect((within(dialog).getByLabelText('组织') as HTMLInputElement).value).toBe('7');
    expect((within(dialog).getByLabelText('流程名称') as HTMLInputElement).value).toMatch(/^流程\d{17}$/);
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText('流程名称'), { target: { value: '新流程' } });
    fireEvent.change(within(dialog).getByLabelText('描述'), { target: { value: '一份说明' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /确\s*定|OK/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/workflow/api/workflows/', {
      name: '新流程',
      description: '一份说明',
      team: [7],
      starter: 'blank',
    }));
    expect(await screen.findByText('已创建为纯草稿')).not.toBeNull();
    expect(mocks.push).not.toHaveBeenCalled();
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
    expect((nameInput as HTMLInputElement).value).toMatch(/^这是一个用于验证单行省略效果的超长流程名称\d{8}$/);
    const duplicateModal = nameInput.closest('.ant-modal-content');
    expect((duplicateModal?.querySelector('.ant-modal-footer') as HTMLElement | null)?.style.marginTop).toBe('20px');
    expect(mocks.post).not.toHaveBeenCalled();

    fireEvent.change(nameInput, { target: { value: copied.name } });
    fireEvent.click(screen.getByRole('button', { name: '确认复制' }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/workflow/api/workflows/1/duplicate/', {
      name: copied.name,
      description: workflow.description,
      team: [7],
    }));
    expect(await screen.findByText('已复制为新的纯草稿')).not.toBeNull();
  });

  it('已发布流程的基本信息可以改名称和描述，组织保持锁定', async () => {
    mocks.patch.mockResolvedValue({ ...workflow, name: '改名后的流程' });
    renderPage();
    await screen.findByText(workflow.name);

    fireEvent.click(screen.getByRole('button', { name: `更多操作：${workflow.name}` }));
    fireEvent.click((await screen.findByText('基本信息')).closest('[role="menuitem"]')!);

    const dialog = (await screen.findByText('编辑流程')).closest('.ant-modal') as HTMLElement;
    expect((within(dialog).getByLabelText('组织') as HTMLInputElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText('流程名称'), { target: { value: '改名后的流程' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /确\s*定|OK/ }));

    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith('/workflow/api/workflows/1/', {
      name: '改名后的流程',
      description: workflow.description,
    }));
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
