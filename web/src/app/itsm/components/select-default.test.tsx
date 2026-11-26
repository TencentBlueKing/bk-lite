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
const remote: FormFieldSchema = {key:'network', label:'网络', type:'select', props:{defaultFirstOption:true},
  fetch:{source:'integration', mode:'options', integration_id:1}};

it('单选可默认选择数字零，编辑已有值时保留原选择，未启用时留空', async () => {
  const submit = vi.fn();
  render(<FormRenderer schema={{version:1, fields:[fixed, {...fixed, key:'old'}, {...fixed,key:'blank',props:{}}]}}
    initialValues={{old:20}} onSubmit={submit}/>);
  fireEvent.click(screen.getByRole('button',{name:/提\s*交/}));
  await waitFor(()=>expect(submit).toHaveBeenCalledWith({size:0,old:20,blank:undefined}));
});

it('表格及独立单选按首次目录结果初始化，无需打开下拉框', async () => {
  fetchField.mockResolvedValue({options:[{value:'net-a',label:'开发网络'}],fills:{},receipt:'proof'});
  const submit = vi.fn();
  render(<FormRenderer schema={{version:1,fields:[remote,{key:'machines',label:'明细',type:'table',children:[fixed,remote]}]}}
    fetchContext={{service_id:18}} initialValues={{machines:[{}, {size:20,network:'net-b'}]}} onSubmit={submit}/>);
  await waitFor(()=>expect(screen.getAllByText('开发网络')).toHaveLength(2));
  fireEvent.click(screen.getByRole('button',{name:/提\s*交/}));
  await waitFor(()=>expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    network:'net-a', machines:[{size:0,network:'net-a',_field_receipts:{network:['proof']}},{size:20,network:'net-b',_field_receipts:{network:['proof']}}]
  })));
  expect(fetchField).toHaveBeenCalledTimes(3);
});

it('子表单的值、选项与回执按同行依赖独立，迟到的旧请求不会回写', async () => {
  const pending = new Map<string, (result: unknown) => void>();
  fetchField.mockImplementation(({field, values}) => new Promise(resolve => pending.set([field, values.vms[0].zone].join('/'), resolve)));
  const submit = vi.fn();
  const source: FormFieldSchema = { key: 'zone', type: 'input', label: '区域' };
  const generated: FormFieldSchema = { key: 'size', type: 'input', label: '规格', fetch: { mode:'value', source:'integration', integration_id:1, enforce:true, inputs:{region:'${form.zone}'}, dependencies:['old'] }};
  const os: FormFieldSchema = { ...remote, fetch:{...remote.fetch!, inputs:{params:[{zone:'${form.zone}'}]}} };
  render(<FormRenderer schema={{version:1,fields:[{key:'vms',type:'table',label:'机器',children:[source,generated,os]}]}}
    initialValues={{vms:[{zone:'a'},{zone:'b'}]}} fetchContext={{service_id:1}} onSubmit={submit}/>);
  await waitFor(()=>expect(pending.size).toBe(4));
  fireEvent.change(screen.getByLabelText('区域 1'),{target:{value:'c'}});
  await waitFor(()=>expect(pending.size).toBe(6));
  for (const zone of ['c','b','a']) {
    pending.get('vms.size/'+zone)!({value:zone,options:[],receipt:'size-'+zone,fills:{}});
    pending.get('vms.network/'+zone)!({options:[{label:'网络'+zone,value:'shared'}],receipt:'net-'+zone,fills:{}});
  }
  await screen.findByText('网络c');
  await screen.findByText('网络b');
  expect(screen.queryByText('网络a')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:/提\s*交/}));
  await waitFor(()=>expect(submit).toHaveBeenCalledWith(expect.objectContaining({vms:['c','b'].map(zone=>expect.objectContaining({
    zone, size:zone, network:'shared', _field_receipts:{size:['size-'+zone],network:['net-'+zone]},
  }))})));
});
