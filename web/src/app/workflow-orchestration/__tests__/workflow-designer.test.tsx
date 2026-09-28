import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';

import { WorkflowOrchestrationConsole } from '../components/workflow-orchestration-console';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get, patch: mocks.patch, post: mocks.post, del: mocks.del }),
}));

const workflow = {
  id: 1,
  name: '主机健康巡检',
  description: '生成巡检报告',
  status: 'DRAFT',
  current_version: 0,
  enabled: false,
  has_draft: true,
  draft_revision: 0,
  draft_base_version: 0,
  definition: {
    name: 'health-check', version: 1, schemaVersion: 2,
    tasks: [{ name: 'bklite_notification', taskReferenceName: 'notify', type: 'SIMPLE', inputParameters: { notification_type: 'EMAIL', channel_id: 1, recipients: ['1', '5'], title: '巡检完成', body: '完成' } }],
  },
  canvas_metadata: { node_titles: { notify: '发送巡检结果' } },
  engine_name: 'bklite_workflow_1',
  created_by: 'admin', updated_by: 'admin', created_at: '2026-09-03T01:00:00Z', updated_at: '2026-09-03T01:00:00Z',
};

const atoms = [
  {
    key: 'bklite_notification',
    name: '系统通知',
    category: '协作',
    description: '发送通知',
    input_schema: {
      type: 'object',
      properties: {
        notification_type: { type: 'string', title: '通知类型', enum: ['EMAIL'], default: 'EMAIL' },
        channel_id: { type: 'integer', title: '通知渠道', enum: [1], 'x-enum-labels': { 1: '默认邮件渠道' } },
        recipients: {
          type: 'array',
          title: '接收人',
          items: {
            type: 'string',
            enum: ['1', '5'],
            'x-enum-labels': { '1': '管理员 (admin)', '5': '值班工程师 (demo_oncall)' },
            'x-enum-usernames': { '1': 'admin', '5': 'demo_oncall' },
          },
        },
        title: { type: 'string', title: '通知标题' },
        body: { type: 'string', title: '通知内容', 'x-widget': 'textarea' },
        report_artifact: { type: 'object', title: '附件' },
        artifacts: { type: 'array', title: 'Office 附件', items: { type: 'string' } },
      },
      required: ['notification_type', 'channel_id', 'recipients', 'title', 'body'],
    },
    output_schema: { type: 'object', properties: { delivery: { type: 'object', title: '投递回执', additionalProperties: true } } },
    safety_level: 'MUTATION',
  },
  {
    key: 'bklite_http_request',
    name: 'HTTP 请求',
    category: '动作',
    description: '按 Method 与完整 URL 发起 HTTP 请求',
    input_schema: {
      type: 'object',
      properties: {
        method: { type: 'string', title: '请求方法', enum: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], default: 'GET', 'x-binding': 'literal-only' },
        url: { type: 'string', title: 'URL', maxLength: 2000 },
        query: { type: 'object', title: '查询参数', 'x-widget': 'key-value', additionalProperties: { type: 'string' } },
        headers: { type: 'object', title: '请求头', 'x-widget': 'key-value', additionalProperties: { type: 'string' } },
        body: { type: 'object', title: '请求体', jsonEditorAllowed: true },
        timeout: { type: 'integer', title: '超时时间（秒）', default: 30 },
      },
      required: ['method', 'url'],
    },
    output_schema: { type: 'object', properties: { status_code: { type: 'integer', title: '状态码' }, body: { title: '响应体' }, size: { type: 'integer', title: '响应大小' } } },
    safety_level: 'MUTATION',
  },
  {
    key: 'bklite_job_execute',
    name: '作业执行',
    category: '作业平台',
    description: '在授权目标上执行脚本',
    input_schema: {
      type: 'object',
      properties: {
        targets: { type: 'array', title: '目标主机', description: '可从左侧拖入兼容字段或手动填写，也可从作业平台选择主机', items: { type: 'string' }, maxItems: 100 },
        linux_script_type: { type: 'string', title: 'Linux 脚本类型', enum: ['shell'], default: 'shell' },
        linux_script_content: { type: 'string', title: 'Linux 脚本' },
      },
      required: ['targets'],
    },
    ui_schema: { linux_script_content: { 'ui:widget': 'code', 'ui:language': 'sh' } },
    output_schema: { type: 'object', properties: { results: { type: 'array' } } },
    safety_level: 'MUTATION',
  },
  {
    key: 'bklite_document_render',
    name: '文档生成',
    category: '输出',
    description: '使用用户模板生成文档',
    input_schema: {
      type: 'object',
      properties: {
        template: { type: 'object', title: 'Word / Excel 模板' },
        data: { type: 'object', title: '文档数据' },
      },
      required: ['template', 'data'],
    },
    output_schema: { type: 'object', properties: { artifact: { type: 'object' } } },
    safety_level: 'READ_ONLY',
  },
];

