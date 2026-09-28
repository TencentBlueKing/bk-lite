import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { vi } from 'vitest';

import { WorkflowLaunchDialog } from '../components/workflow-launch-dialog';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get, post: mocks.post }),
  HandledRequestError: class HandledRequestError extends Error {},
}));

const plan = {
  workflow_id: 1,
  workflow_name: '生产巡检',
  workflow_version: 3,
  input_schema: {
    type: 'object' as const,
    required: ['targets'],
    properties: {
      targets: { type: 'array' as const, title: '目标主机', items: { type: 'string' as const } },
    },
  },
  ui_schema: {},
  target_fields: [{
    key: 'targets',
    name: '目标主机',
    required: true,
    binding_mode: 'runtime' as const,
    allowed_sources: ['node_mgmt', 'job_mgmt'] as const,
    min_count: 1,
    max_count: 100,
  }],
  risk_summary: { description: '启动前重新校验目标。' },
  launch_token: 'launch-token',
  expires_in_seconds: 300,
};

const nodeTarget = {
  id: 'node:node-1',
  source: 'node_mgmt' as const,
  source_id: 'node-1',
  name: 'inspection-linux-01',
  ip: '172.18.0.20',
  operating_system: 'linux' as const,
  connected: true,
};

const jobTarget = {
  id: 'manual:11',
  source: 'job_mgmt' as const,
  source_id: 11,
  name: 'job-linux-01',
  ip: '10.10.41.101',
  operating_system: 'linux' as const,
  connected: true,
};

