import React from 'react';
import { ConfigProvider } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ImportDialog } from './import-dialog';
afterEach(cleanup);
it('选择文件不会立即导入，失败保留文件，重试成功才关闭',async()=>{
  const onImport=vi.fn().mockRejectedValueOnce(Error('文件格式不正确')).mockResolvedValueOnce(true);
  render(<ConfigProvider theme={{token:{motion:false}}}><ImportDialog accept=".json" onImport={onImport}/></ConfigProvider>);
  fireEvent.click(screen.getByRole('button',{name:'导入'}));
  const dialog=screen.getByRole('dialog');
  const input=dialog.querySelector('input[type=file]')!;
  fireEvent.change(input,{target:{files:[new File(['[]'],'test.json',{type:'application/json'})]}});
  await within(dialog).findByText('test.json');
  expect(onImport).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole('button',{name:/导\s*入/}));
  await screen.findByText('文件格式不正确');
  expect(within(dialog).getByText('test.json')).toBeTruthy();
  await waitFor(()=>expect((within(dialog).getByRole('button',{name:/导\s*入/}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(within(dialog).getByRole('button',{name:/导\s*入/}));
  await waitFor(()=>expect(onImport).toHaveBeenCalledTimes(2));
  await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
});
it('取消导入不调用写接口',async()=>{
  const onImport=vi.fn();render(<ConfigProvider theme={{token:{motion:false}}}><ImportDialog accept=".json" onImport={onImport}/></ConfigProvider>);
  fireEvent.click(screen.getByRole('button',{name:'导入'}));
  fireEvent.click(screen.getByRole('button',{name:/取\s*消/}));
  await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());expect(onImport).not.toHaveBeenCalled();
});
