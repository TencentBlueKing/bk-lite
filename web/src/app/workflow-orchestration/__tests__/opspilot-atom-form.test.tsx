import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeAll, vi } from 'vitest';

import { OpsPilotAtomForm } from '../components/opspilot-atom-form';
import type { JsonSchema } from '../lib/types';

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
const currentUser = vi.hoisted(() => ({ username: 'admin', userId: '1' }));

vi.mock('@/utils/request', () => ({
  default: () => ({ post: mocks.post }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => currentUser,
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
});

const intentSchema: JsonSchema = {
  type: 'object',
  required: ['model_id', 'text', 'intents'],
  properties: {
    model_id: { type: 'integer', title: '分类模型', enum: [1], 'x-enum-labels': { '1': '通用模型' } },
    text: { type: 'string', title: '待分类内容', 'x-widget': 'textarea' },
    intents: { type: 'array', title: '意图列表', items: { type: 'string' } },
    classification_rules: { type: 'string', title: '分类规则', 'x-widget': 'textarea' },
  },
};

function IntentHarness() {
  const [value, setValue] = useState<Record<string, unknown>>({ model_id: 1, intents: ['告警处理'], text: '${workflow.input.message}' });
  const [title, setTitle] = useState('意图分类');
  return <App><OpsPilotAtomForm atomKey="bklite_intent_classification" schema={intentSchema} value={value} references={[{ label: '触发输入 · message', value: '${workflow.input.message}', source: '触发输入', type: 'string' }]} workflowId={1} nodeTitle={title} readOnly={false} onChange={setValue} onNodeTitleChange={setTitle} /></App>;
}

describe('OpsPilot 风格原子表单', () => {
  it('意图分类使用编号列表并把实际处理内容收进运行数据', () => {
    render(<IntentHarness />);

    expect(screen.getByText('通用模型')).not.toBeNull();
    expect(screen.getByText('分类 1')).not.toBeNull();
    expect(screen.queryByText('输入参数')).toBeNull();
    expect(screen.queryByText('输出参数')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /添加意图/ }));
    expect(screen.getByText('分类 2')).not.toBeNull();

    fireEvent.click(screen.getByText('运行数据'));
    expect(screen.getByText('待分类内容')).not.toBeNull();
    expect(screen.getByDisplayValue('${workflow.input.message}')).not.toBeNull();
  });

  it('智能体表单提供 OpsPilot 式资源入口和 Markdown 拖拽区', () => {
    render(<App><OpsPilotAtomForm
      atomKey="bklite_agent"
      schema={{ type: 'object', required: ['agent_id', 'message'], properties: {
        agent_id: { type: 'integer', title: '智能体', enum: [2], 'x-enum-labels': { '2': '巡检助手' } },
        prompt: { type: 'string', title: '补充提示词', 'x-widget': 'textarea' },
        knowledge_files: { type: 'array', title: '上传知识' },
        message: { type: 'string', title: '输入内容' },
        memory_context: { type: 'string', title: '记忆上下文' },
      } }}
      value={{ agent_id: 2, message: '检查主机' }}
      references={[]}
      workflowId={null}
      nodeTitle="智能体"
      readOnly={false}
      onChange={vi.fn()}
      onNodeTitleChange={vi.fn()}
    /></App>);

    expect(screen.getByRole('link', { name: /新增智能体/ }).getAttribute('href')).toBe('/opspilot/skill');
    expect(screen.getByText('点击或拖拽 Markdown 文件到此区域上传')).not.toBeNull();
    expect(screen.getByText('首次上传前请先保存流程草稿')).not.toBeNull();
  });

  it('记忆写入使用记忆空间和模型选择器，写入内容仍可引用上游结果', () => {
    const memorySchema: JsonSchema = {
      type: 'object',
      required: ['memory_space_id', 'content', 'model_id'],
      properties: {
        memory_space_id: {
          type: 'integer',
          title: '记忆空间',
          enum: [3],
          'x-enum-labels': { '3': '运维记忆' },
          'x-enum-metadata': { '3': { scope: 'team', default_model: '8' } },
        },
        content: { type: 'string', title: '记忆内容', 'x-widget': 'textarea' },
        title: { type: 'string', title: '记忆标题' },
        model_id: { type: 'integer', title: '处理模型', enum: [8], 'x-enum-labels': { '8': '知识库模型' } },
        write_batch_size: { type: 'integer', title: '分批大小', default: 30, minimum: 1, maximum: 500 },
      },
    };
    const onChange = vi.fn();
    render(<App><OpsPilotAtomForm
      atomKey="bklite_memory_write"
      schema={memorySchema}
      value={{ memory_space_id: 3, model_id: 8, write_batch_size: 30, content: '${agent.output.answer}' }}
      references={[{ label: '智能体 · answer', value: '${agent.output.answer}', source: '智能体', type: 'string' }]}
      workflowId={1}
      nodeTitle="记忆写入"
      readOnly={false}
      onChange={onChange}
      onNodeTitleChange={vi.fn()}
    /></App>);

    expect(screen.getByText('运维记忆')).not.toBeNull();
    expect(screen.getByText('知识库模型')).not.toBeNull();
    expect(screen.getByRole('link', { name: /新增记忆空间/ }).getAttribute('href')).toBe('/opspilot/memory');
    fireEvent.click(screen.getByText('运行数据'));
    expect(screen.getByText('记忆内容')).not.toBeNull();
    expect(screen.getByDisplayValue('${agent.output.answer}')).not.toBeNull();
  });

  it('记忆读取把检索数量收进高级设置', () => {
    render(<App><OpsPilotAtomForm
      atomKey="bklite_memory_read"
      schema={{ type: 'object', required: ['memory_space_id', 'query'], properties: {
        memory_space_id: { type: 'integer', title: '记忆空间', enum: [3], 'x-enum-labels': { '3': '运维记忆' } },
        query: { type: 'string', title: '检索内容', 'x-widget': 'textarea' },
        top_k: { type: 'integer', title: '返回条数', default: 5, minimum: 1, maximum: 20 },
      } }}
      value={{ memory_space_id: 3, query: '${workflow.input.question}', top_k: 5 }}
      references={[{ label: '触发输入 · question', value: '${workflow.input.question}', source: '触发输入', type: 'string' }]}
      workflowId={1}
      nodeTitle="记忆读取"
      readOnly={false}
      onChange={vi.fn()}
      onNodeTitleChange={vi.fn()}
    /></App>);

    fireEvent.click(screen.getByText('高级设置'));
    expect(screen.getByText('返回条数')).not.toBeNull();
    fireEvent.click(screen.getByText('运行数据'));
    expect(screen.getByText('检索内容')).not.toBeNull();
    expect(screen.getByDisplayValue('${workflow.input.question}')).not.toBeNull();
  });

  it('对外通知提供可选附件拖入，并把历史用户名归一成用户 ID 后回显标签', async () => {
    const onChange = vi.fn();
    const notificationSchema: JsonSchema = {
      type: 'object',
      required: ['notification_type', 'channel_id', 'recipients', 'title', 'body'],
      properties: {
        notification_type: {
          type: 'string',
          title: '通知类型',
          enum: ['EMAIL'],
          default: 'EMAIL',
          'x-enum-labels': { EMAIL: '邮件' },
        },
        channel_id: {
          type: 'integer',
          title: '通知渠道',
          enum: [3],
          'x-enum-labels': { '3': '值班邮箱' },
        },
        recipients: {
          type: 'array',
          title: '收件人',
          items: {
            type: 'string',
            enum: ['1'],
            'x-enum-labels': { '1': '管理员 (admin)' },
            'x-enum-usernames': { '1': 'admin' },
          },
        },
        title: { type: 'string', title: '通知标题' },
        body: { type: 'string', title: '通知内容', 'x-widget': 'textarea' },
        report_artifact: { type: 'object', title: '附件' },
      },
    };

    render(<App><OpsPilotAtomForm
      atomKey="bklite_notification"
      schema={notificationSchema}
      value={{
        notification_type: 'EMAIL',
        channel_id: 3,
        recipients: ['admin'],
        title: '巡检完成',
        body: '已完成',
      }}
      references={[{ label: '文档生成 · artifact', value: '${report.output.artifact}', source: '文档生成', type: 'object' }]}
      workflowId={1}
      nodeTitle="系统通知"
      readOnly={false}
      onChange={onChange}
      onNodeTitleChange={vi.fn()}
    /></App>);

    expect(screen.getByText('附件')).not.toBeNull();
    const attachmentItem = screen.getByText('附件').closest('.ant-form-item');
    expect(attachmentItem?.querySelector('.ant-form-item-extra')).toBeNull();
    const attachmentHelp = attachmentItem?.querySelector('[aria-label="question-circle"]');
    expect(attachmentHelp).not.toBeNull();
    await userEvent.hover(attachmentHelp!);
    expect((await screen.findByRole('tooltip')).textContent).toContain('可选，拖入上游报告产物');
    expect(screen.queryByText('邮件通知会自动附带本次工作流运行中生成的全部附件，无需手动选择。')).toBeNull();
    expect(await screen.findByText('管理员 (admin)')).not.toBeNull();
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ recipients: ['1'] }));
  });

  it('内置发起人表达式回显为当前登录用户，不写入用户编号', async () => {
    currentUser.username = 'whj';
    currentUser.userId = '2';
    const onChange = vi.fn();
    const notificationSchema: JsonSchema = {
      type: 'object',
      properties: {
        notification_type: { type: 'string', enum: ['EMAIL'], default: 'EMAIL' },
        channel_id: { type: 'integer', enum: [3], 'x-enum-labels': { '3': '值班邮箱' } },
        recipients: {
          type: 'array',
          items: {
            type: 'string',
            enum: ['1', '2'],
            'x-enum-labels': { '1': '管理员 (admin)', '2': '王宏基 (whj)' },
            'x-enum-usernames': { '1': 'admin', '2': 'whj' },
          },
        },
        title: { type: 'string' },
        body: { type: 'string', 'x-widget': 'textarea' },
      },
    };

    render(<App><OpsPilotAtomForm
      atomKey="bklite_notification"
      schema={notificationSchema}
      value={{
        notification_type: 'EMAIL',
        channel_id: 3,
        recipients: ['${workflow.input.__system.actor_name}'],
        title: '巡检完成',
        body: '已完成',
      }}
      references={[]}
      workflowId={1}
      nodeTitle="对外通知"
      readOnly
      onChange={onChange}
      onNodeTitleChange={vi.fn()}
    /></App>);

    expect(await screen.findByText('王宏基 (whj)')).not.toBeNull();
    expect(screen.queryByText('发起人')).toBeNull();
    expect(screen.queryByText('${workflow.input.__system.actor_name}')).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
    currentUser.username = 'admin';
    currentUser.userId = '1';
  });

  it('通知方式只列出当前类别的渠道，并且名称不带渠道类型', async () => {
    const user = userEvent.setup();
    const notificationSchema: JsonSchema = {
      type: 'object',
      required: ['notification_type', 'channel_id', 'body'],
      properties: {
        notification_type: {
          type: 'string',
          enum: ['EMAIL', 'WECOM_BOT'],
          default: 'EMAIL',
          'x-enum-labels': { EMAIL: '邮件', WECOM_BOT: '企业微信机器人' },
        },
        channel_id: {
          type: 'integer',
          enum: [3, 4, 5],
          'x-enum-labels': { '3': '邮件服务器', '4': '告警中心', '5': '可观测群' },
          'x-enum-channel-types': { '3': 'email', '4': 'nats', '5': 'enterprise_wechat_bot' },
        },
        body: { type: 'string', title: '通知内容' },
      },
    };
    function NotificationHarness() {
      const [value, setValue] = useState<Record<string, unknown>>({ notification_type: 'EMAIL', body: '已完成' });
      return <App><OpsPilotAtomForm
        atomKey="bklite_notification"
        schema={notificationSchema}
        value={value}
        references={[]}
        workflowId={1}
        nodeTitle="对外通知"
        readOnly={false}
        onChange={setValue}
        onNodeTitleChange={vi.fn()}
      /></App>;
    }

    render(<NotificationHarness />);

    await waitFor(() => {
      expect(screen.getByTitle('邮件服务器')).not.toBeNull();
    });
    await user.click(screen.getByRole('combobox'));
    expect((await screen.findAllByText('邮件服务器')).length).toBeGreaterThan(0);
    expect(screen.queryByText('告警中心')).toBeNull();
    expect(screen.queryByText('可观测群')).toBeNull();
    expect(screen.queryByText(/nats|enterprise_wechat_bot/)).toBeNull();

    await user.click(screen.getByText('企业微信机器人'));
    await waitFor(() => {
      expect(screen.getByTitle('可观测群')).not.toBeNull();
    });
    await user.click(screen.getByRole('combobox'));
    expect((await screen.findAllByText('可观测群')).length).toBeGreaterThan(0);
    expect(screen.queryByText('邮件服务器')).toBeNull();
    expect(screen.queryByText('告警中心')).toBeNull();
  });

  it('通知方式允许清空且不会被默认渠道立即写回', async () => {
    const user = userEvent.setup();
    const notificationSchema: JsonSchema = {
      type: 'object',
      required: ['notification_type', 'channel_id', 'body'],
      properties: {
        notification_type: {
          type: 'string',
          enum: ['EMAIL'],
          default: 'EMAIL',
          'x-enum-labels': { EMAIL: '邮件' },
        },
        channel_id: {
          type: 'integer',
          enum: [3],
          'x-enum-labels': { '3': '邮件服务器' },
          'x-enum-channel-types': { '3': 'email' },
        },
        body: { type: 'string', title: '通知内容' },
      },
    };
    function ClearChannelHarness() {
      const [value, setValue] = useState<Record<string, unknown>>({ notification_type: 'EMAIL', channel_id: 3, body: '已完成' });
      return <App><OpsPilotAtomForm
        atomKey="bklite_notification"
        schema={notificationSchema}
        value={value}
        references={[]}
        workflowId={1}
        nodeTitle="对外通知"
        readOnly={false}
        onChange={setValue}
        onNodeTitleChange={vi.fn()}
      /><div data-testid="channel-dump">{String(value.channel_id ?? '')}</div></App>;
    }
    render(<ClearChannelHarness />);
    await waitFor(() => {
      expect(screen.getByTitle('邮件服务器')).not.toBeNull();
    });
    const select = screen.getByRole('combobox').closest('.ant-select');
    expect(select).not.toBeNull();
    fireEvent.mouseEnter(select!);
    const clear = select!.querySelector('.ant-select-clear');
    expect(clear).not.toBeNull();
    await user.click(clear!);
    await waitFor(() => {
      expect(screen.getByTestId('channel-dump').textContent).toBe('');
    });
    expect(screen.queryByTitle('邮件服务器')).toBeNull();
  });

  it('通知方式在渠道类型不匹配时回落到邮件列表第一项，不显示裸数字 1', async () => {
    const notificationSchema: JsonSchema = {
      type: 'object',
      required: ['notification_type', 'body'],
      properties: {
        notification_type: {
          type: 'string',
          enum: ['EMAIL', 'WECOM_BOT'],
          default: 'EMAIL',
          'x-enum-labels': { EMAIL: '邮件', WECOM_BOT: '企业微信机器人' },
        },
        channel_id: {
          type: 'integer',
          enum: [1, 3],
          'x-enum-labels': { '1': '告警中心', '3': '邮件服务器' },
          'x-enum-channel-types': { '1': 'nats', '3': 'email' },
        },
        recipients: {
          type: 'array',
          title: '通知人',
          items: { type: 'string', enum: ['9'], 'x-enum-labels': { '9': '值班 (oncall)' } },
        },
        title: { type: 'string', title: '通知标题' },
        body: { type: 'string', title: '通知内容' },
      },
    };
    function DirtyChannelHarness() {
      const [value, setValue] = useState<Record<string, unknown>>({
        notification_type: 'EMAIL',
        channel_id: 1,
        body: '已完成',
        title: '标题',
        recipients: ['9'],
      });
      return <App><OpsPilotAtomForm
        atomKey="bklite_notification"
        schema={notificationSchema}
        value={value}
        references={[]}
        workflowId={1}
        nodeTitle="发送巡检通知"
        readOnly={false}
        onChange={setValue}
        onNodeTitleChange={vi.fn()}
      /></App>;
    }
    render(<DirtyChannelHarness />);

    await waitFor(() => {
      expect(screen.getByTitle('邮件服务器')).not.toBeNull();
    });
    expect(screen.queryByText('告警中心')).toBeNull();
    expect(screen.getByText('通知方式').closest('.ant-form-item')?.querySelector('.ant-form-item-required')).not.toBeNull();
    expect(screen.getByText('通知人').closest('.ant-form-item')?.querySelector('.ant-form-item-required')).not.toBeNull();
    expect(screen.getByText('通知标题').closest('.ant-form-item')?.querySelector('.ant-form-item-required')).not.toBeNull();
  });

  it('HTTP 请求参数与请求头采用 OpsPilot 键值行布局', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const httpSchema: JsonSchema = {
      type: 'object',
      required: ['method', 'url'],
      properties: {
        method: { type: 'string', enum: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], default: 'GET' },
        url: { type: 'string', title: 'URL' },
        query: { type: 'object', title: '查询参数' },
        headers: { type: 'object', title: '请求头' },
      },
    };

    render(<App><OpsPilotAtomForm
      atomKey="bklite_http_request"
      schema={httpSchema}
      value={{ method: 'GET', url: 'https://example.com/health', query: {}, headers: {} }}
      references={[]}
      workflowId={1}
      nodeTitle="HTTP 请求"
      readOnly={false}
      onChange={onChange}
      onNodeTitleChange={vi.fn()}
    /></App>);

    expect(screen.getByText('请求参数')).not.toBeNull();
    expect(screen.getByText('请求头')).not.toBeNull();
    expect(screen.getByDisplayValue('https://example.com/health')).not.toBeNull();
    expect(screen.getByPlaceholderText('输入URL')).not.toBeNull();
    expect(screen.queryByText('选择连接')).toBeNull();
    expect(screen.getAllByText('str')).toHaveLength(2);
    expect(screen.getAllByPlaceholderText('输入或引用参数值')).toHaveLength(2);
    expect(screen.getAllByPlaceholderText('输入参数名')).toHaveLength(2);
    // method 旁的 drop-guard 不得 w-full，否则会挤扁 URL 输入框
    const apiLabel = screen.getByText('API');
    const apiRow = apiLabel.closest('.ant-form-item')?.querySelector('.flex.w-full.items-center');
    const methodGuard = apiRow?.querySelector('[data-testid="workflow-reference-drop-guard"]');
    expect(methodGuard?.className).toContain('shrink-0');
    expect(methodGuard?.className).not.toContain('w-full');
    expect(apiRow?.querySelector('.min-w-0.flex-1')).not.toBeNull();

    const removeButtons = screen.getAllByRole('button', { name: '删除参数' });
    expect(removeButtons[0].hasAttribute('disabled')).toBe(true);

    await user.click(screen.getAllByRole('button', { name: '添加参数' })[0]);
    expect(screen.getAllByPlaceholderText('输入参数名').length).toBeGreaterThan(2);
    expect(screen.getAllByRole('button', { name: '删除参数' })[0].hasAttribute('disabled')).toBe(false);
  });

  it('节点名称不支持 $ 提示；HTTP 参数名仅 string 且支持 $', async () => {
    const user = userEvent.setup();
    const references = [
      { label: '触发输入 · message', value: '${workflow.input.message}', source: '触发输入', type: 'string', displayName: 'message' },
      { label: '通知 · 全部输出', value: '${notification.output}', source: '通知', type: 'object', displayName: '全部输出' },
    ];
    function HttpHarness() {
      const [value, setValue] = useState<Record<string, unknown>>({ method: 'GET', url: 'https://example.com', query: {}, headers: {} });
      const [title, setTitle] = useState('HTTP 请求');
      return <App><OpsPilotAtomForm
        atomKey="bklite_http_request"
        schema={{
          type: 'object',
          properties: {
            method: { type: 'string', enum: ['GET'], default: 'GET' },
            url: { type: 'string', title: 'URL' },
            query: { type: 'object', title: '查询参数' },
            headers: { type: 'object', title: '请求头' },
          },
        }}
        value={value}
        references={references}
        workflowId={1}
        nodeTitle={title}
        readOnly={false}
        onChange={setValue}
        onNodeTitleChange={setTitle}
      /></App>;
    }
    render(<HttpHarness />);

    const titleInput = screen.getByDisplayValue('HTTP 请求');
    await user.click(titleInput);
    await user.type(titleInput, '$');
    expect(screen.queryByTestId('workflow-template-suggestions')).toBeNull();
    expect(screen.getByDisplayValue('HTTP 请求$')).not.toBeNull();

    const titleGuard = titleInput.closest('[data-testid="workflow-reference-drop-guard"]');
    expect(titleGuard).not.toBeNull();
    fireEvent.drop(titleGuard!, {
      dataTransfer: {
        dropEffect: 'copy',
        types: ['application/x-bklite-workflow-reference'],
        getData: vi.fn().mockReturnValue('${workflow.input.message}'),
      },
    });
    expect(screen.getByDisplayValue('HTTP 请求$')).not.toBeNull();
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/节点名称只用于画布展示/);
    });

    const paramName = screen.getAllByPlaceholderText('输入参数名')[0];
    await user.click(paramName);
    await user.clear(paramName);
    await user.type(paramName, '$');
    expect(await screen.findByTestId('workflow-template-suggestions')).not.toBeNull();
    expect(screen.getByText('${workflow.input.message}')).not.toBeNull();
    expect(screen.queryByText('${notification.output}')).toBeNull();
  });
});
