import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { jobBadge, upstreamJobOutputs } from './job-node-config';
import { JobNodeSettings } from './job-node-settings';

const listJobOptions = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, listJobOptions }) }));
afterEach(cleanup);
const fields = [
  { key: 'business', type: 'input', label: '所属业务' },
  { key: 'vms', type: 'table', label: '虚拟机', children: [{ key: 'hostname', label: '主机名', type: 'input' }] },
  { key: 'disks', type: 'table', label: '磁盘', children: [{ key: 'capacity', label: '容量', type: 'number' }] },
];
function Editor({ initial = { kind: 'job_template' } }: { initial?: Record<string, unknown> }) {
  const [config, setConfig] = useState<Record<string, unknown>>(initial);
  return <><JobNodeSettings config={config} fields={fields} outputs={[{ value: 'inventory', label: '查询清单 · inventory' }]} onChange={setConfig} /><output>{JSON.stringify(config)}</output></>;
}
async function choose(label: string, option: string) {
  fireEvent.mouseDown(await screen.findByRole('combobox', { name: label }));
  fireEvent.click(await screen.findByText(option, { selector: '.ant-select-item-option-content' }));
}
it('映射到所选子表单同行，切换表后清除旧参数', async () => {
  listJobOptions.mockResolvedValue({ scripts: [{ id: 5, name: '只读检查', params: [{ name: 'vm_name' }] }], targets: [{ id: 9, name: '检查主机' }] });
  render(<Editor />);
  await choose('已有作业', '只读检查');
  await choose('执行目标', '检查主机');
  await choose('执行方式', '逐项执行');
  await choose('执行集合', '虚拟机');
  await choose('vm_name 参数来源', '当前项');
  await choose('参数 vm_name', '主机名');
  expect(JSON.parse(screen.getByRole('status').textContent!)).toEqual({ kind: 'job_template', script_id: 5, target_id: 9, mode: 'each', collection: 'form.vms', params: { vm_name: { source: 'item', key: 'hostname' } } });
  await choose('执行集合', '磁盘');
  expect(JSON.parse(screen.getByRole('status').textContent!).params).toEqual({});
  await choose('vm_name 参数来源', '当前项');
  await choose('参数 vm_name', '容量');
  expect(JSON.parse(screen.getByRole('status').textContent!).params).toEqual({ vm_name: { source: 'item', key: 'capacity' } });
}, 15000);
it('读取作业目录失败时说明原因', async () => {
  listJobOptions.mockRejectedValue(new Error('当前组织无权访问作业目录'));
  render(<Editor />);
  expect(await screen.findByText(/当前组织无权访问作业目录/)).toBeTruthy();
});

it('读取旧草稿并切到单次执行，仅清理逐项配置', async () => {
  listJobOptions.mockResolvedValue({ scripts: [{ id: 5, name: '只读检查', params: [{ name: 'vm_name' }] }], targets: [] });
  render(<Editor initial={{ kind: 'job_template', script_id: 5, table_key: 'vms', params: { vm_name: 'hostname' }, batch_size: 2 }} />);
  expect(await screen.findByText('主机名')).toBeTruthy();
  await choose('执行方式', '单次执行');
  expect(JSON.parse(screen.getByRole('status').textContent!)).toEqual({ kind: 'job_template', script_id: 5, mode: 'once', params: {} });
  await choose('vm_name 参数来源', '系统变量');
  await choose('参数 vm_name', '工单号');
  expect(JSON.parse(screen.getByRole('status').textContent!).params.vm_name).toEqual({ source: 'system', key: 'sn' });
});
it('上游输出可作为执行集合，当前项支持自定义属性及批次大小', async () => {
  listJobOptions.mockResolvedValue({ scripts: [{ id: 5, name: '只读检查', params: [{ name: 'vm_name' }] }], targets: [] });
  render(<Editor initial={{ kind: 'job_template', script_id: 5, mode: 'each' }} />);
  await choose('执行集合', '查询清单 · inventory');
  await choose('vm_name 参数来源', '当前项');
  fireEvent.change(screen.getByLabelText('参数 vm_name'), { target: { value: 'name' } });
  await choose('调度方式', '分批执行');
  fireEvent.change(screen.getByRole('spinbutton', { name: '每批项数' }), { target: { value: '3' } });
  expect(JSON.parse(screen.getByRole('status').textContent!)).toMatchObject({ collection: 'output.inventory', batch_size: 3, params: { vm_name: { source: 'item', key: 'name' } } });
});

it('单次作业参数可以引用表单、上游输出或固定值', async () => {
  listJobOptions.mockResolvedValue({ scripts: [{ id: 5, name: '只读检查', params: [{ name: 'value' }] }], targets: [] });
  render(<Editor initial={{ kind: 'job_template', script_id: 5 }} />);
  await choose('value 参数来源', '表单字段');
  await choose('参数 value', '所属业务');
  expect(JSON.parse(screen.getByRole('status').textContent!).params.value).toEqual({ source: 'form', key: 'business' });
  await choose('value 参数来源', '上游输出');
  await choose('参数 value', '查询清单 · inventory');
  expect(JSON.parse(screen.getByRole('status').textContent!).params.value).toEqual({ source: 'output', key: 'inventory' });
  await choose('value 参数来源', '固定值');
  fireEvent.change(screen.getByLabelText('参数 value'), { target: { value: 'readonly' } });
  expect(JSON.parse(screen.getByRole('status').textContent!).params.value).toEqual({ source: 'literal', key: 'readonly' });
});

it('设计画布区分单次、逐项及分批执行，并兼容旧逐行配置', () => {
  expect(jobBadge({ mode: 'once' })).toContain('单次');
  expect(jobBadge({ table_key: 'vms' })).toContain('逐项');
  expect(jobBadge({ mode: 'each', batch_size: 2 })).toContain('每批 2 项');
  expect(jobBadge({ mode: 'each', dispatch_mode: 'parallel' })).toContain('并发');
});

it('仅提供有向上游集成结果，排除当前、下游及孤立节点', () => {
  const nodes = ['src', 'middle', 'job', 'after', 'isolated'].map(id => ({
    id, data: { label: id, auto: { kind: id === 'middle' ? 'job_template' : 'integration', result_field: id } },
  }));
  const edges = [{ source: 'src', target: 'middle' }, { source: 'middle', target: 'job' }, { source: 'job', target: 'after' }];
  expect(upstreamJobOutputs('job', nodes, edges)).toEqual([{ value: 'src', label: 'src · src' }]);
});
