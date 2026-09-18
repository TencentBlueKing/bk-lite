import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import PushSourceSelect from '../../(pages)/settings/components/pushSourceSelect';

const api = vi.hoisted(() => ({ getPushSourceIdOptions: vi.fn() }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => api }));
afterEach(cleanup);
beforeAll(() => { window.matchMedia = vi.fn().mockReturnValue({matches:false, addListener:vi.fn(),removeListener:vi.fn()}); });
beforeEach(() => {
  api.getPushSourceIdOptions.mockReset().mockResolvedValue(['prod', 'staging']);
});

it('打开通道 1 才请求目录', async () => {
  render(<PushSourceSelect value={[]} onChange={vi.fn()} />);
  expect(api.getPushSourceIdOptions).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'alarmCommon.pushSourceSelect'}));
  await waitFor(() => expect(api.getPushSourceIdOptions).toHaveBeenCalledOnce());
});

it('勾选清单项 prod 写入同一数组', async () => {
  const onChange = vi.fn();
  render(<PushSourceSelect value={[]} onChange={onChange} />);
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'alarmCommon.pushSourceSelect'}));
  fireEvent.click(await screen.findByText('prod', {selector:'.ant-select-item-option-content'}));
  expect(onChange).toHaveBeenLastCalledWith(['prod']);
});

it('通道 2 回车 k8s-new 合并进数组', () => {
  const onChange = vi.fn();
  render(<PushSourceSelect value={['prod']} onChange={onChange} />);
  expect(api.getPushSourceIdOptions).not.toHaveBeenCalled();
  const input = screen.getByRole('combobox', {name:'alarmCommon.pushSourceInput'});
  fireEvent.change(input, {target:{value:'k8s-new'}});
  fireEvent.keyDown(input, {key:'Enter', keyCode:13});
  expect(onChange).toHaveBeenLastCalledWith(['prod', 'k8s-new']);
});

it('手输清单成员不产生重复，归到通道 1', async () => {
  const onChange = vi.fn();
  render(<PushSourceSelect value={['k8s-new']} onChange={onChange} />);
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'alarmCommon.pushSourceSelect'}));
  await screen.findByText('prod', {selector:'.ant-select-item-option-content'});
  fireEvent.keyDown(screen.getByRole('combobox', {name:'alarmCommon.pushSourceSelect'}), {key:'Escape', keyCode:27});
  const input = screen.getByRole('combobox', {name:'alarmCommon.pushSourceInput'});
  fireEvent.change(input, {target:{value:'prod'}});
  fireEvent.keyDown(input, {key:'Enter', keyCode:13});
  expect(onChange).toHaveBeenLastCalledWith(['prod', 'k8s-new']);
});

it('清单没有的已存值走通道 2 回显', async () => {
  api.getPushSourceIdOptions.mockResolvedValue([]);
  render(<PushSourceSelect value={['gone']} onChange={vi.fn()} />);
  const channel2 = screen.getByRole('combobox', {name:'alarmCommon.pushSourceInput'});
  expect(channel2.closest('.ant-select')?.querySelector('.ant-select-selection-item-content')?.textContent).toBe('gone');
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'alarmCommon.pushSourceSelect'}));
  await waitFor(() => expect(api.getPushSourceIdOptions).toHaveBeenCalledOnce());
  expect(channel2.closest('.ant-select')?.querySelector('.ant-select-selection-item-content')?.textContent).toBe('gone');
});

it('目录失败可重试，通道 2 仍能输入', async () => {
  api.getPushSourceIdOptions.mockRejectedValueOnce(new Error('network'));
  const onChange = vi.fn();
  render(<PushSourceSelect value={[]} onChange={onChange} />);
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'alarmCommon.pushSourceSelect'}));
  expect(await screen.findByText('alarmCommon.pushSourceOptionsRetry')).toBeTruthy();
  const input = screen.getByRole('combobox', {name:'alarmCommon.pushSourceInput'});
  fireEvent.change(input, {target:{value:'k8s-new'}});
  fireEvent.keyDown(input, {key:'Enter', keyCode:13});
  expect(onChange).toHaveBeenLastCalledWith(['k8s-new']);
  fireEvent.click(screen.getByText('alarmCommon.pushSourceOptionsRetry'));
  await screen.findByText('prod', {selector:'.ant-select-item-option-content'});
  expect(api.getPushSourceIdOptions).toHaveBeenCalledTimes(2);
});
