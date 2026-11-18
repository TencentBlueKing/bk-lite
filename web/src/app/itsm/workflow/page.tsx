'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';

import { ItsmListToolbar, ItsmListTabs, ItsmCreateButton, ItsmRowActions } from '@/app/itsm/components/list-controls';

import { Alert, Button, Empty, Popconfirm, Spin, Tag, Tooltip, message } from 'antd';
import { ImportDialog } from '../components/import-dialog';
import { PlayCircleOutlined } from '@ant-design/icons';
import { ItsmDrawer as OperateModal } from '@/app/itsm/components/interaction-surfaces';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../api/useItsmApi';
import type { WorkflowListItem } from '../types';

interface Version { id: number; version_no: number; is_current: boolean; is_published: boolean; ticket_count: number }
interface ListResult { items?: WorkflowListItem[]; can_add?: boolean; can_edit?: boolean; can_publish?: boolean }
const report = (error: unknown) => message.error(error instanceof Error ? error.message : '操作失败，请重试');

export default function WorkflowListPage() {
  const api = useItsmApi();
  const router = useRouter();
  const requestId = useRef(0);
  const [data, setData] = useState<ListResult>({});
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('all');
  const [versions, setVersions] = useState<Version[]>([]);
  const [selected, setSelected] = useState<WorkflowListItem | null>(null);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versionError, setVersionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [switching, setSwitching] = useState<number>();
  const load = useCallback(async () => setData(await api.listWorkflows() as ListResult), [api.listWorkflows]);
  useEffect(() => { if (api.ready) void load().catch(report); }, [api.ready, load]);
  const loadVersions = async (record: WorkflowListItem) => {
    const token = ++requestId.current;
    setSelected(record); setVersions([]); setVersionError(''); setVersionLoading(true);
    try {
      const result = await api.listWorkflowVersions(record.id) as {items?: Version[]};
      if (token === requestId.current) setVersions(result.items || []);
    } catch (error) { if (token === requestId.current) setVersionError(error instanceof Error ? error.message : '版本加载失败'); }
    finally { if (token === requestId.current) setVersionLoading(false); }
  };
  const create = async () => {
    setBusy(true);
    try { const created = await api.createWorkflow({name:'新建流程',key:`flow_${Date.now()}`}) as {id:number}; router.push(`/itsm/workflow/designer/${created.id}`); }
    catch(error) { report(error); } finally { setBusy(false); }
  };
  const importFile = async (file: File) => {
    setBusy(true);
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('流程文件不能超过 5MB');
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('请选择有效的流程 JSON 文件');
      const bundle = parsed as Record<string, unknown>;
      await api.importWorkflow(bundle.design ? bundle : {design:bundle});
      await load(); message.success('导入成功'); return true;
    } catch (error) { report(error); return false; } finally { setBusy(false); }
  };
  const exportFile = async (record: WorkflowListItem) => {
    try {
      const result = await api.exportWorkflow(record.id);
      const url = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
      const link = document.createElement('a'); link.href=url; link.download=`${record.key}.json`; link.click(); URL.revokeObjectURL(url);
    } catch(error) { report(error); }
  };
  const enable = async (version: Version) => {
    if (!selected) return;
    const record = selected; const token = requestId.current; setSwitching(version.id);
    try { await api.enableWorkflowVersion(record.id,version.id); message.success('版本已启用'); await load(); if (requestId.current === token) await loadVersions(record); }
    catch(error) { report(error); } finally { setSwitching(undefined); }
  };
  return <div className="flex min-h-0 flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar leading={<ItsmListTabs activeKey={status} onChange={setStatus} items={[
      {key:'all',label:'全部'}, {key:'published',label:'已发布'}, {key:'unpublished',label:'未发布'},
    ]} />} search={{value: keyword, onChange: setKeyword, label: '搜索流程', placeholder: '搜索名称或标识'}} actions={<>
{data.can_add && <>
  <ImportDialog accept=".json,application/json" onImport={importFile} />
  <ItsmCreateButton aria-label="新建流程" loading={busy} onClick={() => void create()} />
</>}
</>} />
    <CustomTable queryKey={`${status}:${keyword}`} rowKey="id" dataSource={(data.items || []).filter(item=>(status === 'all' || (status === 'published' ? !!item.current_version_id : !item.current_version_id)) && `${item.name} ${item.key}`.toLowerCase().includes(keyword.trim().toLowerCase()))} columns={[
      {title:'流程名称',dataIndex:'name',key:'name',render:(value:string,row:WorkflowListItem)=><ItsmListEntry allowed={Boolean(data.can_edit)} href={`/itsm/workflow/designer/${row.id}`}>{value}</ItsmListEntry>}, {title:'标识',dataIndex:'key',key:'key'},
      {title:'当前版本',key:'status',render:(_,row:WorkflowListItem)=><Tag color={row.current_version_id?'processing':'default'}>{row.current_version_id?`V${row.current_version_no}`:'未发布'}</Tag>},
      {title:'操作',key:'action',fixed:'right',width:120,render:(_,row:WorkflowListItem)=><ItsmRowActions items={[
        {key:'design',label:'设计',kind:'edit',hidden:!data.can_edit,onClick:()=>router.push(`/itsm/workflow/designer/${row.id}`)},
        {key:'versions',label:'版本管理',kind:'history',onClick:()=>void loadVersions(row)},
        {key:'export',label:'导出',kind:'export',more:true,onClick:()=>void exportFile(row)},
      ]} />}

    ]} />
    <OperateModal title={`${selected?.name || ''} · 版本管理`} width={760} open={!!selected} footer={null} onCancel={()=>{requestId.current++;setSelected(null);}}>
      <Alert type="info" showIcon className="mb-4" message="草稿可编辑，发布后锁定。启用历史版本仅影响新工单，已有工单继续使用原版本。" />
      {versionError ? <Alert type="error" message={versionError} action={<Button onClick={()=>selected && void loadVersions(selected)}>重试</Button>} /> : <Spin spinning={versionLoading}><CustomTable<Version> rowKey="id" size="small" scroll={{y: '45vh'}} dataSource={versions} locale={{emptyText:<Empty description="暂无版本，保存设计后生成草稿" />}} columns={[
        {title:'版本',dataIndex:'version_no',render:value=>`V${value}`},
        {title:'状态',render:(_,row)=><Tag color={row.is_current?'processing':row.is_published?'default':'warning'}>{row.is_current?'当前版本':row.is_published?'历史版本':'草稿'}</Tag>},
        {title:'工单数',dataIndex:'ticket_count'},
        {title:'操作',render:(_,row)=>row.is_published && !row.is_current && data.can_publish ? <Popconfirm title={`启用 V${row.version_no}？`} description="新工单将使用该版本，已有工单不受影响。" okText="确认启用" cancelText="取消" onConfirm={()=>enable(row)}><Tooltip title="启用此版本"><Button type="text" icon={<PlayCircleOutlined />} loading={switching===row.id} disabled={switching!==undefined} aria-label="启用此版本" /></Tooltip></Popconfirm>:null}
      ]}/></Spin>}
    </OperateModal>
  </div>;
}
