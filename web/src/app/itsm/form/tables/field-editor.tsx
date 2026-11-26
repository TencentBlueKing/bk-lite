'use client';
import { Button, Input, Select } from 'antd';
export interface TableField { key: string; label: string; type: string }
export const fieldTypes = [{value:'string',label:'文本'},{value:'number',label:'数字'},{value:'boolean',label:'布尔值'},{value:'date',label:'日期'},{value:'datetime',label:'日期时间'},{value:'object',label:'JSON 对象'},{value:'array',label:'JSON 数组'}];
export function FieldEditor({ fields, fixedKeys, onChange }: {fields: TableField[]; fixedKeys: string[]; onChange: (fields: TableField[]) => void}) {
  const update = (index: number, value: Partial<TableField>) => onChange(fields.map((f,i) => i===index ? {...f,...value} : f));
  return <div className="flex flex-col gap-3">
    <div className="grid grid-cols-[1fr_1fr_130px_60px] gap-2 text-xs text-[var(--color-text-3)]"><span>字段名称</span><span>字段标识</span><span>类型</span><span /></div>
    {fields.map((f,i) => <div key={i} className="grid grid-cols-[1fr_1fr_130px_60px] gap-2">
      <Input aria-label={`字段${i+1}名称`} value={f.label} onChange={e=>update(i,{label:e.target.value})} placeholder="例如：设备名称" />
      <Input aria-label={`字段${i+1}标识`} disabled={fixedKeys.includes(f.key)} value={f.key} onChange={e=>update(i,{key:e.target.value})} placeholder="例如：name" />
      <Select aria-label={`字段${i+1}类型`} value={f.type} options={fieldTypes} onChange={type=>update(i,{type})} />
      <Button danger type="text" disabled={fixedKeys.includes(f.key)} onClick={()=>onChange(fields.filter((_,n)=>n!==i))}>移除</Button>
    </div>)}
    <Button onClick={()=>onChange([...fields,{key:'',label:'',type:'string'}])}>新增字段</Button>
    <span className="text-xs text-[var(--color-text-3)]">标识用于表单取数，保存后保持不变。可修改显示名称；修改类型时已有数据也须符合新类型。</span>
  </div>;
}
