import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { useState } from 'react';
import { beforeAll, vi } from 'vitest';

import { FormSchemaEditor } from '../components/form-schema-editor';
import { createFormFieldSchema } from '../lib/form-field-registry';
import type { JsonSchema } from '../lib/types';

describe('触发表单字段编辑器', () => {
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

  it('为目标和文件展示各自的业务化配置', () => {
    const target = createFormFieldSchema('target-selector', '目标主机');
    const file = createFormFieldSchema('file-upload', '报告模板');

    render(<IntlProvider locale="zh-CN" messages={{}}><App><FormSchemaEditor readOnly={false} value={{
      type: 'object',
      properties: { targets: target, report_template: file },
      required: ['targets', 'report_template'],
    }} onChange={vi.fn()} /></App></IntlProvider>);

    expect(screen.getByText('主机来源')).not.toBeNull();
    expect(screen.getByText('节点管理')).not.toBeNull();
    expect(screen.getByText('作业平台')).not.toBeNull();
    expect(screen.getByText('最多选择')).not.toBeNull();
    expect(screen.queryByText('最少选择')).toBeNull();
    expect(screen.getByText('允许文件类型')).not.toBeNull();
    expect(screen.queryByText('文件来源')).toBeNull();
  });

  it('目标字段最少选择由必填推导', () => {
    const onChange = vi.fn();
    const target = createFormFieldSchema('target-selector', '目标主机');

    render(<IntlProvider locale="zh-CN" messages={{}}><App><FormSchemaEditor readOnly={false} value={{
      type: 'object',
      properties: { targets: target },
      required: ['targets'],
    }} onChange={onChange} /></App></IntlProvider>);

    fireEvent.click(screen.getByRole('switch', { name: /字段 1 必填/ }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      required: [],
      properties: expect.objectContaining({
        targets: expect.objectContaining({
          minItems: 0,
          'x-target-binding': expect.objectContaining({ minCount: 0 }),
        }),
      }),
    }));
  });

  it('Webhook 使用请求输入语义创建字段', () => {
    const onChange = vi.fn();
    render(<IntlProvider locale="zh-CN" messages={{}}><App><FormSchemaEditor context="webhook" readOnly={false} value={{
      type: 'object', properties: {}, required: [], additionalProperties: false,
    }} onChange={onChange} /></App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: /添加请求输入字段/ }));

    expect(screen.queryByText('添加表单字段')).toBeNull();
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      properties: expect.objectContaining({ field: expect.objectContaining({ title: '新请求字段' }) }),
    }));
  });

  it('NATS 使用事件语义创建字段', () => {
    const onChange = vi.fn();
    render(<IntlProvider locale="zh-CN" messages={{}}><App><FormSchemaEditor context="nats" readOnly={false} value={{
      type: 'object', properties: {}, required: [], additionalProperties: false,
    }} onChange={onChange} /></App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: /添加事件字段/ }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      properties: expect.objectContaining({ field: expect.objectContaining({ title: '新事件字段' }) }),
    }));
  });

  it('连续输入字段标识时不丢失焦点和后续字符', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [schema, setSchema] = useState<JsonSchema>({
        type: 'object',
        properties: { field: createFormFieldSchema('input', '新字段') },
        required: [],
        additionalProperties: false,
      });
      return <>
        <FormSchemaEditor readOnly={false} value={schema} onChange={setSchema} />
        <output data-testid="committed-field-key">{Object.keys(schema.properties)[0]}</output>
      </>;
    }

    render(<IntlProvider locale="zh-CN" messages={{}}><App><Harness /></App></IntlProvider>);
    const fieldKey = screen.getByPlaceholderText('field_key');
    const fieldKeyItem = fieldKey.closest('.ant-form-item');

    expect(fieldKeyItem?.classList.contains('ant-form-item-vertical')).toBe(true);
    expect(fieldKeyItem?.querySelector('.ant-form-item-extra')).toBeNull();
    const fieldKeyHelp = screen.getByRole('img', { name: 'question-circle' });
    await user.hover(fieldKeyHelp);
    expect((await screen.findByRole('tooltip')).textContent).toContain('小写字母开头，可包含数字和下划线');
    await user.unhover(fieldKeyHelp);

    await user.type(fieldKey, '_name');

    const updatedFieldKey = screen.getByPlaceholderText<HTMLInputElement>('field_key');
    expect(updatedFieldKey.value).toBe('field_name');
    expect(document.activeElement).toBe(updatedFieldKey);
    expect(screen.getByTestId('committed-field-key').textContent).toBe('field');

    await user.tab();
    await waitFor(() => expect(screen.getByTestId('committed-field-key').textContent).toBe('field_name'));

    const committedFieldKey = screen.getByPlaceholderText<HTMLInputElement>('field_key');
    await user.clear(committedFieldKey);
    await user.type(committedFieldKey, 'Invalid-Key');
    await user.tab();

    expect(committedFieldKey.value).toBe('Invalid-Key');
    await waitFor(() => expect(committedFieldKey.getAttribute('aria-invalid')).toBe('true'));
    expect(screen.getByTestId('committed-field-key').textContent).toBe('field_name');
  });

  it('字段标识重复时在表单项下提示，不弹 toast', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [schema, setSchema] = useState<JsonSchema>({
        type: 'object',
        properties: {
          host: createFormFieldSchema('input', '主机'),
          port: createFormFieldSchema('number', '端口'),
        },
        required: [],
        additionalProperties: false,
      });
      return <FormSchemaEditor readOnly={false} value={schema} onChange={setSchema} />;
    }

    render(<IntlProvider locale="zh-CN" messages={{}}><App><Harness /></App></IntlProvider>);
    const fieldKeys = screen.getAllByPlaceholderText('field_key');
    await user.clear(fieldKeys[1]);
    await user.type(fieldKeys[1], 'host');
    await user.tab();

    await waitFor(() => expect(fieldKeys[1].getAttribute('aria-invalid')).toBe('true'));
    expect(screen.getByText('字段标识已存在')).not.toBeNull();
    expect(document.querySelector('.ant-message')).toBeNull();
  });
});
