'use client';
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, Radio, Select, Space, Table, Tabs, Tag, Tooltip } from 'antd';
import { useEffect, useId, useState } from 'react';
import { ItsmDrawer as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import type { CanvasNodeData } from '../constants/demo-flow';
import type { FormFieldSchema, NodeActionDisplay } from '../types';
import { NODE_ACTIONS, displayActionLabel, nodeActionLabel, orderedNodeActions, ticketActionLabel } from '../constants/node-catalog';
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
  const [groupLoading, setGroupLoading] = useState(false);
  const transferTargetsId = useId();
  const flat = flattenNodeFields(fields);
  const actionOptions = NODE_ACTIONS.filter(action => !['retry','manual_run','template','respond'].includes(action.value) && (data.nodeType === 'approval' ? action.value !== 'submit' : !['approve','reject'].includes(action.value)) && (data.nodeType !== 'submit' || action.value !== 'return'));
  const actions = data.actions ?? actionOptions.map(action => action.value);
  const opinionOptions = actionOptions.filter(option => actions.includes(option.value));
  const requiredOpinionActions = opinionOptions.filter(option => data.requiredOpinionActions?.includes(option.value)).map(option => option.value);
  const displayActions = orderedNodeActions(actions, data.actionDisplay);
  const editableActions = displayActions.filter(row => opinionOptions.some(option => option.value === row.action));
  const previewLabel = data.actionDisplay?.length ? ticketActionLabel : nodeActionLabel;
  const requiredOpinionLabels = displayActions.filter(row => requiredOpinionActions.includes(row.action))
    .map(row => displayActionLabel(row, previewLabel));
  const renderActionPreview = () => <div role="group" aria-label="节点操作预览"><Space wrap>
    {displayActions.map(row => <Button key={row.action}>{displayActionLabel(row, previewLabel)}</Button>)}
  </Space></div>;
  const updateActionDisplay = (actionDisplay: NodeActionDisplay[]) => onChange({ actionDisplay });
  const moveAction = (index: number, offset: number) => {
    const reordered = [...editableActions];
    const [row] = reordered.splice(index, 1);
    reordered.splice(index + offset, 0, row);
    updateActionDisplay(reordered);
  };
  const applySettings = () => {
    commit({ ...data, ...(data.actionDisplay && { actionDisplay: data.actionDisplay.map(({ action, label }) => {
      const name = label?.trim();
      return name ? { action, label: name } : { action };
    }) }) });
    setOpen(false);
    setDraft(undefined);
  };
  const transferEnabled = actions.includes('transfer');
  const transferScope = data.transferScope;
  const transferUsers = transferScope?.type === 'users' && Array.isArray(transferScope.users) &&
    transferScope.users.every(user => typeof user === 'string' && user.trim()) ? transferScope.users : [];
  const transferGroupIds = transferScope?.type === 'handler_groups' && Array.isArray(transferScope.group_ids) &&
    transferScope.group_ids.every(id => Number.isSafeInteger(id) && id > 0) ? transferScope.group_ids : [];
  let transferScopeError = '';
  if (transferScope?.type === 'users' && !transferUsers.length) {
    transferScopeError = '请至少选择一名可接收转交的人员';
  } else if (transferScope?.type === 'handler_groups' && !transferGroupIds.length) {
    transferScopeError = '请至少选择一个可接收转交的处理组';
  } else if (transferScope != null && !['users', 'handler_groups'].includes(transferScope.type)) {
    transferScopeError = '已保存的转交范围无效，请重新选择';
  }
  const needsGroups = open && (
    (tab === 'handler' && data.assigneeSource === 'handler_group') ||
    (tab === 'actions' && transferEnabled && transferScope?.type === 'handler_groups')
  );
  useEffect(() => {
    if (!needsGroups || !api.ready) return;
    let active = true;
    setGroupLoading(true);
    setGroupError('');
    void api.listWorkflowHandlerGroupOptions().then(result => {
      if (active) setGroups(result.items);
    }).catch(() => {
      if (active) {
        setGroups([]);
        setGroupError('处理组加载失败，请重新打开配置');
      }
    }).finally(() => {
      if (active) setGroupLoading(false);
    });
    return () => { active = false; };
  }, [needsGroups, api.ready, api.listWorkflowHandlerGroupOptions]);
  const groupOptions = groups.map(group => ({ value: group.id, label: group.name }));
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
  const previewSchema = { version: 1, fields };
  const previewForm = <FormRenderer key={JSON.stringify(data.fieldPerm)} schema={previewSchema} fetchContext={{ preview: true, schema: previewSchema }} fieldPerm={data.fieldPerm as Parameters<typeof FormRenderer>[0]['fieldPerm']} hideSubmit onSubmit={() => undefined} />;
  return <>
    <Button type="primary" onClick={() => { setDraft(source); setTab('handler'); setOpen(true); }}>配置节点</Button>
    <Button onClick={() => { setDraft(source); setTab('preview'); setOpen(true); }}>预览该节点</Button>
    <OperateModal title={`${data.label} · 节点配置`} open={open} formValue={data} onCancel={() => { setOpen(false); setDraft(undefined); }} width={1000} onOk={applySettings} okText="应用到流程草稿" okButtonProps={{ disabled: transferEnabled && Boolean(transferScopeError) }}>
      <Tabs activeKey={tab} onChange={setTab} items={[
        {key:"preview", label:"节点预览", children:<>
          {previewForm}
          <div className="mt-4">{renderActionPreview()}</div>
          {requiredOpinionLabels.length > 0 && <p className="mt-2 text-xs text-[var(--color-text-3)]">
            {requiredOpinionLabels.join('、')}前需填写处理意见。
          </p>}
        </>},
        {key:'handler',label:'处理人',children:<div className="flex flex-col gap-4">
          <Select aria-label="处理人来源" value={data.assigneeSource || 'users'} options={[{value:'users',label:'指定人员'},{value:'handler_group',label:'指定处理组'},{value:'service_group',label:'使用服务处理组'},{value:'variable',label:'引用人员字段 / 提单人'}]} onChange={source => onChange({assigneeSource:source,assignees:[],assigneeValue:undefined})} />
          {(!data.assigneeSource || data.assigneeSource === 'users') && <UserSelector value={data.assignees} onChange={assignees => onChange({assignees})} />}
          {data.assigneeSource === 'handler_group' && <><Select aria-label="处理组" showSearch loading={groupLoading} optionFilterProp="label" value={data.assigneeValue} options={groupOptions} onChange={assigneeValue=>onChange({assigneeValue})} />{groupError && <span role="alert">{groupError}</span>}</>}
          {data.assigneeSource === 'variable' && <Select aria-label="引用人员字段" showSearch optionFilterProp="label" value={data.assigneeValue} options={[{value:'initiator',label:'提单人'},...flat.filter(field=>['user','singleUser','multiUser'].includes(field.type)).map(field=>({value:`form.${field.key}`,label:field.label}))]} onChange={assigneeValue=>onChange({assigneeValue})} />}
          <span className="text-xs text-[var(--color-text-3)]">{data.assigneeSource === 'service_group' ? '办理人来自提单服务在服务管理中绑定的处理组。' : '引用人员字段需在提单时有值；后续流转按最新值解析。未找到处理人时按下方兜底策略执行。'}</span>
          {data.assigneeSource !== 'service_group' && <Select aria-label="无处理人时" value={data.original?.fallback || 'block'} options={[{value:'block',label:'阻止流转，修正处理人配置'},...(data.original?.fallback && data.original.fallback !== 'block' ? [{value:data.original.fallback,label:`当前兜底：${data.original.fallback}`}] : [])]} onChange={fallback=>onChange({original:{...data.original,id:data.original?.id || '',type:data.nodeType,name:data.label,fallback}})} />}
          <Select aria-label="多人处理方式" value={data.multiMode || (data.orSign ? 'any' : 'single')} options={[{value:'single',label:'单人：首位处理人办理'},{value:'serial',label:'依次会签：所有人依次处理'},{value:'any',label:'或签：一人处理即可'},{value:'all',label:'会签：所有人均需处理'}]} onChange={mode=>onChange({orSign:mode==='any',multiMode:mode})} />
        </div>},
        {key:'actions',label:'操作按钮',children:<div className="flex flex-col gap-4">
          <div className="rounded border border-[var(--color-border)] p-3">{renderActionPreview()}</div>
          <span className="text-xs text-[var(--color-text-3)]">配置允许的操作；实际可见按钮还会按当前节点状态、处理人和操作权限过滤。</span>
          <Checkbox.Group options={actionOptions} value={actions} onChange={value => {
            const enabled = value.map(String);
            onChange({
              actions: enabled,
              actionDisplay: data.actionDisplay?.length ? orderedNodeActions(enabled, data.actionDisplay) : data.actionDisplay,
              requiredOpinionActions: data.requiredOpinionActions === undefined ? undefined : requiredOpinionActions.filter(action => enabled.includes(action)),
            });
          }} />
          {editableActions.length > 0 && <fieldset>
            <legend className="mb-2 text-sm font-medium">按钮名称与顺序</legend>
            <p className="mb-2 text-xs text-[var(--color-text-3)]">留空使用默认名称。上移或下移可调整展示顺序。</p>
            <ol className="divide-y divide-[var(--color-border)] rounded border border-[var(--color-border)]">
              {editableActions.map((row, index) => {
                const original = nodeActionLabel(row.action);
                const inputId = `${transferTargetsId}-action-${row.action}`;
                return <li key={row.action} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-3 py-2 sm:grid-cols-[minmax(8rem,1fr)_minmax(0,2fr)_auto]">
                  <label htmlFor={inputId} className="col-span-2 text-sm sm:col-span-1">{original}</label>
                  <Input id={inputId} aria-label={`${original}按钮名称`} value={row.label ?? ''} placeholder={ticketActionLabel(row.action)} maxLength={24}
                    onChange={event => updateActionDisplay(editableActions.map(item => item.action === row.action ? { ...item, label: event.target.value } : item))} />
                  <Space>
                    <Tooltip title={`上移${original}`}>
                      <Button aria-label={`上移${original}`} icon={<ArrowUpOutlined aria-hidden="true" />} disabled={index === 0} onClick={() => moveAction(index, -1)} />
                    </Tooltip>
                    <Tooltip title={`下移${original}`}>
                      <Button aria-label={`下移${original}`} icon={<ArrowDownOutlined aria-hidden="true" />} disabled={index === editableActions.length - 1} onClick={() => moveAction(index, 1)} />
                    </Tooltip>
                  </Space>
                </li>;
              })}
            </ol>
          </fieldset>}
          {opinionOptions.length > 0 && <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium">处理意见必填</legend>
            <Checkbox.Group value={requiredOpinionActions} onChange={value => onChange({ requiredOpinionActions: value.map(String) })}>
              {opinionOptions.map(option => <Checkbox key={option.value} value={option.value} aria-label={`${option.label}处理意见必填`}>
                {option.label}
              </Checkbox>)}
            </Checkbox.Group>
            <span className="text-xs text-[var(--color-text-3)]">勾选后，办理人执行该操作前需填写处理意见。</span>
          </fieldset>}
          {transferEnabled && <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium">转交范围</legend>
            <Radio.Group
              value={transferScope == null ? 'all' : transferScope.type}
              options={[
                { value: 'all', label: '本组织不限' },
                { value: 'users', label: '指定人员' },
                { value: 'handler_groups', label: '指定处理组' },
              ]}
              onChange={event => {
                const mode = event.target.value;
                if (mode === 'users') {
                  onChange({ transferScope: { type: 'users', users: [] } });
                } else if (mode === 'handler_groups') {
                  onChange({ transferScope: { type: 'handler_groups', group_ids: [] } });
                } else {
                  onChange({ transferScope: null });
                }
              }}
            />
            {transferScope?.type === 'users' && <>
              <label htmlFor={transferTargetsId}>可接收转交的人员</label>
              <UserSelector id={transferTargetsId} ariaLabel="可接收转交的人员"
                placeholder="选择人员" value={transferUsers}
                onChange={users => onChange({ transferScope: { type: 'users', users } })} />
            </>}
            {transferScope?.type === 'handler_groups' && <>
              <label htmlFor={transferTargetsId}>可接收转交的处理组</label>
              <Select id={transferTargetsId} aria-label="可接收转交的处理组" placeholder="选择处理组"
                mode="multiple" showSearch optionFilterProp="label" loading={groupLoading}
                notFoundContent={groupLoading ? '正在加载处理组' : '暂无可选择的处理组'}
                value={transferGroupIds} options={groupOptions}
                onChange={group_ids => onChange({ transferScope: { type: 'handler_groups', group_ids } })} />
              {groupError && <span role="alert">{groupError}</span>}
            </>}
            {transferScopeError && <span className="text-xs text-[var(--color-text-3)]">{transferScopeError}</span>}
          </fieldset>}
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
