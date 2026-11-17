import React from 'react';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {ConditionBuilder} from './condition-builder';
afterEach(cleanup);
it('单条已有条件可回显并编辑，不丢失字段和运算符',()=>{
  const change=vi.fn();render(<ConditionBuilder fields={['amount']} value={{field:'amount',op:'>=',value:1000}} onChange={change}/>);
  expect((screen.getByPlaceholderText('比较值') as HTMLInputElement).value).toBe('1000');
  fireEvent.change(screen.getByPlaceholderText('比较值'),{target:{value:'2000'}});
  expect(change).toHaveBeenCalledWith({logic:'and',items:[{field:'amount',op:'>=',value:'2000'}]});
});
it('数值字段编辑条件后仍保存数值，避免后端比较失败',()=>{
  const change=vi.fn();render(<ConditionBuilder fields={['amount']} fieldTypes={{amount:'number'}} value={{field:'amount',op:'>=',value:1000}} onChange={change}/>);
  fireEvent.change(screen.getByPlaceholderText('比较值'),{target:{value:'1200'}});
  expect(change).toHaveBeenLastCalledWith({logic:'and',items:[{field:'amount',op:'>=',value:1200}]});
});
