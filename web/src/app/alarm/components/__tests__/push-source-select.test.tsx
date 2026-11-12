import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

const select = () => screen.getByRole('combobox', { name: 'alarmCommon.pushSourceSelect' });

it('打开下拉才请求目录，页面上只有一个输入框', async () => {
  render(<PushSourceSelect value={[]} onChange={vi.fn()} />);
  expect(api.getPushSourceIdOptions).not.toHaveBeenCalled();
  expect(screen.getAllByRole('combobox', { name: 'alarmCommon.pushSourceSelect' })).toHaveLength(1);
  expect(screen.queryByRole('combobox', { name: 'alarmCommon.pushSourceInput' })).toBeNull();
  fireEvent.mouseDown(select());
  await waitFor(() => expect(api.getPushSourceIdOptions).toHaveBeenCalledOnce());
});

it('勾选清单项 prod 写入同一数组', async () => {
  const onChange = vi.fn();
  render(<PushSourceSelect value={[]} onChange={onChange} />);
  fireEvent.mouseDown(select());
  fireEvent.click(await screen.findByText('prod', { selector: '.ant-select-item-option-content' }));
  expect(onChange).toHaveBeenLastCalledWith(['prod']);
});

it('同一个框回车添加目录外的值', async () => {
  const onChange = vi.fn();
  render(<PushSourceSelect value={['prod']} onChange={onChange} />);
  expect(api.getPushSourceIdOptions).not.toHaveBeenCalled();
  fireEvent.change(select(), { target: { value: 'k8s-new' } });
  fireEvent.keyDown(select(), { key: 'Enter', keyCode: 13 });
  expect(onChange).toHaveBeenLastCalledWith(['prod', 'k8s-new']);
  await waitFor(() => expect(api.getPushSourceIdOptions).toHaveBeenCalled());
  await act(async () => { await Promise.resolve(); });
});

it('回车输入清单中的值不产生重复', async () => {
  const onChange = vi.fn();
  render(<PushSourceSelect value={['k8s-new']} onChange={onChange} />);
  fireEvent.mouseDown(select());
  await screen.findByText('prod', { selector: '.ant-select-item-option-content' });
  fireEvent.change(select(), { target: { value: 'prod' } });
  fireEvent.keyDown(select(), { key: 'Enter', keyCode: 13 });
  expect(onChange).toHaveBeenLastCalledWith(['k8s-new', 'prod']);
});

it('目录没有的已存值仍在同一个框回显', async () => {
  api.getPushSourceIdOptions.mockResolvedValue([]);
  render(<PushSourceSelect value={['gone']} onChange={vi.fn()} />);
  expect(select().closest('.ant-select')?.querySelector('.ant-select-selection-item-content')?.textContent).toBe('gone');
  fireEvent.mouseDown(select());
  await waitFor(() => expect(api.getPushSourceIdOptions).toHaveBeenCalledOnce());
  expect(select().closest('.ant-select')?.querySelector('.ant-select-selection-item-content')?.textContent).toBe('gone');
});

it('目录失败可重试，同一个框仍能输入', async () => {
  api.getPushSourceIdOptions.mockRejectedValueOnce(new Error('network'));
  const onChange = vi.fn();
  render(<PushSourceSelect value={[]} onChange={onChange} />);
  fireEvent.mouseDown(select());
  expect(await screen.findByText('alarmCommon.pushSourceOptionsRetry')).toBeTruthy();
  fireEvent.change(select(), { target: { value: 'k8s-new' } });
  fireEvent.keyDown(select(), { key: 'Enter', keyCode: 13 });
  expect(onChange).toHaveBeenLastCalledWith(['k8s-new']);
  fireEvent.click(screen.getByText('alarmCommon.pushSourceOptionsRetry'));
  await screen.findByText('prod', { selector: '.ant-select-item-option-content' });
  expect(api.getPushSourceIdOptions).toHaveBeenCalledTimes(2);
});
