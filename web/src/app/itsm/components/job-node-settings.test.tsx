import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { JobNodeSettings } from './job-node-settings';

const listJobOptions = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, listJobOptions }) }));
afterEach(cleanup);
const fields = [
  { key: 'vms', type: 'table', label: '虚拟机', children: [{ key: 'hostname', label: '主机名', type: 'input' }] },
  { key: 'disks', type: 'table', label: '磁盘', children: [{ key: 'capacity', label: '容量', type: 'number' }] },
];
function Editor() {
  const [config, setConfig] = useState<Record<string, unknown>>({ kind: 'job_template' });
  return <><JobNodeSettings config={config} fields={fields} onChange={setConfig} /><output>{JSON.stringify(config)}</output></>;
}
async function choose(label: string, option: string) {
  fireEvent.mouseDown(screen.getByRole('combobox', { name: label }));
  fireEvent.click(await screen.findByText(option, { selector: '.ant-select-item-option-content' }));
}
it('映射到所选子表单同行，切换表后清除旧参数', async () => {
  listJobOptions.mockResolvedValue({ scripts: [{ id: 5, name: '只读检查', params: [{ name: 'vm_name' }] }], targets: [{ id: 9, name: '检查主机' }] });
  render(<Editor />);
  await choose('已有作业', '只读检查');
  await choose('执行目标', '检查主机');
  await choose('逐行执行的子表单', '虚拟机');
  await choose('参数 vm_name', '主机名');
  expect(JSON.parse(screen.getByRole('status').textContent!)).toEqual({ kind: 'job_template', script_id: 5, target_id: 9, table_key: 'vms', params: { vm_name: 'hostname' } });
  await choose('逐行执行的子表单', '磁盘');
  expect(JSON.parse(screen.getByRole('status').textContent!).params).toEqual({});
  await choose('参数 vm_name', '容量');
  expect(JSON.parse(screen.getByRole('status').textContent!).params).toEqual({ vm_name: 'capacity' });
});
it('读取作业目录失败时说明原因', async () => {
  listJobOptions.mockRejectedValue(new Error('当前组织无权访问作业目录'));
  render(<Editor />);
  expect(await screen.findByText(/当前组织无权访问作业目录/)).toBeTruthy();
});
