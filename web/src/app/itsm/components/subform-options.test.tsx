import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import type { FormChoice } from '../types';
import { SubformOptions } from './subform-options';

it('编辑级联子项时保留父项和其他分支的值类型', () => {
  function Editor() {
    const [options, setOptions] = useState<FormChoice[]>([{ label: '区域', value: 1 }, { label: '其他', value: '2' }]);
    return <><SubformOptions tree options={options} onChange={setOptions} /><output>{JSON.stringify(options)}</output></>;
  }
  render(<Editor />);
  fireEvent.click(screen.getByRole('button', { name: '添加子选项 区域' }));
  fireEvent.change(screen.getAllByLabelText('选项名称')[1], { target: { value: '北京' } });
  const choices = JSON.parse(screen.getByRole('status').textContent || '[]');
  expect(choices).toEqual([{ label: '区域', value: 1, children: [{ label: '北京', value: '3' }] }, { label: '其他', value: '2' }]);
});
