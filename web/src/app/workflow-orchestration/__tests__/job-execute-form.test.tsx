import './test-mocks';

import { App } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { JobExecuteForm } from '../components/job-execute-form';
import { WORKFLOW_REFERENCE_MIME } from '../components/schema-node-form';

vi.mock('@/utils/request', () => ({
  default: () => ({ get: vi.fn().mockResolvedValue({ items: [] }), post: vi.fn(), put: vi.fn(), del: vi.fn() }),
}));

describe('作业执行脚本本地暂存', () => {
  afterEach(cleanup);
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

  it('切换脚本类型时本地暂存，写回节点的只有当前类型', () => {
    let value: Record<string, unknown> = {
      script_type: 'shell',
      script_content: 'echo hello',
      targets: [],
    };
    const onChange = vi.fn((next: Record<string, unknown>) => {
      value = next;
      rerender(<IntlProvider locale="zh-CN" messages={{}}><App><JobExecuteForm
        value={value}
        references={[]}
        readOnly={false}
        onChange={onChange}
      /></App></IntlProvider>);
    });

    const { rerender } = render(<IntlProvider locale="zh-CN" messages={{}}><App><JobExecuteForm
      value={value}
      references={[]}
      readOnly={false}
      onChange={onChange}
    /></App></IntlProvider>);

    const editor = screen.getByLabelText('script-editor-shell');
    expect(editor).toHaveProperty('value', 'echo hello');
    fireEvent.change(editor, { target: { value: 'echo hello#edited' } });
    expect(value).toEqual(expect.objectContaining({ script_type: 'shell', script_content: 'echo hello#edited' }));

    fireEvent.click(screen.getByRole('button', { name: 'powershell' }));
    expect(value).toEqual(expect.objectContaining({ script_type: 'powershell', script_content: '' }));
    expect(screen.getByTestId('script-editor-lang').textContent).toBe('powershell');

    fireEvent.change(screen.getByLabelText('script-editor-powershell'), { target: { value: 'Write-Host ok' } });
    expect(value).toEqual(expect.objectContaining({ script_type: 'powershell', script_content: 'Write-Host ok' }));

    fireEvent.click(screen.getByRole('button', { name: 'shell' }));
    expect(value).toEqual(expect.objectContaining({ script_type: 'shell', script_content: 'echo hello#edited' }));
    expect(screen.getByLabelText('script-editor-shell')).toHaveProperty('value', 'echo hello#edited');
    expect(screen.getByRole('button', { name: '脚本输出说明' })).not.toBeNull();
  });

  it('执行参数用 tag 输入，空格拆成多个参数', async () => {
    let value: Record<string, unknown> = {
      script_type: 'shell',
      script_content: 'echo hello',
      execution_params: 'a b',
      targets: [],
    };
    const onChange = vi.fn((next: Record<string, unknown>) => {
      value = next;
      rerender(<IntlProvider locale="zh-CN" messages={{}}><App><JobExecuteForm
        value={value}
        references={[]}
        readOnly={false}
        onChange={onChange}
      /></App></IntlProvider>);
    });

    const { rerender } = render(<IntlProvider locale="zh-CN" messages={{}}><App><JobExecuteForm
      value={value}
      references={[]}
      readOnly={false}
      onChange={onChange}
    /></App></IntlProvider>);

    expect(screen.getByText('a')).not.toBeNull();
    expect(screen.getByText('b')).not.toBeNull();
    const paramsItem = screen.getByText('执行参数').closest('.ant-form-item');
    expect(paramsItem?.querySelector('.ant-form-item-extra')).toBeNull();
    const paramsHelp = paramsItem?.querySelector('[aria-label="question-circle"]');
    expect(paramsHelp).not.toBeNull();
    await userEvent.hover(paramsHelp!);
    expect((await screen.findByRole('tooltip')).textContent).toContain('回车添加参数，也可从左侧拖入字段');
    expect(screen.queryByText(/Shell \/ Python 仅能选择/)).toBeNull();
  });

  it('执行参数可拖入 string 引用作为单个 tag', () => {
    let value: Record<string, unknown> = {
      script_type: 'shell',
      script_content: 'echo hello',
      execution_params: 'a',
      targets: [],
    };
    const onChange = vi.fn((next: Record<string, unknown>) => {
      value = next;
      rerender(<IntlProvider locale="zh-CN" messages={{}}><App><JobExecuteForm
        value={value}
        references={[{ label: '系统上下文 · workflow_id', value: '${system.workflow_id}', type: 'string', source: '系统上下文', sourceKind: 'system' }]}
        readOnly={false}
        onChange={onChange}
      /></App></IntlProvider>);
    });

    const { rerender } = render(<IntlProvider locale="zh-CN" messages={{}}><App><JobExecuteForm
      value={value}
      references={[{ label: '系统上下文 · workflow_id', value: '${system.workflow_id}', type: 'string', source: '系统上下文', sourceKind: 'system' }]}
      readOnly={false}
      onChange={onChange}
    /></App></IntlProvider>);

    const dataTransfer = {
      dropEffect: 'none',
      effectAllowed: 'copy',
      types: [WORKFLOW_REFERENCE_MIME],
      setData: vi.fn(),
      getData: vi.fn().mockImplementation((format: string) => format === WORKFLOW_REFERENCE_MIME ? '${system.workflow_id}' : ''),
    };
    const paramsItem = screen.getByText('执行参数').closest('.ant-form-item');
    const dropzone = paramsItem?.querySelector('[data-testid="workflow-reference-dropzone"]');
    expect(dropzone).not.toBeNull();
    fireEvent.dragOver(dropzone!, { dataTransfer });
    fireEvent.drop(dropzone!, { dataTransfer });
    expect(value.execution_params).toBe('a ${system.workflow_id}');
  });
});
