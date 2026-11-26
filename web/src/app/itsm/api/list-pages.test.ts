import { expect, it, vi } from 'vitest';
import { readListPages } from './list-pages';
it('读取后续页且保留权限元数据，避免管理列表只显示前二十项', async () => {
  const read = vi.fn().mockResolvedValueOnce({items:[{id:1},{id:2}],count:3,can_add:false,can_edit:true}).mockResolvedValueOnce({items:[{id:3}],count:3});
  const result = await readListPages(read);
  expect(read.mock.calls).toEqual([[1],[2]]);
  expect(result).toEqual({items:[{id:1},{id:2},{id:3}],count:3,can_add:false,can_edit:true});
});
it('空列表停止读取，不丢失权限标志', async () => {
  const read=vi.fn().mockResolvedValue({items:[],count:0,can_add:false});
  expect(await readListPages(read)).toEqual({items:[],count:0,can_add:false});
  expect(read).toHaveBeenCalledTimes(1);
});
