import './test-mocks';

import { App } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { DocumentRenderForm } from '../components/document-render-form';

vi.mock('@/utils/request', () => ({ default: () => ({ post: vi.fn() }) }));

describe('文档生成节点配置', () => {
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

  it('在文档节点上传模板，文档数据支持整个上游输出或手写 JSON', async () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App><DocumentRenderForm
      schema={{
        type: 'object',
        properties: {
          template: { type: 'object', title: 'Word / Excel 模板' },
          data: { type: 'object', title: '文档数据' },
        },
        required: ['template', 'data'],
      }}
      value={{ data: {} }}
      references={[
        { label: '触发输入 · file (object)', value: '${workflow.input.file}', type: 'object', source: '触发输入', sourceKind: 'trigger', widget: 'file-upload' },
        { label: 'job_execute · 全部输出 (object)', value: '${job_execute.output}', type: 'object', source: 'job_execute', sourceKind: 'node_output' },
      ]}
      nodeTitle="文档生成"
      readOnly={false}
      onChange={vi.fn()}
      onNodeTitleChange={vi.fn()}
    /></App></IntlProvider>);

    expect(screen.getByText('报告模板')).not.toBeNull();
    expect(screen.getByText('Word')).not.toBeNull();
    expect(screen.getByText('Excel')).not.toBeNull();
    expect(screen.queryByText('触发输入 · file (object)')).toBeNull();
    const jsonEditor = document.querySelector('textarea.font-mono');
    expect(jsonEditor).not.toBeNull();
    expect(jsonEditor?.hasAttribute('disabled')).toBe(false);
    const dataItem = screen.getByText('文档数据').closest('.ant-form-item');
    const templateItem = screen.getByText('报告模板').closest('.ant-form-item');
    expect(dataItem?.querySelector('.ant-form-item-extra')).toBeNull();
    expect(templateItem?.querySelector('.ant-form-item-extra')).toBeNull();
    expect(dataItem?.querySelector('[aria-label="question-circle"]')).not.toBeNull();
    expect(templateItem?.querySelector('[aria-label="question-circle"]')).not.toBeNull();
    await userEvent.hover(dataItem!.querySelector('[aria-label="question-circle"]')!);
    expect((await screen.findByRole('tooltip')).textContent).toContain('拖入上游作业输出');
    expect(screen.queryByText(/上游作业需按输出契约返回/)).toBeNull();
    expect(screen.getByRole('button', { name: '模板语法说明' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '数据结构说明' })).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '模板语法说明' }));
    expect(await screen.findByText('怎么工作')).not.toBeNull();
    fireEvent.click(document.querySelector('.ant-drawer-close')!);

    fireEvent.click(screen.getByRole('button', { name: '数据结构说明' }));
    expect(await screen.findByText('平台固定外层')).not.toBeNull();
    expect(screen.getByText('数据如何进模板')).not.toBeNull();
  });

  it('已上传模板时回显文件名，并可移除后重新上传', () => {
    const onChange = vi.fn();
    render(<IntlProvider locale="zh-CN" messages={{}}><App><DocumentRenderForm
      schema={{
        type: 'object',
        properties: {
          template: { type: 'object', title: 'Word / Excel 模板' },
          data: { type: 'object', title: '文档数据' },
        },
        required: ['template', 'data'],
      }}
      value={{
        template: {
          kind: 'uploaded',
          name: 'windows-health.docx',
          format: 'docx',
          size: 38811,
          placeholders: ['d.summary.total'],
          token: 'token',
        },
        data: '${scan.output}',
      }}
      references={[]}
      nodeTitle="文档生成"
      readOnly={false}
      onChange={onChange}
      onNodeTitleChange={vi.fn()}
    /></App></IntlProvider>);

    expect(screen.getByText('windows-health.docx')).not.toBeNull();
    expect(screen.getByText(/DOCX/)).not.toBeNull();
    expect(screen.getByText(/识别到的占位符/)).not.toBeNull();
    expect(screen.queryByText('更换模板')).toBeNull();
    expect(screen.queryByText('上传 Word / Excel 模板')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '移除报告模板' }));
    expect(onChange).toHaveBeenCalledWith({ data: '${scan.output}' });
  });

  it('已发布固化模板也回显，移除时清空 snapshot', () => {
    const onChange = vi.fn();
    render(<IntlProvider locale="zh-CN" messages={{}}><App><DocumentRenderForm
      schema={{ type: 'object', properties: { template: { type: 'object' }, data: { type: 'object' } }, required: ['template', 'data'] }}
      value={{
        template_snapshot: {
          object_key: 'workflow-orchestration/templates/frozen/health.docx',
          format: 'docx',
          size: 38811,
          filename_prefix: 'health-inspection',
          sha256: 'a'.repeat(64),
        },
        data: {},
      }}
      references={[]}
      nodeTitle="文档生成"
      readOnly={false}
      onChange={onChange}
      onNodeTitleChange={vi.fn()}
    /></App></IntlProvider>);

    expect(screen.getByText('health-inspection.docx')).not.toBeNull();
    expect(screen.getByText(/已发布固化/)).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '移除报告模板' }));
    expect(onChange).toHaveBeenCalledWith({ data: {} });
  });
});