describe('编排中心正式设计器', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.patch.mockReset();
    mocks.del.mockReset();
    mocks.push.mockReset();
    mocks.replace.mockReset();
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(workflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      return Promise.resolve([]);
    });
  });

  it('新建时只在前端打开空白画布，首次保存才创建流程', async () => {
    const draftName = '流程20260909101910372';
    const created = { ...workflow, id: 7, name: draftName };
    mocks.get.mockImplementation((url: string) => {
      if (url.includes('/workflows/atoms/')) return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mocks.post.mockResolvedValue(created);

    render(<App><WorkflowOrchestrationConsole workflowId={null} initialName={draftName} /></App>);

    expect(await screen.findByDisplayValue(draftName)).not.toBeNull();
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledWith('/workflow_orchestration/api/workflows/atoms/', expect.anything());
    expect(mocks.post).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /保存草稿/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/',
      expect.objectContaining({
        name: draftName,
        starter: 'blank',
        definition: expect.objectContaining({ tasks: [] }),
        canvas_metadata: expect.objectContaining({ trigger_nodes: [], return_nodes: [], edges: [] }),
      }),
    ));
    expect(mocks.replace).toHaveBeenCalledWith('/workflow-orchestration/workflows/7?mode=edit');
  });

  it('新建流程的第一个节点只能选择触发器', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="空白流程" /></App>);

    const addFirstNode = await screen.findByRole('button', { name: '添加第一个节点' });
    expect(container.querySelector('.react-flow__background-pattern.dots')).not.toBeNull();
    expect(container.querySelector('.react-flow__background')?.getAttribute('style')).toContain('--xy-background-pattern-color-props: var(--color-border-3)');
    expect(screen.queryByText('表单触发器')).toBeNull();

    fireEvent.click(addFirstNode);

    expect(await screen.findByRole('dialog', { name: /选择触发器/ })).not.toBeNull();
    expect(screen.getByText(/每个流程先从一个触发器开始/)).not.toBeNull();
    expect(screen.getByRole('button', { name: /表单触发器/ })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /系统通知/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /条件分支/ })).toBeNull();
  });

  it('点击触发器后立即加入画布，关闭配置不会撤销节点', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="空白流程" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /表单触发器/ }));

    const inspectorNameInput = await screen.findByDisplayValue('表单触发器');
    const inspectorDialog = inspectorNameInput.closest<HTMLElement>('.ant-modal-content');
    expect(inspectorDialog).not.toBeNull();
    expect(container.querySelector('[data-workflow-node="trigger"] button[aria-label="表单触发器"]')).not.toBeNull();

    if (!inspectorDialog) return;
    fireEvent.click(within(inspectorDialog).getByRole('button', { name: 'Close' }));

    expect(container.querySelector('[data-workflow-node="trigger"] button[aria-label="表单触发器"]')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '添加第一个节点' })).toBeNull();
  });

  it('允许删除唯一触发器，空画布仍可保存为草稿', async () => {
    const created = { ...workflow, id: 7, name: '可保存的空草稿', definition: { ...workflow.definition, tasks: [] }, canvas_metadata: { trigger_nodes: [], return_nodes: [], edges: [] } };
    mocks.post.mockResolvedValue(created);
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="可保存的空草稿" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /表单触发器/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    const trigger = container.querySelector<HTMLButtonElement>('[data-workflow-node="trigger"] button[aria-label="表单触发器"]');
    expect(trigger).not.toBeNull();
    if (!trigger) return;
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole('button', { name: '删除节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /^删\s*除$/ }));

    expect(await screen.findByRole('button', { name: '添加第一个节点' })).not.toBeNull();
    expect(screen.queryByText('流程至少需要一个触发器')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /保存草稿/ }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/',
      expect.objectContaining({ canvas_metadata: expect.objectContaining({ trigger_nodes: [] }), starter: 'blank' }),
    ));
  });

  it('未首次保存时单步执行先确认保存，确认后自动继续测试', async () => {
    mocks.post.mockImplementation((url: string, payload: Record<string, unknown>) => {
      if (url === '/workflow_orchestration/api/workflows/') return Promise.resolve({ ...workflow, id: 7, name: '首次测试', definition: payload.definition, canvas_metadata: payload.canvas_metadata });
      if (url === '/workflow_orchestration/api/workflows/7/debug/') return Promise.resolve({ id: 'debug-7', status: 'SUCCEEDED', output: { result: { status_code: 200 } }, permission: ['View'] });
      return Promise.resolve({});
    });
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="首次测试" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /表单触发器/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /HTTP 请求/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    const httpNode = container.querySelector<HTMLButtonElement>('[data-workflow-node="atom"] button[aria-label="HTTP 请求"]');
    expect(httpNode).not.toBeNull();
    if (!httpNode) return;
    fireEvent.click(httpNode);
    fireEvent.click(screen.getByRole('button', { name: '单步执行' }));

    expect((await screen.findAllByText('保存草稿后继续测试？')).length).toBeGreaterThan(0);
    expect(mocks.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /保存并继续/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/workflow_orchestration/api/workflows/', expect.objectContaining({ starter: 'blank' })));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/workflow_orchestration/api/workflows/7/debug/', expect.objectContaining({ task_reference: 'http_request' })));
  });

  it('表单触发器的节点测试和整流程调试共用 Schema 动态表单', async () => {
    const formWorkflow = {
      ...workflow,
      definition: { ...workflow.definition, tasks: [] },
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form', name: '健康巡检表单', trigger_type: 'FORM', config: {},
          input_schema: {
            type: 'object',
            properties: {
              targets: {
                type: 'array', title: '目标主机', items: { type: 'string' }, 'x-widget': 'target-selector',
                'x-target-binding': { mode: 'runtime', allowedSources: ['node_mgmt'], allowedOperatingSystems: ['linux', 'windows'], minCount: 1, maxCount: 20 },
              },
              report_template: {
                type: 'object', title: '报告模板', 'x-widget': 'file-upload',
                'x-file-options': { accept: ['docx', 'xlsx'], maxSizeMiB: 5, maxCount: 1, sourceModes: ['upload'] },
              },
            },
            required: ['targets', 'report_template'],
            additionalProperties: false,
          },
        }],
        return_nodes: [],
        edges: [],
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(formWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve([]);
      return Promise.resolve([]);
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    let trigger: HTMLButtonElement | null = null;
    await waitFor(() => {
      trigger = container.querySelector<HTMLButtonElement>('[data-workflow-node="trigger"] button[aria-label="健康巡检表单"]');
      expect(trigger).not.toBeNull();
    });
    expect(trigger).not.toBeNull();
    if (!trigger) return;
    fireEvent.doubleClick(trigger);
    fireEvent.click(await screen.findByRole('button', { name: /执行节点/ }));

    const nodeTestTitle = await screen.findByText('测试当前节点');
    const nodeTestDialog = nodeTestTitle.closest<HTMLElement>('.ant-modal-content');
    expect(nodeTestDialog).not.toBeNull();
    expect(within(nodeTestDialog!).getByText('目标主机')).not.toBeNull();
    expect(within(nodeTestDialog!).getByText('报告模板')).not.toBeNull();
    expect(within(nodeTestDialog!).getByRole('button', { name: /选择 Word \/ Excel 模板/ })).not.toBeNull();
    expect(within(nodeTestDialog!).getByRole('link', { name: 'Word' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.docx');
    expect(within(nodeTestDialog!).getByRole('link', { name: 'Excel' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.xlsx');
    fireEvent.click(within(nodeTestDialog!).getByRole('button', { name: /Cancel|取\s*消/ }));

    const inspector = screen.getByDisplayValue('健康巡检表单').closest<HTMLElement>('.ant-modal-content');
    expect(inspector).not.toBeNull();
    fireEvent.click(within(inspector!).getByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: /调试流程/ }));

    const debugTitle = await screen.findByText('调试当前草稿');
    const debugDialog = debugTitle.closest<HTMLElement>('.ant-modal-content');
    expect(debugDialog).not.toBeNull();
    expect(within(debugDialog!).getByText('目标主机')).not.toBeNull();
    expect(within(debugDialog!).getByText('报告模板')).not.toBeNull();
    expect(within(debugDialog!).queryByText('调试入口')).toBeNull();
    expect(within(debugDialog!).getByRole('link', { name: 'Word' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.docx');
    expect(within(debugDialog!).getByRole('link', { name: 'Excel' }).getAttribute('href')).toBe('/workflow-orchestration/templates/health-inspection-example.xlsx');
  });

  it('多触发器流程调试时选择一个入口并生成单条调试执行', async () => {
    const multiTriggerWorkflow = {
      ...workflow,
      canvas_metadata: {
        trigger_nodes: [
          { id: 'trigger_form', name: '人工表单', trigger_type: 'FORM', input_schema: { type: 'object', properties: {}, required: [] }, config: {} },
          { id: 'trigger_webhook', name: '告警 Webhook', trigger_type: 'WEBHOOK', input_schema: { type: 'object', properties: {}, required: [] }, config: { response_mode: 'IMMEDIATE' } },
        ],
        return_nodes: [],
        edges: [
          { id: 'from-form', source: 'trigger_form', target: 'notify' },
          { id: 'from-webhook', source: 'trigger_webhook', target: 'notify' },
        ],
        node_titles: { notify: '发送巡检结果' },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(multiTriggerWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      return Promise.resolve([]);
    });
    mocks.post.mockResolvedValue({
      id: 'debug-webhook-1',
      status: 'RUNNING',
      mode: 'DEBUG',
      trigger_type: 'WEBHOOK',
      trigger_id: 'trigger_webhook',
      permission: ['View'],
    });

    render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    fireEvent.click(await screen.findByRole('button', { name: /调试流程/ }));

    const debugDialog = (await screen.findByText('调试当前草稿')).closest<HTMLElement>('.ant-modal-content');
    expect(debugDialog).not.toBeNull();
    expect(within(debugDialog!).getByText('调试入口')).not.toBeNull();
    fireEvent.mouseDown(within(debugDialog!).getByRole('combobox'));
    fireEvent.click(await screen.findByText('告警 Webhook · WEBHOOK'));
    fireEvent.click(within(debugDialog!).getByRole('button', { name: '开始调试' }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/1/debug/',
      expect.objectContaining({ trigger_id: 'trigger_webhook', inputs: {} }),
    ));
    expect(mocks.post.mock.calls.filter(([url]) => String(url).endsWith('/debug/'))).toHaveLength(1);
  });

  it('选择动作原子后立即加入画布，无需在配置弹窗保存', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="空白流程" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /表单触发器/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /系统通知/ }));
    expect(await screen.findByRole('dialog')).not.toBeNull();
    expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="系统通知"]')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /^保\s*存$/ })).toBeNull();
    fireEvent.click(document.querySelector<HTMLButtonElement>('.ant-modal-close')!);
    expect(screen.queryByRole('button', { name: '添加第一个节点' })).toBeNull();
  });

  it('作业执行可从作业平台选择主机并回填节点固定值', async () => {
    const jobTarget = { id: 'manual:11', source: 'job_mgmt', source_id: 11, name: 'job-linux-01', ip: '10.10.41.101', operating_system: 'linux' };
    mocks.get.mockImplementation((url: string) => {
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      if (url.includes('/workflows/targets/?') && url.includes('source=job_mgmt')) return Promise.resolve({ source: 'job_mgmt', count: 1, items: [jobTarget] });
      if (url.includes('/workflows/targets/?') && url.includes('source=node_mgmt')) return Promise.resolve({ source: 'node_mgmt', count: 0, items: [] });
      return Promise.resolve([]);
    });
    render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="作业流程" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /表单触发器/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /作业执行/ }));

    expect(screen.getAllByTestId('workflow-reference-dropzone').length).toBeGreaterThan(0);
    fireEvent.click(await screen.findByRole('button', { name: /选择作业平台主机/ }));
    expect(screen.queryByRole('tab', { name: /节点管理/ })).toBeNull();
    const row = (await screen.findByText('job-linux-01')).closest('tr');
    expect(row).not.toBeNull();
    fireEvent.click(within(row!).getByRole('checkbox'));
    expect(await screen.findByText(/已选 1 台/)).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));

    await waitFor(() => {
      expect(screen.getAllByText(/job-linux-01|作业目标 #11/).length).toBeGreaterThan(0);
    });
    expect(screen.queryByText('manual:11')).toBeNull();
  });

  it('Webhook 只保留自动接口与响应模式，并仅在等待模式开放响应节点', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="Webhook 流程" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /Webhook 触发器/ }));

    expect(await screen.findByText('Webhook 接口')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /添加请求输入字段/ })).toBeNull();
    expect(screen.getByText('立即响应（返回 execution_id）')).not.toBeNull();

    fireEvent.click(document.querySelector<HTMLButtonElement>('.ant-modal-close')!);
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    expect(screen.queryByRole('button', { name: /Webhook 响应/ })).toBeNull();
    const pickerClose = container.querySelector<HTMLButtonElement>('.ant-drawer-close');
    expect(pickerClose).not.toBeNull();
    if (!pickerClose) return;
    fireEvent.click(pickerClose);

    const trigger = screen.getByRole('button', { name: /Webhook 触发器/ });
    fireEvent.doubleClick(trigger);
    fireEvent.mouseDown(await screen.findByText('立即响应（返回 execution_id）'));
    fireEvent.click(await screen.findByText('等待流程结果（同步）'));
    fireEvent.click(document.querySelector<HTMLButtonElement>('.ant-modal-close')!);
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    expect(await screen.findByRole('button', { name: /Webhook 响应/ })).not.toBeNull();
  });

  it('Webhook 监听真实测试请求并用 body 推断输入字段', async () => {
    const webhookWorkflow = {
      ...workflow,
      name: 'Webhook 测试',
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_webhook',
          name: 'Webhook 触发器',
          trigger_type: 'WEBHOOK',
          input_schema: {
            type: 'object',
            properties: { body: { type: 'object', title: '请求正文', properties: {}, additionalProperties: true } },
            required: ['body'],
            additionalProperties: false,
          },
          config: { response_mode: 'IMMEDIATE' },
        }],
        return_nodes: [],
        edges: [],
      },
    };
    let resolveListen: ((value: unknown) => void) | undefined;
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(webhookWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve([]);
      return Promise.resolve([]);
    });
    mocks.post.mockImplementation((url: string) => {
      if (url.endsWith('/triggers/webhook-test-session/')) return Promise.resolve({ token: 'signed-webhook-session', timeout_seconds: 60 });
      if (url.endsWith('/triggers/webhook-test-listen/')) return new Promise((resolve) => { resolveListen = resolve; });
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });

    render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    const trigger = (await screen.findByText('Webhook 触发器')).closest('[data-workflow-node]')?.querySelector<HTMLButtonElement>('button');
    expect(trigger).not.toBeNull();
    if (!trigger) return;
    fireEvent.doubleClick(trigger);
    fireEvent.click(await screen.findByRole('button', { name: /监听测试请求/ }));

    expect(await screen.findByText(/signed-webhook-session/)).not.toBeNull();
    expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/triggers/webhook-test-session/',
      { workflow_id: 1, node_key: 'trigger_webhook' },
    );
    resolveListen?.({ body: { host: '10.0.0.8', severity: 'critical' } });

    expect(await screen.findByText('已捕获请求')).not.toBeNull();
    expect(screen.getByText('body.host')).not.toBeNull();
    expect(screen.getByText('body.severity')).not.toBeNull();
  });

  it('NATS 只配置节点名称，并通过短时主题监听真实测试事件', async () => {
    const natsWorkflow = {
      ...workflow,
      name: 'NATS 流程',
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_nats',
          name: '事件触发器（NATS）',
          trigger_type: 'NATS',
          input_schema: { type: 'object', properties: {}, required: [], additionalProperties: true },
          config: {},
        }],
        return_nodes: [],
        edges: [],
      },
    };
    let resolveListen: ((value: unknown) => void) | undefined;
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(natsWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve([]);
      return Promise.resolve([]);
    });
    mocks.post.mockImplementation((url: string) => {
      if (url.endsWith('/triggers/nats-test-session/')) return Promise.resolve({
        token: 'signed-session',
        subject: 'bklite.workflow.test.1.trigger_nats.session',
        timeout_seconds: 30,
      });
      if (url.endsWith('/triggers/nats-test-listen/')) return new Promise((resolve) => { resolveListen = resolve; });
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    const trigger = (await screen.findByText('事件触发器（NATS）')).closest('[data-workflow-node]')?.querySelector<HTMLButtonElement>('button');
    expect(trigger).not.toBeNull();
    if (!trigger) return;
    fireEvent.doubleClick(trigger);

    expect(await screen.findByDisplayValue('事件触发器（NATS）')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /添加事件字段/ })).toBeNull();
    expect(screen.queryByText(/通道标识|输入参数|输出参数/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /监听测试事件/ }));

    expect(await screen.findByText('bklite.workflow.test.1.trigger_nats.session')).not.toBeNull();
    expect(screen.getByRole('button', { name: /取消监听/ })).not.toBeNull();
    expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/triggers/nats-test-session/',
      { workflow_id: 1, node_key: 'trigger_nats' },
    );
    resolveListen?.({
      event: { event_id: 'evt-1', occurred_at: '2026-09-18T10:00:00Z', producer: 'job-platform', payload: { status: 'SUCCESS' } },
      inputs: { status: 'SUCCESS' },
    });

    expect(await screen.findByText('上次测试')).not.toBeNull();
    expect(screen.getByText('status')).not.toBeNull();
    expect(screen.getByText('已捕获事件')).not.toBeNull();
    expect(container.querySelector('[data-workflow-node="trigger"]')).not.toBeNull();

    mocks.post.mockImplementation((url: string) => {
      if (url.endsWith('/triggers/nats-test-session/')) return Promise.resolve({
        token: 'failed-session',
        subject: 'bklite.workflow.test.1.trigger_nats.failed',
        timeout_seconds: 30,
      });
      if (url.endsWith('/triggers/nats-test-listen/')) return Promise.reject(new Error('timeout'));
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    const listenAgain = screen.getByRole<HTMLButtonElement>('button', { name: /监听测试事件/ });
    await waitFor(() => expect(listenAgain.disabled).toBe(false));
    fireEvent.click(listenAgain);

    expect(await screen.findByText('监听失败')).not.toBeNull();
    expect(screen.queryByText('已捕获事件')).toBeNull();
  });

  it('定时触发使用结构化频率、预览下次执行并可立即模拟触发', async () => {
    mocks.post.mockResolvedValue({
      config: { frequency: 'daily', time: ['02:00'], expressions: ['0 2 * * *'], expression: '0 2 * * *', timezone: 'Asia/Shanghai' },
      expressions: ['0 2 * * *'],
      timezone: 'Asia/Shanghai',
      next_runs: ['2026-09-19T02:00:00+08:00', '2026-09-20T02:00:00+08:00'],
      test_output: {
        triggered_at: '2026-09-18T09:24:02+08:00',
        scheduled_at: '2026-09-19T02:00:00+08:00',
        timezone: 'Asia/Shanghai',
        schedule: ['0 2 * * *'],
        test: true,
      },
    });

    render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="定时流程" /></App>);
    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /定时触发器/ }));

    expect(await screen.findByText('触发频率')).not.toBeNull();
    expect(screen.getByText('每天')).not.toBeNull();
    expect(screen.getByLabelText('执行时间 1')).not.toBeNull();
    expect(screen.queryByText('时区')).toBeNull();
    expect(screen.queryByText('输入参数')).toBeNull();
    expect(screen.queryByText('输出参数')).toBeNull();
    expect(await screen.findByText('2026-09-19 02:00:00')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /执行节点/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/triggers/schedule-preview/',
      expect.objectContaining({ config: expect.objectContaining({ frequency: 'daily', time: ['02:00'] }) }),
    ));
    expect(await screen.findByText('上次测试')).not.toBeNull();
  });

  it('未保存的条件节点可以将右值切换为字段引用', async () => {
    render(<App><WorkflowOrchestrationConsole workflowId={null} initialName="条件流程" /></App>);

    fireEvent.click(await screen.findByRole('button', { name: '添加第一个节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /表单触发器/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    fireEvent.click(await screen.findByRole('button', { name: /条件分支/ }));
    fireEvent.mouseDown(await screen.findByText('固定值'));
    fireEvent.click(await screen.findByText('字段引用'));

    expect(await screen.findByText('选择同类型右值字段')).not.toBeNull();
  });

  it('以点阵画布为主，并按需打开原子选择和节点配置', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);

    expect(await screen.findByText('表单触发器')).not.toBeNull();
    expect(container.querySelector('main')?.className).toContain('h-full');
    fireEvent.click(screen.getByRole('button', { name: '添加节点' }));
    expect(await screen.findByText('动作')).not.toBeNull();
    expect(screen.queryByText('子流程触发器')).toBeNull();
    expect(screen.queryByText('子流程响应')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /系统通知/ }));
    expect(await screen.findByText('节点名称')).not.toBeNull();
    expect(screen.queryByText('节点引用')).toBeNull();
    expect(screen.queryByText('节点类型')).toBeNull();
  });

  it('HTTP 请求保留业务配置并可直接执行真实步骤', async () => {
    const httpWorkflow = {
      ...workflow,
      definition: {
        ...workflow.definition,
        tasks: [{
          name: 'bklite_http_request',
          taskReferenceName: 'request_status',
          type: 'SIMPLE',
          inputParameters: { method: 'GET', url: 'https://example.com/health', query: {}, headers: {}, timeout: 30 },
        }],
      },
      canvas_metadata: {
        trigger_nodes: [{ id: 'trigger_schedule', name: '定时触发器', trigger_type: 'SCHEDULE', input_schema: { type: 'object', properties: {}, required: [] }, config: {} }],
        node_titles: { request_status: '检查服务状态' },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(httpWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      return Promise.resolve([]);
    });
    mocks.post.mockResolvedValue({
      id: 'execution-http-1',
      status: 'SUCCEEDED',
      output: { result: { status_code: 200, body: { status: 'ok' }, size: 15 } },
      permission: ['View'],
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="检查服务状态"]')).not.toBeNull());
    const node = container.querySelector<HTMLButtonElement>('[data-workflow-node="atom"] button[aria-label="检查服务状态"]');
    expect(node).not.toBeNull();
    if (!node) return;
    fireEvent.doubleClick(node);

    expect(await screen.findByDisplayValue('检查服务状态')).not.toBeNull();
    expect(screen.getByText('API')).not.toBeNull();
    expect(screen.getByText('请求参数')).not.toBeNull();
    expect(screen.getByText('请求头')).not.toBeNull();
    expect(screen.getByText('请求体')).not.toBeNull();
    expect(screen.getByText('超时设置（秒）')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '管理连接' })).toBeNull();
    expect(screen.queryByText('高级设置')).toBeNull();
    expect(screen.queryByText('节点引用')).toBeNull();
    expect(screen.queryByText('输入参数')).toBeNull();
    expect(screen.queryByText('输出参数')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /执行节点/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/1/debug/',
      expect.objectContaining({ task_reference: 'request_status', node_inputs: expect.objectContaining({ method: 'GET', url: 'https://example.com/health' }) }),
    ));
    expect(screen.queryByText('测试当前节点')).toBeNull();
    const httpOutput = screen.getByRole('region', { name: '节点输出' });
    fireEvent.click(within(httpOutput).getByText('JSON'));
    await waitFor(() => expect(httpOutput.querySelector('pre')?.textContent).toContain('200'));
  });

  it('文档生成可引用整个作业输出，并在测试前轻量校验模板', async () => {
    const documentWorkflow = {
      ...workflow,
      definition: {
        ...workflow.definition,
        tasks: [
          { name: 'bklite_job_execute', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: { targets: [] } },
          { name: 'bklite_document_render', taskReferenceName: 'document_render', type: 'SIMPLE', inputParameters: { template: '${workflow.input.file}', data: '${job_execute.output}' } },
        ],
      },
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form', name: '表单触发器', trigger_type: 'FORM', config: {},
          input_schema: {
            type: 'object',
            properties: { file: { type: 'object', title: '报告模板', 'x-widget': 'file-upload' } },
            required: ['file'],
          },
        }],
        edges: [
          { id: 'edge-1', source: 'trigger_form', target: 'job_execute' },
          { id: 'edge-2', source: 'job_execute', target: 'document_render' },
        ],
        node_titles: { job_execute: '作业执行', document_render: '文档生成' },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(documentWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      return Promise.resolve([]);
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="文档生成"]')).not.toBeNull());
    fireEvent.doubleClick(container.querySelector('[data-workflow-node="atom"] button[aria-label="文档生成"]')!);

    expect(await screen.findByText('${job_execute.output}')).not.toBeNull();
    expect(screen.queryByText('该结构没有可生成表单的子字段')).toBeNull();
    const dataItem = screen.getByText('文档数据').closest('.ant-form-item');
    expect(dataItem?.querySelector('[aria-label="question-circle"]')).not.toBeNull();
    expect(dataItem?.querySelector('.ant-form-item-extra')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /执行节点/ }));
    const testDialogTitle = await screen.findByText('测试当前节点');
    const testDialog = testDialogTitle.closest<HTMLElement>('.ant-modal-content');
    expect(testDialog).not.toBeNull();
    expect(within(testDialog!).getByRole('link', { name: 'Word' })).not.toBeNull();
    expect(within(testDialog!).getByRole('link', { name: 'Excel' })).not.toBeNull();
    expect(within(testDialog!).getByRole('button', { name: /上传测试模板/ })).not.toBeNull();
    fireEvent.click(within(testDialog!).getByRole('button', { name: /执行节点/ }));
    expect(await screen.findByText('请先上传 Word 或 Excel 测试模板')).not.toBeNull();
    expect(mocks.post).not.toHaveBeenCalledWith(expect.stringContaining('/debug/'), expect.anything());
  });

  it('文档生成测试弹窗会带入节点已配置的模板和文档数据引用', async () => {
    const uploadedTemplate = {
      kind: 'uploaded',
      name: 'health-inspection.docx',
      format: 'docx',
      size: 2048,
      placeholders: ['summary.total'],
      token: 'template-token-1',
    };
    const documentWorkflow = {
      ...workflow,
      definition: {
        ...workflow.definition,
        tasks: [
          { name: 'bklite_job_execute', taskReferenceName: 'scan', type: 'SIMPLE', inputParameters: { targets: ['host-1'] } },
          {
            name: 'bklite_document_render',
            taskReferenceName: 'document_render',
            type: 'SIMPLE',
            inputParameters: {
              template: uploadedTemplate,
              data: '${scan.output}',
            },
          },
        ],
      },
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form', name: '表单触发器', trigger_type: 'FORM', config: {},
          input_schema: { type: 'object', properties: {}, required: [] },
        }],
        edges: [
          { id: 'edge-1', source: 'trigger_form', target: 'scan' },
          { id: 'edge-2', source: 'scan', target: 'document_render' },
        ],
        node_titles: { scan: '作业执行', document_render: '文档生成' },
        node_test_data: {
          scan: { summary: { total: 2 }, results: [{ status: 'ok' }] },
        },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(documentWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      return Promise.resolve([]);
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="文档生成"]')).not.toBeNull());
    fireEvent.doubleClick(container.querySelector('[data-workflow-node="atom"] button[aria-label="文档生成"]')!);
    fireEvent.click(await screen.findByRole('button', { name: /执行节点/ }));

    const testDialog = (await screen.findByText('测试当前节点')).closest<HTMLElement>('.ant-modal-content');
    expect(testDialog).not.toBeNull();
    expect(within(testDialog!).getByText('health-inspection.docx')).not.toBeNull();
    expect(within(testDialog!).getByText(/summary\.total/)).not.toBeNull();
    expect(within(testDialog!).queryByRole('button', { name: /替换测试模板/ })).toBeNull();
    expect(within(testDialog!).queryByRole('button', { name: /上传测试模板/ })).toBeNull();
    expect(within(testDialog!).getByDisplayValue('${scan.output}')).not.toBeNull();

    fireEvent.click(within(testDialog!).getByRole('button', { name: /移除测试模板/ }));
    expect(within(testDialog!).getByRole('button', { name: /上传测试模板/ })).not.toBeNull();
    expect(within(testDialog!).queryByText('health-inspection.docx')).toBeNull();
  });

  it('文档生成测试弹窗也会带入已发布固化的模板快照', async () => {
    const documentWorkflow = {
      ...workflow,
      definition: {
        ...workflow.definition,
        tasks: [{
          name: 'bklite_document_render',
          taskReferenceName: 'document_render',
          type: 'SIMPLE',
          inputParameters: {
            template_snapshot: {
              object_key: 'workflow-orchestration/templates/team/health.docx',
              format: 'docx',
              size: 4096,
              filename_prefix: 'health-inspection',
              sha256: 'a'.repeat(64),
            },
            data: { summary: { total: 1 } },
          },
        }],
      },
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form', name: '表单触发器', trigger_type: 'FORM', config: {},
          input_schema: { type: 'object', properties: {}, required: [] },
        }],
        edges: [{ id: 'edge-1', source: 'trigger_form', target: 'document_render' }],
        node_titles: { document_render: '文档生成' },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(documentWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      return Promise.resolve([]);
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="文档生成"]')).not.toBeNull());
    fireEvent.doubleClick(container.querySelector('[data-workflow-node="atom"] button[aria-label="文档生成"]')!);
    fireEvent.click(await screen.findByRole('button', { name: /执行节点/ }));

    const testDialog = (await screen.findByText('测试当前节点')).closest<HTMLElement>('.ant-modal-content');
    expect(testDialog).not.toBeNull();
    expect(within(testDialog!).getByText('health-inspection.docx')).not.toBeNull();
    expect(within(testDialog!).getByText(/已发布固化/)).not.toBeNull();
    expect(within(testDialog!).getByDisplayValue(/"total": 1/)).not.toBeNull();
  });

  it('作业节点测试以摘要样式展示已配主机并可改选作业平台主机', async () => {
    const jobTarget = { id: 'manual:11', source: 'job_mgmt', source_id: 11, name: 'job-linux-01', ip: '10.10.41.101', operating_system: 'linux' };
    const otherTarget = { id: 'manual:12', source: 'job_mgmt', source_id: 12, name: 'job-linux-02', ip: '10.10.41.102', operating_system: 'linux' };
    const jobWorkflow = {
      ...workflow,
      definition: {
        ...workflow.definition,
        tasks: [{ name: 'bklite_job_execute', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: { targets: ['manual:11'] } }],
      },
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form', name: '表单触发器', trigger_type: 'FORM', config: {},
          input_schema: {
            type: 'object',
            properties: { report_template: { type: 'object', title: '报告模板', 'x-widget': 'file-upload' } },
            required: ['report_template'],
          },
        }],
        edges: [{ id: 'edge-1', source: 'trigger_form', target: 'job_execute' }],
        node_titles: { job_execute: '作业执行' },
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(jobWorkflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      if (url.includes('/workflows/targets/?') && url.includes('source=job_mgmt')) {
        return Promise.resolve({ source: 'job_mgmt', count: 2, items: [jobTarget, otherTarget] });
      }
      return Promise.resolve([]);
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="作业执行"]')).not.toBeNull());
    fireEvent.doubleClick(container.querySelector('[data-workflow-node="atom"] button[aria-label="作业执行"]')!);
    fireEvent.click(await screen.findByRole('button', { name: /执行节点/ }));

    const testDialog = (await screen.findByText('测试当前节点')).closest<HTMLElement>('.ant-modal-content');
    expect(testDialog).not.toBeNull();
    expect(within(testDialog!).queryByText('报告模板')).toBeNull();
    expect(within(testDialog!).getByText('已选择 1 台主机')).not.toBeNull();
    expect(within(testDialog!).getByText('点击打开主机选择器，确认后回填本执行表单')).not.toBeNull();
    expect(within(testDialog!).queryByText('manual:11')).toBeNull();

    fireEvent.click(within(testDialog!).getByRole('button', { name: /已选择 1 台主机/ }));
    expect(await screen.findByText(/已选 1 台/)).not.toBeNull();
    expect(screen.queryByRole('tab', { name: /节点管理/ })).toBeNull();

    const otherRow = (await screen.findByText(otherTarget.name)).closest('tr');
    expect(otherRow).not.toBeNull();
    fireEvent.click(within(otherRow!).getByRole('checkbox'));
    expect(await screen.findByText(/已选 2 台/)).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));

    await waitFor(() => {
      expect(within(testDialog!).getByText('已选择 2 台主机')).not.toBeNull();
    });
  });

  it('对外通知在真实发送前明确确认，并支持修改节点名称', async () => {
    mocks.post.mockResolvedValue({
      id: 'execution-notification-1',
      status: 'SUCCEEDED',
      output: { result: { delivery: { status: 'SENT', message_id: 'message-1' } } },
      permission: ['View'],
    });
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="发送巡检结果"]')).not.toBeNull());
    const node = container.querySelector<HTMLButtonElement>('[data-workflow-node="atom"] button[aria-label="发送巡检结果"]');
    expect(node).not.toBeNull();
    if (!node) return;
    fireEvent.doubleClick(node);

    const nodeName = await screen.findByDisplayValue('发送巡检结果');
    expect(screen.getByText('通知类别')).not.toBeNull();
    expect(screen.getByText('通知方式')).not.toBeNull();
    expect(screen.getByRole('link', { name: /新增通知渠道/ })).not.toBeNull();
    expect(screen.getByText('通知人')).not.toBeNull();
    expect(screen.getByText('通知标题')).not.toBeNull();
    expect(screen.getByText('附件')).not.toBeNull();
    const attachmentItem = screen.getByText('附件').closest('.ant-form-item');
    expect(attachmentItem?.querySelector('[aria-label="question-circle"]')).not.toBeNull();
    expect(attachmentItem?.querySelector('.ant-form-item-extra')).toBeNull();
    expect(screen.queryByText('邮件通知会自动附带本次工作流运行中生成的全部附件，无需手动选择。')).toBeNull();
    expect(screen.getByText('通知内容')).not.toBeNull();
    expect(screen.queryByText('高级设置')).toBeNull();
    fireEvent.change(nodeName, { target: { value: '通知值班人员' } });
    expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="通知值班人员"]')).not.toBeNull();
    expect(screen.queryByText('节点引用')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /执行节点/ }));

    const confirmTitle = (await screen.findAllByText('发送真实测试通知？')).find((item) => item.closest('.ant-modal'));
    const confirm = confirmTitle?.closest<HTMLElement>('.ant-modal');
    expect(confirm).not.toBeNull();
    expect(within(confirm!).getByText('管理员 (admin)、值班工程师 (demo_oncall)')).not.toBeNull();
    expect(mocks.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /发送测试通知/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/1/debug/',
      expect.objectContaining({ task_reference: 'notify', confirmed: true }),
    ));
    const notificationOutput = screen.getByRole('region', { name: '节点输出' });
    fireEvent.click(within(notificationOutput).getByText('JSON'));
    await waitFor(() => expect(notificationOutput.querySelector('pre')?.textContent).toContain('message-1'));
  });

  it('去掉编辑器切换 Tab，从右侧工具栏跳转当前流程的执行记录', async () => {
    render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);

    const executionsButton = await screen.findByRole('button', { name: '执行记录' });
    expect(screen.queryByText('编辑器')).toBeNull();

    fireEvent.click(executionsButton);

    expect(mocks.push).toHaveBeenCalledWith('/workflow-orchestration/executions?query=%E4%B8%BB%E6%9C%BA%E5%81%A5%E5%BA%B7%E5%B7%A1%E6%A3%80');
  });

  it('未产生调试执行时，底部执行详情入口为禁用的 link 按钮', async () => {
    render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);

    const detailsButton = await screen.findByRole('button', { name: '运行后可查看执行详情' });

    expect(detailsButton.hasAttribute('disabled')).toBe(true);
    expect(detailsButton.className).toContain('ant-btn-link');
  });

  it('单击节点只选中，双击节点才打开业务配置窗口', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);

    const triggerLabel = await screen.findByText('表单触发器');
    const trigger = triggerLabel.closest('[data-workflow-node]')?.querySelector<HTMLButtonElement>('button[aria-label="表单触发器"]');
    expect(trigger).not.toBeNull();
    if (!trigger) return;
    fireEvent.click(trigger);
    expect(screen.queryByRole('dialog')).toBeNull();

    const selectedTrigger = container.querySelector<HTMLButtonElement>('[data-workflow-node="trigger"] button[aria-label="表单触发器"]');
    expect(selectedTrigger).not.toBeNull();
    if (!selectedTrigger) return;
    fireEvent.doubleClick(selectedTrigger);
    expect(await screen.findByRole('region', { name: '节点参数' })).not.toBeNull();
    expect(screen.queryByRole('region', { name: '节点输入' })).toBeNull();
    expect(screen.getByRole('region', { name: '节点输出' })).not.toBeNull();
  });

  it('节点参数修改立即写入前端草稿，关闭弹窗后仍然保留', async () => {
    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);

    const triggerLabel = await screen.findByText('表单触发器');
    const trigger = triggerLabel.closest('[data-workflow-node]')?.querySelector<HTMLButtonElement>('button[aria-label="表单触发器"]');
    expect(trigger).not.toBeNull();
    if (!trigger) return;

    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole('button', { name: '配置' }));
    const nameInput = await screen.findByDisplayValue('表单触发器');
    fireEvent.change(nameInput, { target: { value: '临时名称' } });
    expect((await screen.findAllByText('临时名称')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /完\s*成/ })).toBeNull();
    expect(screen.queryByText(/刷新前未保存内容会丢失/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    const reopenedTrigger = container.querySelector<HTMLButtonElement>('[data-workflow-node="trigger"] button[aria-label="临时名称"]');
    expect(reopenedTrigger).not.toBeNull();
    if (!reopenedTrigger) return;
    fireEvent.click(reopenedTrigger);
    fireEvent.click(await screen.findByRole('button', { name: '配置' }));
    expect(await screen.findByDisplayValue('临时名称')).not.toBeNull();
    fireEvent.change(screen.getByDisplayValue('临时名称'), { target: { value: '已暂存名称' } });
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(mocks.patch).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
    const savedTriggerLabels = await screen.findAllByText('已暂存名称');
    const savedTrigger = savedTriggerLabels
      .map(label => label.closest('[data-workflow-node]')?.querySelector<HTMLButtonElement>('button[aria-label="已暂存名称"]'))
      .find(Boolean);
    expect(savedTrigger).not.toBeNull();
    if (!savedTrigger) return;
    fireEvent.click(savedTrigger);
    fireEvent.click(await screen.findByRole('button', { name: '配置' }));
    expect(await screen.findByDisplayValue('已暂存名称')).not.toBeNull();
    expect(screen.queryByText(/刷新前未保存内容会丢失/)).toBeNull();
  });

  it('保存和加载同一原子的组织共享配置模板，加载后直接回填前端草稿', async () => {
    const template = {
      id: 9,
      name: '常用邮件通知',
      atom_key: 'bklite_notification',
      parameters: {
        notification_type: 'EMAIL',
        channel_id: 1,
        recipients: ['ops'],
        title: '模板标题',
        body: '模板内容',
      },
      organization_id: 1,
      created_by: 'admin',
      updated_by: 'admin',
      created_at: '2026-09-20T01:00:00Z',
      updated_at: '2026-09-20T01:00:00Z',
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(workflow);
      if (url.includes('/workflows/atoms/')) return Promise.resolve(atoms);
      if (url.includes('/atom-config-templates/')) return Promise.resolve({ count: 1, items: [template] });
      return Promise.resolve([]);
    });
    mocks.post.mockImplementation((url: string, payload: Record<string, unknown>) => {
      if (url === '/workflow_orchestration/api/atom-config-templates/') return Promise.resolve({ ...template, ...payload });
      return Promise.resolve({});
    });

    const { container } = render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    await waitFor(() => expect(container.querySelector('[data-workflow-node="atom"] button[aria-label="发送巡检结果"]')).not.toBeNull());
    fireEvent.doubleClick(container.querySelector<HTMLButtonElement>('[data-workflow-node="atom"] button[aria-label="发送巡检结果"]')!);
    expect(await screen.findByDisplayValue('发送巡检结果')).not.toBeNull();

    fireEvent.click(await screen.findByRole('button', { name: /配置模板/ }));
    expect(await screen.findByLabelText('模板名称')).not.toBeNull();
    const saveDialog = screen.getAllByRole('dialog').at(-1)!;
    fireEvent.change(within(saveDialog).getByLabelText('模板名称'), { target: { value: '常用邮件通知' } });
    fireEvent.click(within(saveDialog).getByRole('button', { name: /保\s*存/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/atom-config-templates/',
      expect.objectContaining({
        name: '常用邮件通知',
        atom_key: 'bklite_notification',
        parameters: expect.objectContaining({ title: '巡检完成', body: '完成' }),
      }),
    ));

    fireEvent.click(screen.getByRole('button', { name: /加载模板/ }));
    expect(await screen.findByPlaceholderText('搜索配置模板')).not.toBeNull();
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/atom-config-templates\/\?.*atom_key=bklite_notification.*page=1.*page_size=10/),
    ));
    const loadDialog = screen.getAllByRole('dialog').at(-1)!;
    expect(within(loadDialog).queryByRole('alert')).toBeNull();
    const templateRow = within(loadDialog).getByText('常用邮件通知').closest('tr');
    expect(templateRow).not.toBeNull();
    expect(within(templateRow!).getByRole('button', { name: '选用' })).not.toBeNull();
    expect(within(templateRow!).getByRole('button', { name: '修改' })).not.toBeNull();
    expect(within(templateRow!).getByRole('button', { name: '删除' })).not.toBeNull();
    fireEvent.click(within(templateRow!).getByRole('button', { name: '选用' }));

    expect(await screen.findByDisplayValue('模板标题')).not.toBeNull();
    expect(screen.getByDisplayValue('模板内容')).not.toBeNull();
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it('单选和多选字段按 Enter 生成选项 Tag', async () => {
    const workflowWithOptions = {
      ...workflow,
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form',
          name: '表单触发器',
          trigger_type: 'FORM',
          input_schema: {
            type: 'object',
            properties: {
              os: { type: 'string', title: '操作系统', 'x-widget': 'select', enum: [] },
              regions: { type: 'array', title: '地域', 'x-widget': 'multiselect', items: { type: 'string', enum: [] } },
            },
            required: [],
            additionalProperties: false,
          },
          config: {},
        }],
      },
    };
    mocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/workflows/1/')) return Promise.resolve(workflowWithOptions);
      if (url.includes('/workflows/atoms/')) return Promise.resolve([]);
      return Promise.resolve([]);
    });

    render(<App><WorkflowOrchestrationConsole workflowId={1} /></App>);
    const triggerLabel = await screen.findByText('表单触发器');
    const trigger = triggerLabel.closest('[data-workflow-node]')?.querySelector<HTMLButtonElement>('button[aria-label="表单触发器"]');
    expect(trigger).not.toBeNull();
    if (!trigger) return;
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole('button', { name: '配置' }));

    const optionLabels = await screen.findAllByText('选项');
    expect(optionLabels).toHaveLength(2);
    const optionInputs = optionLabels
      .map((label) => label.closest('.ant-form-item')?.querySelector<HTMLInputElement>('input'))
      .filter((item): item is HTMLInputElement => Boolean(item));
    expect(optionInputs).toHaveLength(2);
    expect(optionLabels[0].closest('.ant-form-item')?.querySelector('[aria-label="question-circle"]')).not.toBeNull();
    expect(optionLabels[0].closest('.ant-form-item')?.querySelector('.ant-form-item-extra')).toBeNull();

    fireEvent.change(optionInputs[0], { target: { value: 'Linux' } });
    fireEvent.keyDown(optionInputs[0], { key: 'Enter', code: 'Enter', keyCode: 13, which: 13 });
    const outputPanel = screen.getByRole('region', { name: '节点输出' });
    fireEvent.click(within(outputPanel).getByText('JSON'));
    await waitFor(() => {
      const schemaText = outputPanel.querySelector('pre')?.textContent;
      expect(JSON.parse(schemaText || '{}')).toMatchObject({ properties: { os: { enum: ['Linux'] } } });
    });
    const currentMultiSelectInput = optionLabels[1].closest('.ant-form-item')?.querySelector<HTMLInputElement>('input');
    expect(currentMultiSelectInput).not.toBeNull();
    if (!currentMultiSelectInput) return;
    fireEvent.change(currentMultiSelectInput, { target: { value: 'Guangzhou' } });
    fireEvent.keyDown(currentMultiSelectInput, { key: 'Enter', code: 'Enter', keyCode: 13, which: 13 });

    await waitFor(() => {
      const schemaText = screen.getByRole('region', { name: '节点输出' }).querySelector('pre')?.textContent;
      expect(JSON.parse(schemaText || '{}')).toMatchObject({
        properties: {
          os: { enum: ['Linux'] },
          regions: { items: { enum: ['Guangzhou'] } },
        },
      });
    });
  });

});
