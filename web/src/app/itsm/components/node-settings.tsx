'use client';
import { Button, Checkbox, Input, Select, Space, Table, Tabs, Tag } from 'antd';
import { useEffect, useState } from 'react';
import { ItsmDrawer as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import type { CanvasNodeData } from '../constants/demo-flow';
import type { FormFieldSchema } from '../types';
import { NODE_ACTIONS } from '../constants/node-catalog';
import { useItsmApi } from '../api/useItsmApi';
import { UserSelector } from './user-selector';
import { FormRenderer } from './form-renderer';

export function flattenNodeFields(fields: FormFieldSchema[]): FormFieldSchema[] {
  return fields.flatMap(field => [field, ...flattenNodeFields(field.children || [])]);
}
export function NodeSettings({ data: source, fields, onChange: commit }: { data: CanvasNodeData; fields: FormFieldSchema[]; onChange: (patch: Partial<CanvasNodeData>) => void }) {
  const [draft, setDraft] = useState<CanvasNodeData>();
  const data = draft || source;
  const onChange = (patch: Partial<CanvasNodeData>) => setDraft({ ...data, ...patch });
  const api = useItsmApi();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('handler');
  const [keyword, setKeyword] = useState('');
  const [groups, setGroups] = useState<{id:number;name:string}[]>([]);
  const [groupError, setGroupError] = useState('');
  const flat = flattenNodeFields(fields);
  useEffect(() => {
    if (!open || !api.ready || data.assigneeSource !== 'handler_group') return;
    let active = true;
    void api.listHandlerGroups().then(result => { if (active) { setGroups((result as {items:{id:number;name:string}[]}).items || []); setGroupError(''); } }).catch(() => { if (active) setGroupError('处理组加载失败，请重新打开配置'); });
    return () => { active = false; };
  }, [open, api.ready, api.listHandlerGroups, data.assigneeSource]);
  const actionOptions = NODE_ACTIONS.filter(action => !['retry','manual_run','template','respond'].includes(action.value) && (data.nodeType === 'approval' ? action.value !== 'submit' : !['approve','reject'].includes(action.value)) && (data.nodeType !== 'submit' || action.value !== 'return'));
  const actions = data.actions ?? actionOptions.map(action => action.value);
  const inherited = new Map<string, string>();
  const inherit = (items: FormFieldSchema[], mode?: string) => items.forEach(field => {
    if (mode) inherited.set(field.key, mode);
    const own = mode || (['hidden','readonly','disabled'].includes(field.state || '') ? (field.state === 'hidden' ? 'hidden' : 'read') : data.fieldPerm?.[field.key]);
    inherit(field.children || [], ['read','readonly','hidden'].includes(own || '') ? own : undefined);
  });
  inherit(fields);
  const setPerm = (field: FormFieldSchema, mode: string) => onChange({fieldPerm:{...data.fieldPerm,...Object.fromEntries(flattenNodeFields([field]).map(child => [child.key,mode]))}});
  const tree = (items: FormFieldSchema[]): FormFieldSchema[] => items.flatMap(item => {
    const children = tree(item.children || []);
    return !keyword || `${item.label} ${item.key}`.toLowerCase().includes(keyword.toLowerCase()) || children.length ? [{...item,children:children.length ? children : undefined}] : [];
  });
  const previewForm = <FormRenderer key={JSON.stringify(data.fieldPerm)} schema={{version:1,fields}} fieldPerm={data.fieldPerm as Parameters<typeof FormRenderer>[0]['fieldPerm']} hideSubmit onSubmit={() => undefined} />;
  return <>
    <Button type="primary" onClick={() => { setDraft(source); setTab('handler'); setOpen(true); }}>配置节点</Button>
    <Button onClick={() => { setDraft(source); setTab('preview'); setOpen(true); }}>预览该节点</Button>
    <OperateModal title={`${data.label} · 节点配置`} open={open} formValue={data} onCancel={() => { setOpen(false); setDraft(undefined); }} width={1000} onOk={() => { commit(data); setOpen(false); setDraft(undefined); }} okText="应用到流程草稿">
      <Tabs activeKey={tab} onChange={setTab} items={[
        {key:"preview", label:"节点预览", children:<>{previewForm}<Space className="mt-4" wrap>{actions.map(action=><Button key={action}>{NODE_ACTIONS.find(item=>item.value===action)?.label || action}</Button>)}</Space></>},
        {key:'handler',label:'处理人',children:<div className="flex flex-col gap-4">
          <Select aria-label="处理人来源" value={data.assigneeSource || 'users'} options={[{value:'users',label:'指定人员'},{value:'handler_group',label:'指定处理组'},{value:'variable',label:'引用人员字段 / 提单人'}]} onChange={source => onChange({assigneeSource:source,assignees:[],assigneeValue:undefined})} />
          {(!data.assigneeSource || data.assigneeSource === 'users') && <UserSelector value={data.assignees} onChange={assignees => onChange({assignees})} />}
          {data.assigneeSource === 'handler_group' && <><Select aria-label="处理组" showSearch optionFilterProp="label" value={data.assigneeValue} options={groups.map(group=>({value:group.id,label:group.name}))} onChange={assigneeValue=>onChange({assigneeValue})} />{groupError && <span role="alert">{groupError}</span>}</>}
          {data.assigneeSource === 'variable' && <Select aria-label="引用人员字段" showSearch optionFilterProp="label" value={data.assigneeValue} options={[{value:'initiator',label:'提单人'},...flat.filter(field=>['user','singleUser','multiUser'].includes(field.type)).map(field=>({value:`form.${field.key}`,label:field.label}))]} onChange={assigneeValue=>onChange({assigneeValue})} />}
          <span className="text-xs text-[var(--color-text-3)]">引用人员字段需在提单时有值；后续流转按最新值解析。未找到处理人时按下方兜底策略执行。</span>
          <Select aria-label="无处理人时" value={data.original?.fallback || 'block'} options={[{value:'block',label:'阻止流转，修正处理人配置'},...(data.original?.fallback && data.original.fallback !== 'block' ? [{value:data.original.fallback,label:`当前兜底：${data.original.fallback}`}] : [])]} onChange={fallback=>onChange({original:{...data.original,id:data.original?.id || '',type:data.nodeType,name:data.label,fallback}})} />
          <Select aria-label="多人处理方式" value={data.multiMode || (data.orSign ? 'any' : 'single')} options={[{value:'single',label:'单人：首位处理人办理'},{value:'serial',label:'依次会签：所有人依次处理'},{value:'any',label:'或签：一人处理即可'},{value:'all',label:'会签：所有人均需处理'}]} onChange={mode=>onChange({orSign:mode==='any',multiMode:mode})} />
        </div>},
        {key:'actions',label:'操作按钮',children:<div className="flex flex-col gap-4">
          <div className="rounded border border-[var(--color-border)] p-3"><Space wrap>{actions.map(action=><Button key={action}>{NODE_ACTIONS.find(item=>item.value===action)?.label || action}</Button>)}</Space></div>
          <span className="text-xs text-[var(--color-text-3)]">配置允许的操作；实际可见按钮还会按当前节点状态、处理人和操作权限过滤。</span>
          <Checkbox.Group options={actionOptions} value={actions} onChange={value=>onChange({actions:value.map(String)})} />
          <span className="text-xs text-[var(--color-text-3)]">取消全部按钮后，该节点无法手动提交，请保留需要的处理操作。</span>
        </div>},
        {key:'fields',label:'字段配置',children:<div className="flex flex-col gap-3">
          <div className="flex justify-between gap-2"><Input aria-label="搜索节点字段" placeholder="搜索字段名称或标识" value={keyword} onChange={event=>setKeyword(event.target.value)} allowClear /><Select aria-label="批量设置字段" placeholder="全部字段设置为" options={[{value:'edit',label:'可编辑'},{value:'read',label:'只读'},{value:'hidden',label:'隐藏'}]} onChange={mode=>onChange({fieldPerm:Object.fromEntries(flat.map(field=>[field.key,mode]))})} /></div>
          <Table<FormFieldSchema> rowKey="key" size="small" pagination={false} dataSource={tree(fields)} scroll={{y:400}} columns={[
            {title:'字段名称',dataIndex:'label',render:(label,field)=><span>{label} <span className="text-xs text-[var(--color-text-3)]">{field.key}</span>{field.state && field.state !== 'default' && <Tag>{field.state}</Tag>}</span>},
            {title:'当前节点状态',render:(_,field)=><Select aria-label={`${field.label}状态`} value={inherited.get(field.key) || (data.fieldPerm?.[field.key]==='required'?'edit':data.fieldPerm?.[field.key] || 'edit')} disabled={inherited.has(field.key) || ['readonly','disabled','hidden'].includes(field.state || '')} options={[{value:'edit',label:'可编辑'},{value:'read',label:'只读'},{value:'hidden',label:'隐藏'}]} onChange={mode=>setPerm(field,mode)} />},
            {title:'必填',render:(_,field)=><Checkbox aria-label={`${field.label}必填`} checked={Boolean(field.required || data.fieldPerm?.[field.key]==='required')} disabled={Boolean(inherited.has(field.key) || field.required || field.children?.length || ['read','readonly','hidden'].includes(data.fieldPerm?.[field.key] || '') || ['readonly','disabled','hidden'].includes(field.state || ''))} onChange={event=>onChange({fieldPerm:{...data.fieldPerm,[field.key]:event.target.checked?'required':'edit'}})} />},
          ]} />
          <span className="text-xs text-[var(--color-text-3)]">分组设置会应用到子字段；隐藏保留已有数据，只读禁止修改。表单本身的隐藏、只读和必填约束继续生效。</span>
          <Button onClick={()=>setTab('preview')}>预览该节点</Button>
        </div>},
      ]} />
    </OperateModal>
  </>;
}
