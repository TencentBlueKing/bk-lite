import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState, type ReactNode } from 'react';
import { beforeAll, vi } from 'vitest';

import { resolveSchemaForNodeInput, SchemaNodeForm, WORKFLOW_REFERENCE_MIME } from '../components/schema-node-form';
import type { JsonSchema } from '../lib/types';

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

function Harness({ schema, initial, uiSchema, fieldActions, readOnly = false }: { schema: JsonSchema; initial: Record<string, unknown>; uiSchema?: Record<string, unknown>; fieldActions?: Record<string, ReactNode>; readOnly?: boolean }) {
  const [value, setValue] = useState(initial);
  return <App><SchemaNodeForm schema={schema} uiSchema={uiSchema} value={value} references={[{ label: '触发输入 · owner', value: '${workflow.input.owner}', source: '触发输入', type: 'string' }]} readOnly={readOnly} onChange={setValue} fieldActions={fieldActions} /></App>;
}

describe('原子 Schema 参数表单', () => {
  it('string 字段拖入上游引用时插入到文本中，而不是整格替换为只读芯片', () => {
    render(<Harness schema={{ type: 'object', properties: { owner: { type: 'string', title: '负责人' } } }} initial={{ owner: 'alice' }} />);

    const dataTransfer = {
      dropEffect: 'none',
      types: [WORKFLOW_REFERENCE_MIME],
      getData: vi.fn()
        .mockImplementationOnce(() => '')
        .mockImplementation((format: string) => format === WORKFLOW_REFERENCE_MIME ? '${workflow.input.owner}' : ''),
    };
    fireEvent.dragOver(screen.getByTestId('workflow-reference-dropzone'), { dataTransfer });
    fireEvent.drop(screen.getByTestId('workflow-reference-dropzone'), { dataTransfer });

    expect(screen.getByDisplayValue('alice${workflow.input.owner}')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '清除字段引用' })).toBeNull();
  });

  it('宽收文本表面允许拖入 object；仅 string 表面会拒绝', () => {
    function ObjectHarness({ surface }: { surface: 'coerce' | 'string-only' }) {
      const [value, setValue] = useState<Record<string, unknown>>({ body: '生成内容：' });
      return <App><SchemaNodeForm
        schema={{ type: 'object', properties: { body: { type: 'string', title: '通知内容', 'x-widget': 'textarea', 'x-text-surface': surface } } }}
        value={value}
        references={[{ label: '作业 · 全部输出', value: '${job.output}', source: '作业', type: 'object', displayName: '全部输出' }]}
        onChange={setValue}
      /></App>;
    }
    const { unmount } = render(<ObjectHarness surface="coerce" />);
    const dataTransfer = {
      dropEffect: 'none',
      types: [WORKFLOW_REFERENCE_MIME],
      getData: vi.fn().mockImplementation((format: string) => format === WORKFLOW_REFERENCE_MIME ? '${job.output}' : ''),
    };
    fireEvent.drop(screen.getByTestId('workflow-reference-dropzone'), { dataTransfer });
    expect(screen.getByDisplayValue('生成内容：${job.output}')).not.toBeNull();
    unmount();

    render(<ObjectHarness surface="string-only" />);
    fireEvent.drop(screen.getByTestId('workflow-reference-dropzone'), { dataTransfer });
    expect(screen.getByDisplayValue('生成内容：')).not.toBeNull();
  });

  it('布尔开关保持原生宽度并左对齐', () => {
    render(<Harness schema={{ type: 'object', properties: { enabled: { type: 'boolean', title: '是否启用' } } }} initial={{ enabled: true }} />);

    expect(screen.getByRole('switch').classList.contains('self-start')).toBe(true);
  });

  it('传入节点名称回调时展示名称输入', () => {
    const onNodeTitleChange = vi.fn();
    render(<App><SchemaNodeForm
      schema={{ type: 'object', properties: { owner: { type: 'string', title: '负责人' } } }}
      value={{}}
      nodeTitle="HTTP 请求"
      onChange={vi.fn()}
      onNodeTitleChange={onNodeTitleChange}
    /></App>);

    fireEvent.change(screen.getByDisplayValue('HTTP 请求'), { target: { value: '查询状态' } });
    expect(onNodeTitleChange).toHaveBeenCalledWith('查询状态');
  });

  it('根据注册项选择解析对应的参数 Schema', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: { operation: { type: 'string', enum: ['health', 'inventory'] } },
      required: ['operation'],
    };
    const uiSchema = {
      capability_selector: {
        kind: 'CONTROLLED_OPERATION',
        field: 'operation',
        profiles: [
          { key: 'health', version: '1.0.0', name: '健康采集', description: '', input_schema: { type: 'object', properties: { threshold: { type: 'number' } }, required: ['threshold'] } },
          { key: 'inventory', version: '1.0.0', name: '资产采集', description: '', input_schema: { type: 'object', properties: { include_network: { type: 'boolean' } }, required: [] } },
        ],
      },
    };

    const resolved = resolveSchemaForNodeInput(schema, uiSchema, { operation: 'inventory' });

    expect(Object.keys(resolved.properties || {})).toEqual(['operation', 'include_network']);
    expect(resolved.required).toEqual(['operation']);
  });

  it('字段映射使用键值编辑器而不是禁用的整块 JSON', () => {
    render(<Harness schema={{ type: 'object', properties: { values: { type: 'object', title: '字段映射', 'x-widget': 'key-value', additionalProperties: { jsonEditorAllowed: true } } } }} initial={{ values: { owner: 'alice' } }} />);

    expect(screen.getByDisplayValue('owner')).not.toBeNull();
    expect(screen.getByDisplayValue('alice')).not.toBeNull();
    expect(screen.queryByText('该结构没有可生成表单的子字段')).toBeNull();
  });

  it('作业执行脚本使用对应语言的代码编辑器', async () => {
    render(<Harness
      schema={{ type: 'object', properties: {
        linux_script_content: { type: 'string', title: 'Linux 脚本' },
        windows_script_content: { type: 'string', title: 'Windows PowerShell 脚本' },
      } }}
      uiSchema={{
        linux_script_content: { 'ui:widget': 'code', 'ui:language': 'sh', 'ui:help': 'Linux 目标必填' },
        windows_script_content: { 'ui:widget': 'code', 'ui:language': 'powershell', 'ui:help': 'Windows 目标必填' },
      }}
      initial={{ linux_script_content: 'uptime', windows_script_content: 'Get-ComputerInfo' }}
    />);

    const linuxEditor = screen.getByRole('textbox', { name: 'code-editor-sh' }) as HTMLTextAreaElement;
    const windowsEditor = screen.getByRole('textbox', { name: 'code-editor-powershell' }) as HTMLTextAreaElement;
    expect(linuxEditor.value).toBe('uptime');
    expect(windowsEditor.value).toBe('Get-ComputerInfo');
    expect(linuxEditor.dataset.theme).toBe('monokai');
    expect(windowsEditor.dataset.theme).toBe('monokai');
    expect(linuxEditor.dataset.height).toBe('320px');
    expect(windowsEditor.dataset.height).toBe('320px');
    const linuxHelp = screen.getByText('Linux 脚本').closest('.ant-form-item')?.querySelector('[aria-label="question-circle"]');
    const windowsHelp = screen.getByText('Windows PowerShell 脚本').closest('.ant-form-item')?.querySelector('[aria-label="question-circle"]');
    expect(linuxHelp).not.toBeNull();
    expect(windowsHelp).not.toBeNull();
    expect(screen.getByText('Linux 脚本').closest('.ant-form-item')?.querySelector('.ant-form-item-extra')).toBeNull();
    expect(screen.getByText('Windows PowerShell 脚本').closest('.ant-form-item')?.querySelector('.ant-form-item-extra')).toBeNull();
    await userEvent.hover(linuxHelp!);
    expect((await screen.findByRole('tooltip')).textContent).toContain('Linux 目标必填');
  });

  it('目标主机支持手动录入并在字段旁展示选择入口', async () => {
    render(<Harness
      schema={{ type: 'object', properties: { targets: { type: 'array', title: '目标主机', description: '可从左侧拖入兼容字段或手动填写，也可从作业平台选择主机', items: { type: 'string' } } } }}
      initial={{ targets: [] }}
      fieldActions={{ targets: <button type="button">选择作业平台主机</button> }}
    />);

    expect(screen.getByRole('button', { name: '选择作业平台主机' })).not.toBeNull();
    expect((screen.getByRole('combobox') as HTMLInputElement).disabled).toBe(false);
    expect(screen.queryByText('该结构没有可生成表单的子字段')).toBeNull();
    const targetsItem = screen.getByText('目标主机').closest('.ant-form-item');
    expect(targetsItem?.querySelector('.ant-form-item-extra')).toBeNull();
    const targetsHelp = targetsItem?.querySelector('[aria-label="question-circle"]');
    expect(targetsHelp).not.toBeNull();
    await userEvent.hover(targetsHelp!);
    expect((await screen.findByRole('tooltip')).textContent).toContain('可从左侧拖入兼容字段或手动填写，也可从作业平台选择主机');
  });

  it('失效引用使用表单校验文案而不是 Alert', () => {
    render(<Harness
      schema={{ type: 'object', properties: { targets: { type: 'array', title: '目标主机', items: { type: 'string' } } } }}
      initial={{ targets: '${workflow.input.missing_targets}' }}
    />);

    expect(screen.getByDisplayValue('${workflow.input.missing_targets}')).not.toBeNull();
    expect(screen.getByText(/失效引用：来源不存在/)).not.toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('部分失败处理使用简洁且含义完整的选项文案', () => {
    render(<Harness
      schema={{ type: 'object', properties: { failure_policy: {
        type: 'string', title: '部分失败处理', enum: ['FAIL_NODE', 'COLLECT'],
        'x-enum-labels': { FAIL_NODE: '失败并终止', COLLECT: '记录失败并继续' },
      } } }}
      initial={{ failure_policy: 'FAIL_NODE' }}
    />);

    fireEvent.mouseDown(screen.getByRole('combobox'));
    expect(screen.getAllByText('失败并终止').length).toBeGreaterThan(0);
    expect(screen.getByText('记录失败并继续')).not.toBeNull();
  });

  it('查询列表可以追加一条 SELECT', async () => {
    const user = userEvent.setup();
    render(<Harness
      schema={{
        type: 'object',
        properties: {
          queries: {
            type: 'array',
            title: '查询',
            'x-widget': 'query-list',
            'x-binding': 'literal-only',
            items: { type: 'object', properties: { name: { type: 'string' }, sql: { type: 'string' } } },
          },
        },
      }}
      initial={{ queries: [] }}
    />);

    await user.click(screen.getByRole('button', { name: /添加查询/ }));
    const editor = screen.getByRole('textbox', { name: 'code-editor-sql' });
    expect(screen.getByPlaceholderText('结果名')).not.toBeNull();
    expect(editor).not.toBeNull();
    expect(editor.getAttribute('data-height')).toBe('160px');
    await user.type(editor, 'SELECT 1');
    expect((editor as HTMLTextAreaElement).value).toBe('SELECT 1');
    fireEvent.click(screen.getByRole('button', { name: 'SQL 写法说明' }));
    expect(screen.getByRole('dialog', { name: 'SQL 写法说明' }).className).toContain('customDrawer');
    expect(screen.getByText('输入位置')).not.toBeNull();
    expect(screen.getAllByText(/input\.payload/).length).toBeGreaterThan(0);
    expect(screen.getByText(/json_each 将数组拆成多行/)).not.toBeNull();
    expect(screen.getByText('写入限制')).not.toBeNull();
  });

  it('只读时文本、数字、下拉和 JSON 都不能改，拖入引用也不会写入', () => {
    render(<Harness
      readOnly
      schema={{
        type: 'object',
        properties: {
          owner: { type: 'string', title: '负责人' },
          count: { type: 'integer', title: '次数' },
          level: { type: 'string', title: '级别', enum: ['low', 'high'], 'x-binding': 'literal-only' },
          payload: { type: 'object', title: '数据', 'x-widget': 'json', jsonEditorAllowed: true, 'x-binding': 'literal-only' },
        },
      }}
      initial={{ owner: 'keep', count: 3, level: 'low', payload: { ok: true } }}
    />);

    expect(screen.getByDisplayValue('keep').hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('spinbutton').hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('combobox').hasAttribute('disabled')).toBe(true);
    expect(screen.getByDisplayValue(/"ok": true/).hasAttribute('disabled')).toBe(true);

    const dataTransfer = {
      dropEffect: 'none',
      types: [WORKFLOW_REFERENCE_MIME],
      getData: vi.fn().mockImplementation((format: string) => format === WORKFLOW_REFERENCE_MIME ? '${workflow.input.owner}' : ''),
    };
    fireEvent.drop(screen.getByTestId('workflow-reference-dropzone'), { dataTransfer });
    expect(screen.getByDisplayValue('keep')).not.toBeNull();
    expect(screen.queryByDisplayValue(/workflow\.input\.owner/)).toBeNull();
  });

  it('只读时带图标的引用输入框也使用禁用样式', () => {
    render(<Harness
      readOnly
      schema={{ type: 'object', properties: { artifact: { type: 'object', title: '附件' } } }}
      initial={{ artifact: '${workflow.input.owner}' }}
    />);

    const input = screen.getByDisplayValue('${workflow.input.owner}');
    expect(input.hasAttribute('disabled')).toBe(true);
    expect(input.closest('.ant-input-affix-wrapper')?.className).toContain('ant-input-affix-wrapper-disabled');
  });

  it('只读时查询 SQL 仍可查看但不能改', () => {
    render(<Harness
      readOnly
      schema={{
        type: 'object',
        properties: {
          queries: {
            type: 'array',
            title: '查询',
            'x-widget': 'query-list',
            'x-binding': 'literal-only',
            items: { type: 'object', properties: { name: { type: 'string' }, sql: { type: 'string' } } },
          },
        },
      }}
      initial={{ queries: [{ name: 'summary', sql: 'SELECT 1' }] }}
    />);

    const editor = screen.getByRole('textbox', { name: 'code-editor-sql' });
    expect(editor).toHaveProperty('readOnly', true);
    expect((editor as HTMLTextAreaElement).value).toBe('SELECT 1');
    expect(screen.queryByRole('button', { name: /添加查询/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /删除查询/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'SQL 写法说明' })).not.toBeNull();
  });

  it('超时清空后保持空白，不回填默认值', async () => {
    const user = userEvent.setup();
    let latest = { timeout_seconds: 30 as number | undefined };
    function Probe() {
      const [value, setValue] = useState(latest);
      return <App><SchemaNodeForm
        schema={{
          type: 'object',
          properties: {
            timeout_seconds: {
              type: 'integer',
              title: '超时（秒）',
              minimum: 1,
              maximum: 120,
              default: 30,
              'x-binding': 'literal-only',
            },
          },
        }}
        value={value}
        onChange={(next) => {
          latest = next as typeof latest;
          setValue(next);
        }}
      /></App>;
    }
    render(<Probe />);
    const input = screen.getByRole('spinbutton');
    await user.clear(input);
    expect(latest).toEqual({});
    expect((input as HTMLInputElement).value).toBe('');
  });
});
