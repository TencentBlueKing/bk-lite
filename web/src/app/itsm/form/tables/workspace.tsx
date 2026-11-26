'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ImportDialog } from '../../components/import-dialog';
import { useRouter } from 'next/navigation';
import { ItsmDrawer, usePageLeave } from '../../components/interaction-surfaces';
import { ItsmBackButton } from '@/app/itsm/components/back-button';

import { ItsmRowActions, ItsmListToolbar, ItsmCreateButton } from '@/app/itsm/components/list-controls';
import { Alert, Button, Input, InputNumber, Select, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { FieldRow } from '../../components/field-row';
import { useTranslation } from '@/utils/i18n';
import { FieldEditor, type TableField } from './field-editor';
interface TableItem { id:number; name:string; key:string; fields?:TableField[] }
interface RowItem { id:number; data:Record<string,unknown> }
interface TableDraft { id?:number; name:string; key:string; fields:TableField[]; fixedKeys:string[] }

export default function DataTablesWorkspace({ tableId }: { tableId?: number }) {
  const router = useRouter();
  const [baseline,setBaseline]=useState('');

  const {t}=useTranslation();
  const api=useItsmApi();
  const [items,setItems]=useState<TableItem[]>([]);
  const [keyword,setKeyword]=useState('');
  useEffect(()=>{setKeyword(sessionStorage.getItem('itsm:tables:search') || '');},[]);
  const search=(value:string)=>{setKeyword(value);sessionStorage.setItem('itsm:tables:search',value);};
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
  const leave=usePageLeave(!!(draft && baseline !== JSON.stringify(draft)) || !!(rowDraft && baseline !== JSON.stringify(rowDraft)));
  const [formError,setFormError]=useState('');
  const [rowPage, setRowPage] = useState({ current: 1, pageSize: 20, total: 0 });
  const rowsRequest=useRef(0);
  useEffect(()=>()=>{rowsRequest.current++;},[]);
  const notify=(error:unknown)=>message.error(error instanceof Error?error.message:'操作失败');
  const load=useCallback(async()=>{
    const data=await api.listDataTables() as {items:TableItem[];can_add:boolean;can_edit:boolean};
    setItems(data.items||[]);setPermissions({can_add:!!data.can_add,can_edit:!!data.can_edit});
  },[api.listDataTables]);
  useEffect(()=>{if(api.ready && !tableId) void load().catch(notify);},[api.ready,load,tableId]);

  const openRows=async(item:TableItem, page = rowPage.current, pageSize = rowPage.pageSize)=>{
    const seq=++rowsRequest.current;setActive(item);setRows([]);setFields([]);setRowsError('');setCanEditRows(false);setRowsLoading(true);
    try{
      const data=await api.listDataRows(item.id, page, pageSize) as {page:number;total:number;items:RowItem[];fields?:TableField[];can_edit:boolean};
      if(seq!==rowsRequest.current)return;
      setRowPage({current:data.page, pageSize, total:data.total});
      setRows(data.items||[]);setFields(data.fields||[]);setCanEditRows(data.can_edit===true);
    }catch(error){if(seq===rowsRequest.current)setRowsError(error instanceof Error?error.message:'加载数据失败，请重试');}
    finally{if(seq===rowsRequest.current)setRowsLoading(false);}
  };
  useEffect(()=>{
    if (!api.ready || !tableId) return;
    let live=true;
    void api.getDataTable(tableId).then(value=>{if(live)void openRows(value as TableItem, 1, 20);}).catch(error=>{if(live)setRowsError(error instanceof Error?error.message:'加载失败');});
    return ()=>{live=false;rowsRequest.current++;};
  },[api.ready,tableId,api.getDataTable]);
  const editFields=async(item:TableItem)=>{
    try{const data=await api.getDataTable(item.id) as TableItem;setFormError('');setBaseline(JSON.stringify({...data,fields:data.fields||[],fixedKeys:(data.fields||[]).map(f=>f.key)}));setDraft({...data,fields:data.fields||[],fixedKeys:(data.fields||[]).map(f=>f.key)});}catch(error){notify(error);}
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
      const created=await api.importDataTable(content,file.name) as TableItem;await load();router.push(`/itsm/form/tables/${created.id}`);message.success(`已导入：${created.name}`);return true;
    }catch(error){notify(error);return false;}finally{setBusy(false);}
  };
  const beginRow=(row?:RowItem)=>{
    const data={...(row?.data||{})};for(const f of fields)if(['object','array'].includes(f.type)&&data[f.key]!=null)data[f.key]=JSON.stringify(data[f.key],null,2);
    setFormError('');setBaseline(JSON.stringify({id:row?.id,data}));setRowDraft({id:row?.id,data});
  };
  const visibleFields=fields.length?fields:Array.from(new Set(rows.flatMap(r=>Object.keys(r.data)))).map(key=>({key,label:key,type:'string'}));
  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    {!tableId && <><ItsmListToolbar search={{value: keyword, onChange: search, label: '搜索数据表', placeholder: '搜索名称或标识'}} actions={<>
{permissions.can_add&&<><ImportDialog accept=".xlsx" onImport={upload} /><ItsmCreateButton onClick={()=>{setFormError('');setBaseline(JSON.stringify({name:'',key:'',fields:[{key:'name',label:'名称',type:'string'}],fixedKeys:[]}));setDraft({name:'',key:'',fields:[{key:'name',label:'名称',type:'string'}],fixedKeys:[]});}}>新建</ItsmCreateButton></>}
</>} />
    <CustomTable storageKey="itsm:tables:position" queryKey={keyword} rowKey="id" dataSource={items.filter(i=>`${i.name} ${i.key}`.toLowerCase().includes(keyword.trim().toLowerCase()))} columns={[
      {title:'名称',dataIndex:'name',key:'name',render:(value:string,item:TableItem)=><ItsmListEntry href={`/itsm/form/tables/${item.id}`}>{value}</ItsmListEntry>},{title:'标识',dataIndex:'key',key:'key'},
      { fixed: 'right' as const, width: 120,title:'操作',key:'actions',render:(_:unknown,item:TableItem)=><ItsmRowActions items={[{key: 'action-0', label: t('itsm.admin.data'), kind: 'data' as const, onClick: ()=>router.push(`/itsm/form/tables/${item.id}`)},
        ...(permissions.can_edit ? [{key: 'action-1', label: "字段配置", kind: 'configure' as const, onClick: ()=>void editFields(item)}] : []),
        {key: 'action-2', label: "导出", kind: 'export' as const, onClick: ()=>void download(item.id), more: true}]} />},
    ]}/>
    </>}
    {tableId && <section aria-label="数据表数据">
      <div className="mb-4 flex items-center gap-3"><ItsmBackButton label="返回数据表列表" onClick={()=>leave(()=>router.push('/itsm/form/tables'))} /><span className="text-base font-semibold">{active?.name || '数据表'} · 数据</span><span className="text-xs text-[var(--color-text-3)]">{active?.key}</span></div>
      {rowsError?<Alert type="error" message={rowsError} action={<Button onClick={()=>{if(active)void openRows(active);else if(tableId)void api.getDataTable(tableId).then(value=>openRows(value as TableItem)).catch(notify);}}>重试</Button>}/>:<>
        {canEditRows&&<ItsmListToolbar actions={<ItsmCreateButton onClick={()=>beginRow()}>新增数据</ItsmCreateButton>} />}
        <CustomTable serverPagination={{ ...rowPage, onChange: (page, size) => { if (active) void openRows(active, size === rowPage.pageSize ? page : 1, size); } }} rowKey="id" loading={rowsLoading} dataSource={rows} scroll={{x:'max-content',y:'40vh'}} columns={[
          ...visibleFields.map(f=>({title:f.label||f.key,key:f.key,render:(_:unknown,row:RowItem)=>row.data[f.key]==null?'':typeof row.data[f.key]==='boolean'?(row.data[f.key]?'是':'否'):typeof row.data[f.key]==='object'?JSON.stringify(row.data[f.key]):String(row.data[f.key])})),
          ...(canEditRows?[{ fixed: 'right' as const, width: 120,title:'操作',key:'actions',render:(_:unknown,row:RowItem)=><ItsmRowActions items={[{key: 'action-3', label: "编辑", kind: 'edit' as const, onClick: ()=>beginRow(row)},
            {key: 'action-4', label: t('itsm.common.delete'), kind: 'delete' as const, danger: true, confirm: {title: '确定删除这条数据？'}, onClick: ()=>{const seq=rowsRequest.current;void api.deleteDataRows(active!.id,[row.id]).then(()=>{if(seq===rowsRequest.current)active && void openRows(active);}).catch(notify);}}]} />}]:[]),
        ]}/>
      </>}
    </section>}
    {draft&&<ItsmDrawer formValue={draft} title={draft.id?'字段配置':'新建数据表'} open width={850} onCancel={()=>setDraft(undefined)} onOk={()=>void saveTable()} confirmLoading={busy} destroyOnHidden>
      <div className="flex flex-col gap-4"><FieldRow label="名称"><Input aria-label="数据表名称" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></FieldRow><FieldRow label="标识"><Input aria-label="数据表标识" disabled={!!draft.id} value={draft.key} onChange={e=>setDraft({...draft,key:e.target.value})}/></FieldRow>
      <FieldEditor fields={draft.fields} fixedKeys={draft.fixedKeys} onChange={newFields=>setDraft({...draft,fields:newFields})}/>{formError&&<Alert type="error" message={formError}/>}</div>
    </ItsmDrawer>}
    {rowDraft&&<ItsmDrawer formValue={rowDraft} title={rowDraft.id?'编辑数据':'新增数据'} open width={650} onCancel={()=>setRowDraft(undefined)} onOk={()=>void saveRow()} confirmLoading={busy} destroyOnHidden><div className="flex flex-col gap-3">
      {fields.map(f=>{const value=rowDraft.data[f.key];const change=(next:unknown)=>setRowDraft({...rowDraft,data:{...rowDraft.data,[f.key]:next}});return <FieldRow key={f.key} label={f.label||f.key}>
        {f.type==='number'?<InputNumber aria-label={f.label||f.key} value={value as number} onChange={change} className="!w-full"/>:f.type==='boolean'?<Select aria-label={f.label||f.key} className="w-full" allowClear value={value==null?undefined:String(value)} options={[{value:'true',label:'是'},{value:'false',label:'否'}]} onChange={v=>change(v==null?null:v==='true')}/>:['object','array'].includes(f.type)?<Input.TextArea aria-label={f.label||f.key} value={String(value??'')} rows={4} placeholder={f.type==='object'?'例如 {"name":"示例"}':'例如 ["示例"]'} onChange={e=>change(e.target.value)}/>:<Input aria-label={f.label||f.key} type={f.type==='date'?'date':f.type==='datetime'?'datetime-local':'text'} value={String(value??'')} onChange={e=>change(e.target.value||null)}/>}
      </FieldRow>;})}{formError&&<Alert type="error" message={formError}/>}</div></ItsmDrawer>}
  </div>;
}