describe('流程启动目标选择', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({
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
    mocks.get.mockImplementation((url: string) => {
      if (url === '/launch-plan/') return Promise.resolve(plan);
      if (url.includes('source=node_mgmt')) return Promise.resolve({ source: 'node_mgmt', count: 1, items: [nodeTarget] });
      if (url.includes('source=job_mgmt')) return Promise.resolve({ source: 'job_mgmt', count: 1, items: [jobTarget] });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  it('切换目标来源会清空另一来源已选，确认后仅保留当前来源', async () => {
    render(
      <IntlProvider locale="zh-CN" messages={{
        'common.confirm': '确定',
        'common.cancel': '取消',
        'common.selectAll': '全选',
        'common.selected': '已选',
        'common.items': '项',
        'common.clear': '清除',
        'common.total': '共',
        'common.checked': '已选择',
      }}>
        <App>
          <WorkflowLaunchDialog
            open
            title="执行流程"
            planUrl="/launch-plan/"
            submitUrl="/run/"
            onClose={vi.fn()}
            onStarted={vi.fn()}
          />
        </App>
      </IntlProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /请选择目标主机/ }));

    const nodeRow = (await screen.findByText(nodeTarget.name)).closest('tr');
    expect(nodeRow).not.toBeNull();
    fireEvent.click(within(nodeRow!).getByRole('checkbox'));

    expect(screen.getByRole('columnheader', { name: '主机名' })).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: 'IP' })).not.toBeNull();
    expect(screen.queryByRole('columnheader', { name: '状态' })).toBeNull();
    const selectedPreview = screen.getByLabelText('已选项预览');
    expect(within(selectedPreview).getByText(nodeTarget.name)).not.toBeNull();
    expect(within(selectedPreview).queryByText(nodeTarget.ip)).toBeNull();
    expect(screen.getByText(/节点管理与作业平台不能混选/)).not.toBeNull();
    expect(screen.queryByText('批量录入 IP')).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: '作业平台' }));
    await waitFor(() => {
      expect(within(screen.getByLabelText('已选项预览')).queryByText(nodeTarget.name)).toBeNull();
    });

    const jobRow = (await screen.findAllByText(jobTarget.name))
      .map((element) => element.closest('tr'))
      .find(Boolean);
    expect(jobRow).not.toBeNull();
    fireEvent.click(jobRow!.querySelector('input[type="checkbox"]')!);

    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));
    expect(await screen.findByText('已选择 1 台主机')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /已选择 1 台主机/ }));

    await waitFor(() => {
      expect(screen.getAllByText(jobTarget.name).length).toBeGreaterThan(0);
      expect(screen.queryByText(nodeTarget.name)).toBeNull();
      expect(screen.queryByText(jobTarget.id)).toBeNull();
    });
  });

  it('健康巡检启动表单仅要求选择目标和上传用户模板', async () => {
    const healthPlan = {
      ...plan,
      input_schema: {
        type: 'object' as const,
        required: ['targets', 'report_template'],
        properties: {
          ...plan.input_schema.properties,
          report_template: { type: 'object' as const, title: '报告模板', 'x-widget': 'file-upload' as const, 'x-file-options': {
            accept: ['docx', 'xlsx'], maxSizeMiB: 5, maxCount: 1 as const, sourceModes: ['upload'],
            sampleFiles: [
              { name: 'Word', url: '/workflow-orchestration/templates/health-inspection-example.docx' },
              { name: 'Excel', url: '/workflow-orchestration/templates/health-inspection-example.xlsx' },
            ],
          } },
        },
      },
      ui_schema: {
        report_template: { 'ui:widget': 'file-upload' },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url === '/launch-plan/') return Promise.resolve(healthPlan);
      if (url.includes('source=node_mgmt')) return Promise.resolve({ source: 'node_mgmt', count: 1, items: [nodeTarget] });
      if (url.includes('source=job_mgmt')) return Promise.resolve({ source: 'job_mgmt', count: 1, items: [jobTarget] });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
    render(<IntlProvider locale="zh-CN" messages={{}}><App><WorkflowLaunchDialog open title="执行流程" planUrl="/launch-plan/" submitUrl="/run/" onClose={vi.fn()} onStarted={vi.fn()} /></App></IntlProvider>);

    expect(await screen.findByRole('button', { name: /选择 Word \/ Excel 模板/ })).not.toBeNull();
    expect(screen.queryByText('请上传一份报告模板后再启动')).toBeNull();
    expect(screen.getByRole('link', { name: 'Word' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.docx');
    expect(screen.getByRole('link', { name: 'Excel' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.xlsx');
    expect(screen.queryByText('CPU 使用率')).toBeNull();
  });

  it('主启动弹窗关闭时同步关闭目标选择器且不跨会话保留草稿', async () => {
    const renderDialog = (open: boolean) => (
      <IntlProvider locale="zh-CN" messages={{
        'common.confirm': '确定',
        'common.cancel': '取消',
        'common.selectAll': '全选',
        'common.selected': '已选',
        'common.items': '项',
        'common.clear': '清除',
        'common.total': '共',
        'common.checked': '已选择',
      }}>
        <App>
          <WorkflowLaunchDialog
            open={open}
            title="执行流程"
            planUrl="/launch-plan/"
            submitUrl="/run/"
            onClose={vi.fn()}
            onStarted={vi.fn()}
          />
        </App>
      </IntlProvider>
    );
    const view = render(renderDialog(true));

    fireEvent.click(await screen.findByRole('button', { name: /请选择目标主机/ }));
    expect(await screen.findByText('选择主机 · 目标主机')).not.toBeNull();
    const nodeRow = (await screen.findAllByText(nodeTarget.name))
      .map((element) => element.closest('tr'))
      .find(Boolean);
    fireEvent.click(nodeRow!.querySelector('input[type="checkbox"]')!);

    view.rerender(renderDialog(false));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '选择主机 · 目标主机' })).toBeNull());

    view.rerender(renderDialog(true));
    expect(await screen.findByRole('button', { name: /请选择目标主机/ })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /已选择 1 台主机/ })).toBeNull();
  });

  it('填写必填目标后将权威校验和错误提示交给全局请求处理', async () => {
    mocks.post.mockRejectedValue(new Error('接口校验失败'));
    render(
      <IntlProvider locale="zh-CN" messages={{}}>
        <App>
          <WorkflowLaunchDialog
            open
            title="执行流程"
            planUrl="/launch-plan/"
            submitUrl="/run/"
            onClose={vi.fn()}
            onStarted={vi.fn()}
          />
        </App>
      </IntlProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /请选择目标主机/ }));
    const nodeRow = (await screen.findByText(nodeTarget.name)).closest('tr');
    expect(nodeRow).not.toBeNull();
    fireEvent.click(within(nodeRow!).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));
    fireEvent.click(screen.getByRole('button', { name: '启动执行' }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/run/',
      { launch_token: 'launch-token', inputs: { targets: [nodeTarget.id] }, offline_confirmed: false },
    ));
  });
});
