import React from 'react';
import { fireEvent, render, screen, cleanup, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Modal } from 'antd';
import { ItsmModal, ItsmDrawer } from './interaction-surfaces';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('未修改直接关闭，修改后确认放弃才关闭，保存期间禁止关闭',()=>{
  const cancel=vi.fn(); const confirm=vi.spyOn(Modal,'confirm').mockReturnValue({destroy:vi.fn(),update:vi.fn()});
  const {rerender}=render(<ItsmModal title="编辑" open formValue={{name:'原值'}} onCancel={cancel}><input aria-label="名称" /></ItsmModal>);
  fireEvent.click(screen.getByRole('button',{name:'Close'}));expect(cancel).toHaveBeenCalledTimes(1);
  rerender(<ItsmModal title="编辑" open formValue={{name:'修改'}} onCancel={cancel} />);
  fireEvent.click(screen.getByRole('button',{name:'Close'}));expect(confirm).toHaveBeenCalledTimes(1);expect(cancel).toHaveBeenCalledTimes(1);
  confirm.mock.calls[0][0].onOk?.();expect(cancel).toHaveBeenCalledTimes(2);
  rerender(<ItsmModal title="编辑" open formValue={{name:'修改'}} confirmLoading onCancel={cancel} />);
  expect(screen.queryByRole('button',{name:'Close'})).toBeNull();
});
it('抽屉沿用公共容器，保存和取消行为明确',async()=>{
  const save=vi.fn();const cancel=vi.fn();
  render(<ItsmDrawer title="字段配置" open onOk={save} onCancel={cancel}>配置内容</ItsmDrawer>);
  expect(screen.getByRole('dialog')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:/保\s*存/}));expect(save).toHaveBeenCalledTimes(1);
  await waitFor(()=>expect((screen.getByRole('button',{name:/取\s*消/}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:/取\s*消/}));expect(cancel).toHaveBeenCalledTimes(1);
});
