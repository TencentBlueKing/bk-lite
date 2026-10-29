import './test-mocks';

import { App } from 'antd';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { JsonValueInput, type JsonValueInputHandle } from '../components/json-value-input';

describe('JSON 表单控件', () => {
  it('输入过程不触发外层表单更新，失焦后一次提交解析结果', () => {
    const onChange = vi.fn();
    render(<App><JsonValueInput ariaLabel="文档数据" expectedType="object" value={{}} onChange={onChange} /></App>);

    const input = screen.getByRole('textbox', { name: '文档数据' });
    fireEvent.change(input, { target: { value: '{"summary":{"total":2}}' } });
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith({ summary: { total: 2 } });
  });

  it('编辑与执行入口共用同一组 JSON 对象校验', async () => {
    const ref = createRef<JsonValueInputHandle>();
    const onChange = vi.fn();
    render(<App><JsonValueInput ref={ref} ariaLabel="文档数据" expectedType="object" required value={{}} onChange={onChange} /></App>);

    const input = screen.getByRole('textbox', { name: '文档数据' });
    fireEvent.change(input, { target: { value: '[1, 2]' } });

    let result: ReturnType<JsonValueInputHandle['validate']> | undefined;
    await act(async () => { result = ref.current?.validate(); });
    expect(result).toEqual({ valid: false });
    expect(await screen.findByText('请输入 JSON 对象')).not.toBeNull();
  });
});
