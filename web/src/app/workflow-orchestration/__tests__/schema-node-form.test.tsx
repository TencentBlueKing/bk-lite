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

function Harness({ schema, initial, uiSchema, fieldActions }: { schema: JsonSchema; initial: Record<string, unknown>; uiSchema?: Record<string, unknown>; fieldActions?: Record<string, ReactNode> }) {
  const [value, setValue] = useState(initial);
  return <App><SchemaNodeForm schema={schema} uiSchema={uiSchema} value={value} references={[{ label: '触发输入 · owner', value: '${workflow.input.owner}', source: '触发输入', type: 'string' }]} onChange={setValue} fieldActions={fieldActions} /></App>;
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
});
