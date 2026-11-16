'use client';
import { Alert, Button, Input, InputNumber, Select, Upload, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';
import { FieldEditor, type TableField } from './field-editor';
interface TableItem { id:number; name:string; key:string; fields?:TableField[] }
interface RowItem { id:number; data:Record<string,unknown> }
interface TableDraft { id?:number; name:string; key:string; fields:TableField[]; fixedKeys:string[] }

export default function DataTablesPage() {
  const {t}=useTranslation();
  const api=useItsmApi();
  const [items,setItems]=useState<TableItem[]>([]);
  const [keyword,setKeyword]=useState('');
  const [permissions,setPermissions]=useState({can_add:false,can_edit:false});
  const [active,setActive]=useState<TableItem|null>(null);
  const [rows,setRows]=useState<RowItem[]>([]);
  const [fields,setFields]=useState<TableField[]>([]);
  const [canEditRows,setCanEditRows]=useState(false);
  const [rowsLoading,setRowsLoading]=useState(false);
  const [rowsError,setRowsError]=useState('');
  const [draft,setDraft]=useState<TableDraft>();
  const [rowDraft,setRowDraft]=useState<{id?:number;data:Record<string,unknown>}>();
  const [busy,setBusy]=useState(false);
  const [formError,setFormError]=useState('');
  const rowsRequest=useRef(0);
  useEffect(()=>()=>{rowsRequest.current++;},[]);
  const notify=(error:unknown)=>message.error(error instanceof Error?error.message:'操作失败');
  const load=useCallback(async()=>{
    const data=await api.listDataTables() as {items:TableItem[];can_add:boolean;can_edit:boolean};
    setItems(data.items||[]);setPermissions({can_add:!!data.can_add,can_edit:!!data.can_edit});
  },[api.listDataTables]);
  useEffect(()=>{if(api.ready) void load().catch(notify);},[api.ready,load]);
  const closeRows=()=>{rowsRequest.current++;setActive(null);setRows([]);setRowDraft(undefined);setRowsLoading(false);setRowsError('');};
  const openRows=async(item:TableItem)=>{
    const seq=++rowsRequest.current;setActive(item);setRows([]);setFields([]);setRowsError('');setCanEditRows(false);setRowsLoading(true);
    try{
      const data=await api.listDataRows(item.id) as {items:RowItem[];fields?:TableField[];can_edit:boolean};
      if(seq!==rowsRequest.current)return;
      setRows(data.items||[]);setFields(data.fields||[]);setCanEditRows(data.can_edit===true);
    }catch(error){if(seq===rowsRequest.current)setRowsError(error instanceof Error?error.message:'加载数据失败，请重试');}
    finally{if(seq===rowsRequest.current)setRowsLoading(false);}
  };
  const editFields=async(item:TableItem)=>{
    try{const data=await api.getDataTable(item.id) as TableItem;setFormError('');setDraft({...data,fields:data.fields||[],fixedKeys:(data.fields||[]).map(f=>f.key)});}catch(error){notify(error);}
  };
  const saveTable=async()=>{
    if(!draft)return;setBusy(true);setFormError('');
    try{
      const payload={name:draft.name.trim(),key:draft.key.trim(),fields:draft.fields};
      if(!payload.name||!payload.key)throw Error('请填写名称和标识');
      const keys=new Set<string>();
      for(const f of draft.fields){if(!f.label.trim()||!(/^[A-Za-z][A-Za-z0-9_]{0,63}$/).test(f.key)||keys.has(f.key))throw Error('请填写字段名称和有效且不重复的标识');keys.add(f.key);}
      if(!draft.fields.length)throw Error('至少配置一个字段');
      if(draft.id)await api.saveDataTable(draft.id,payload);else await api.createDataTable(payload);
      setDraft(undefined);await load();message.success('已保存数据表');
    }catch(error){setFormError(error instanceof Error?error.message:'保存失败');}finally{setBusy(false);}
  };
  const saveRow=async()=>{
    if(!active||!rowDraft)return;setBusy(true);setFormError('');
    try{
      const data={...rowDraft.data};
      for(const f of fields){if(['object','array'].includes(f.type)&&typeof data[f.key]==='string')data[f.key]=data[f.key]===''?null:JSON.parse(data[f.key] as string);}
      await api.saveDataRow(active.id,data,rowDraft.id);setRowDraft(undefined);await openRows(active);message.success('已保存数据');
    }catch(error){setFormError(error instanceof Error?error.message:'请检查数据格式');}finally{setBusy(false);}
  };
  const download=async(id:number)=>{
    try{const data=await api.exportDataTable(id) as {filename:string;content_base64:string};const bytes=Uint8Array.from(atob(data.content_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes]));const link=document.createElement('a');link.href=url;link.download=data.filename;link.click();URL.revokeObjectURL(url);}catch(error){notify(error);}
  };
  const upload=async(file:File)=>{
    setBusy(true);
    try{
      if(!file.name.toLowerCase().endsWith('.xlsx')||file.size>20*1024*1024)throw Error('请选择20MB以内的 xlsx 文件');
      const content=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||'').split(',')[1]||'');reader.onerror=()=>reject(reader.error);reader.readAsDataURL(file);});
      const created=await api.importDataTable(content,file.name) as TableItem;await load();await openRows(created);message.success(`已导入：${created.name}`);
    }catch(error){notify(error);}finally{setBusy(false);}
  };
  const beginRow=(row?:RowItem)=>{
    const data={...(row?.data||{})};for(const f of fields)if(['object','array'].includes(f.type)&&data[f.key]!=null)data[f.key]=JSON.stringify(data[f.key],null,2);
    setFormError('');setRowDraft({id:row?.id,data});
  };
  const visibleFields=fields.length?fields:Array.from(new Set(rows.flatMap(r=>Object.keys(r.data)))).map(key=>({key,label:key,type:'string'}));
  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex gap-2">
      {permissions.can_add&&<><Button type="primary" onClick={()=>{setFormError('');setDraft({name:'',key:'',fields:[{key:'name',label:'名称',type:'string'}],fixedKeys:[]});}}>新建数据表</Button><Upload accept=".xlsx" showUploadList={false} beforeUpload={file=>{void upload(file);return false;}}><Button loading={busy}>导入</Button></Upload></>}
    </div><Input aria-label="搜索数据表" className="!w-64" placeholder="搜索名称或标识" value={keyword} onChange={e=>setKeyword(e.target.value)} allowClear/></div>
    <CustomTable rowKey="id" dataSource={items.filter(i=>`${i.name} ${i.key}`.toLowerCase().includes(keyword.trim().toLowerCase()))} columns={[
      {title:'名称',dataIndex:'name',key:'name'},{title:'标识',dataIndex:'key',key:'key'},
      {title:'操作',key:'actions',render:(_:unknown,item:TableItem)=><span className="inline-flex gap-2"><Button type="link" onClick={()=>void openRows(item)}>{t('itsm.admin.data')}</Button>{permissions.can_edit&&<Button type="link" onClick={()=>void editFields(item)}>字段配置</Button>}<Button type="link" onClick={()=>void download(item.id)}>导出</Button></span>},
    ]}/>
    {active&&<OperateModal title={`${active.name} · 数据`} subTitle={active.key} open width={1100} footer={null} onCancel={closeRows} destroyOnHidden>
      {rowsError?<Alert type="error" message={rowsError} action={<Button onClick={()=>void openRows(active)}>重试</Button>}/>:<>
        {canEditRows&&<Button type="primary" className="mb-3" onClick={()=>beginRow()}>新增数据</Button>}
        <CustomTable rowKey="id" loading={rowsLoading} dataSource={rows} scroll={{x:'max-content',y:'40vh'}} columns={[
          ...visibleFields.map(f=>({title:f.label||f.key,key:f.key,render:(_:unknown,row:RowItem)=>row.data[f.key]==null?'':typeof row.data[f.key]==='boolean'?(row.data[f.key]?'是':'否'):typeof row.data[f.key]==='object'?JSON.stringify(row.data[f.key]):String(row.data[f.key])})),
          ...(canEditRows?[{title:'操作',key:'actions',render:(_:unknown,row:RowItem)=><span className="inline-flex gap-2"><Button type="link" onClick={()=>beginRow(row)}>编辑</Button><Button type="link" danger onClick={()=>{const seq=rowsRequest.current;void api.deleteDataRows(active.id,[row.id]).then(()=>{if(seq===rowsRequest.current)void openRows(active);}).catch(notify);}}>{t('itsm.common.delete')}</Button></span>}]:[]),
        ]}/>
      </>}
    </OperateModal>}
    {draft&&<OperateModal title={draft.id?'字段配置':'新建数据表'} open width={850} onCancel={()=>setDraft(undefined)} onOk={()=>void saveTable()} confirmLoading={busy} destroyOnHidden>
      <div className="flex flex-col gap-4"><FieldRow label="名称"><Input aria-label="数据表名称" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></FieldRow><FieldRow label="标识"><Input aria-label="数据表标识" disabled={!!draft.id} value={draft.key} onChange={e=>setDraft({...draft,key:e.target.value})}/></FieldRow>
      <FieldEditor fields={draft.fields} fixedKeys={draft.fixedKeys} onChange={newFields=>setDraft({...draft,fields:newFields})}/>{formError&&<Alert type="error" message={formError}/>}</div>
    </OperateModal>}
    {rowDraft&&<OperateModal title={rowDraft.id?'编辑数据':'新增数据'} open width={650} onCancel={()=>setRowDraft(undefined)} onOk={()=>void saveRow()} confirmLoading={busy} destroyOnHidden><div className="flex flex-col gap-3">
      {fields.map(f=>{const value=rowDraft.data[f.key];const change=(next:unknown)=>setRowDraft({...rowDraft,data:{...rowDraft.data,[f.key]:next}});return <FieldRow key={f.key} label={f.label||f.key}>
        {f.type==='number'?<InputNumber aria-label={f.label||f.key} value={value as number} onChange={change} className="!w-full"/>:f.type==='boolean'?<Select aria-label={f.label||f.key} className="w-full" allowClear value={value==null?undefined:String(value)} options={[{value:'true',label:'是'},{value:'false',label:'否'}]} onChange={v=>change(v==null?null:v==='true')}/>:['object','array'].includes(f.type)?<Input.TextArea aria-label={f.label||f.key} value={String(value??'')} rows={4} placeholder={f.type==='object'?'例如 {"name":"示例"}':'例如 ["示例"]'} onChange={e=>change(e.target.value)}/>:<Input aria-label={f.label||f.key} type={f.type==='date'?'date':f.type==='datetime'?'datetime-local':'text'} value={String(value??'')} onChange={e=>change(e.target.value||null)}/>}
      </FieldRow>;})}{formError&&<Alert type="error" message={formError}/>}</div></OperateModal>}
  </div>;
}
