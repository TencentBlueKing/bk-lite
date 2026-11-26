import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { FormFieldSchema } from '../types';
import { FormRenderer } from './form-renderer';

vi.mock('@/app/opspilot/components/ai-editor', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
const fetchField = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, fetchField }) }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener() {}, removeListener() {} }) });

const fixed: FormFieldSchema = { key: 'size', label: '容量', type: 'select', props: { defaultFirstOption: true },
  source: {type:'static', options:[{value:0,label:'无数据盘'},{value:20,label:'20 GiB'}]} };
it('单选可默认选择数字零，编辑已有值时保留原选择，未启用时留空', async () => {
  const submit = vi.fn();
  render(<FormRenderer schema={{version:1, fields:[fixed, {...fixed, key:'old'}, {...fixed,key:'blank',props:{}}]}}
    initialValues={{old:20}} onSubmit={submit}/>);
  fireEvent.click(screen.getByRole('button',{name:/提\s*交/}));
  await waitFor(()=>expect(submit).toHaveBeenCalledWith({size:0,old:20,blank:undefined}));
});
