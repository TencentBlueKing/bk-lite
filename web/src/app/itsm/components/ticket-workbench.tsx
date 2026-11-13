'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Key } from 'react';
import Link from 'next/link';
import dayjs from 'dayjs';
import { Alert, App, Button, Checkbox, DatePicker, Input, Modal, Popconfirm, Select, Spin, Table, Tabs, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { CloseOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { UserSelector } from './user-selector';
import { TicketTagSelector } from './ticket-tag-selector';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketListItem } from '../types';

const DEFAULT_COLUMNS = ['sn', 'title', 'status', 'creator', 'node', 'created_at'];
const FIELD_LABELS: Record<string, string> = { sn: '单号', title: '标题', status: '状态', creator: '提单人', node: '当前节点', assignees: '当前处理人', workflow: '流程', created_at: '创建时间', updated_at: '更新时间', priority: '优先级', sla: 'SLA截止时间' };
const STATUS = [
  { value: 'new', label: '新建', color: 'processing' }, { value: 'processing', label: '处理中', color: 'warning' },
  { value: 'suspended', label: '已挂起', color: 'purple' }, { value: 'finished', label: '已完成', color: 'success' },
  { value: 'terminated', label: '已终止', color: 'error' }, { value: 'cancelled', label: '已撤回', color: 'default' },
];
const GROUPS = [{ key: 'all', label: '全部工单' }, { key: 'mine', label: '我的待办' }, { key: 'created', label: '我发起的' }, { key: 'following', label: '我关注的' }, { key: 'history', label: '我的历史' }];
const ACTIONS = [{ value: 'follow', label: '关注' }, { value: 'unfollow', label: '取消关注' }, { value: 'submit', label: '提交' }, { value: 'approve', label: '审批通过' }, { value: 'reject', label: '审批拒绝' }, { value: 'claim', label: '认领' }, { value: 'urge', label: '催办' }, { value: 'suspend', label: '挂起' }, { value: 'resume', label: '恢复' }];
interface Filters { q: string; status: string; creator: string; priority: string; tag: string; created_after: string; created_before: string; tab: string; ordering: string }
const EMPTY: Filters = { q: '', status: '', creator: '', priority: '', tag: '', created_after: '', created_before: '', tab: 'all', ordering: '-created_at' };
interface SavedView { id: number; name: string; filters: Partial<Filters> }
interface Settings { columns: string[]; views: SavedView[] }
interface BatchResult { id: number; ok: boolean; error?: string }
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试';

export function TicketWorkbench() {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [columns, setColumns] = useState(DEFAULT_COLUMNS);
  const [columnDraft, setColumnDraft] = useState(DEFAULT_COLUMNS);
  const [views, setViews] = useState<SavedView[]>([]);
  const [settingsReady, setSettingsReady] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [tab, setTab] = useState('all');
  const [query, setQuery] = useState<Filters>(EMPTY);
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<TicketListItem[]>([]);
  const [batchOptions, setBatchOptions] = useState<string[]>([]);
  const [batchReason, setBatchReason] = useState('');
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<Key[]>([]);
  const [columnOpen, setColumnOpen] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [groupName, setGroupName] = useState('');
  const [saving, setSaving] = useState(false);
  const [action, setAction] = useState('follow');
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const batchLock = useRef(false);
  const [opinion, setOpinion] = useState('');
  const [results, setResults] = useState<BatchResult[] | null>(null);
  const [batchNames, setBatchNames] = useState<Record<number, string>>({});

  const loadSettings = useCallback(async () => {
    try {
      const value = await api.centerSettings() as Settings;
      setColumns(value.columns); setViews(value.views); setSettingsReady(true); setSettingsError('');
    } catch (error) { setSettingsError(errorText(error)); }
  }, [api.centerSettings]);
  useEffect(() => { if (api.ready) void loadSettings(); }, [api.ready, loadSettings]);
  useEffect(() => {
    if (!api.ready || !settingsReady) return;
    let active = true;
    setLoading(true); setLoadError('');
    void api.listTickets({ ...query, fields: columns.join(','), page, page_size: pageSize }).then((value) => {
      if (!active) return;
      const result = value as { items: TicketListItem[]; count: number; can_operate: boolean };
      setItems(result.items); setTotal(result.count);
    }).catch((error: unknown) => { if (active) { setLoadError(errorText(error)); setItems([]); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api.ready, api.listTickets, settingsReady, query, columns, page, pageSize, refresh]);

  useEffect(() => {
    let active = true;
    setBatchOptions([]); setBatchReason('');
    if (!selected.length) return;
    setOptionsLoading(true);
    void api.batchOptions(selected.map(Number)).then(value => {
      if (!active) return;
      const result = value as { actions: string[]; reason: string };
      setBatchOptions(result.actions); setBatchReason(result.reason);
      setAction(current => result.actions.includes(current) ? current : result.actions[0] || '');
    }).catch((error: unknown) => { if (active) setBatchReason(errorText(error)); })
      .finally(() => { if (active) setOptionsLoading(false); });
    return () => { active = false; };
  }, [selected, api.batchOptions]);

  const apply = (next: Filters) => { setQuery({ ...next }); setDraft(next); setPage(1); setSelected([]); };
  const switchTab = (key: string) => {
    const saved = views.find(view => `view:${view.id}` === key);
    setTab(key); apply(saved ? { ...EMPTY, ...saved.filters } : { ...EMPTY, tab: key });
  };
  const saveColumns = async (value: string[] | null) => {
    setSaving(true);
    try {
      const result = await api.saveTicketColumns(value) as { columns: string[] };
      setColumns(result.columns); setColumnOpen(false); setSelected([]);
    } catch (error) { message.error(errorText(error)); } finally { setSaving(false); }
  };
  const saveGroup = async () => {
    setSaving(true);
    try {
      const saved = await api.saveTicketGroup(groupName.trim(), { ...query }) as SavedView;
      setViews(current => [...current, saved]); setTab(`view:${saved.id}`); setGroupOpen(false); setGroupName('');
    } catch (error) { message.error(errorText(error)); } finally { setSaving(false); }
  };
  const deleteGroup = async (id: number) => {
    try {
      await api.deleteTicketGroup(id); setViews(current => current.filter(view => view.id !== id));
      if (tab === `view:${id}`) { setTab('all'); apply(EMPTY); }
    } catch (error) { message.error(errorText(error)); }
  };
  const runBatch = async () => {
    if (batchLock.current || optionsLoading || !batchOptions.includes(action)) return;
    batchLock.current = true; setBatchBusy(true);
    try {
      const result = await api.batchTickets(selected.map(Number), action, opinion) as { items: BatchResult[] };
      setResults(result.items); setSelected([]); setRefresh(value => value + 1);
    } catch (error) { message.error(errorText(error)); } finally { batchLock.current = false; setBatchBusy(false); }
  };

  const sortable = new Set(['sn', 'title', 'status', 'creator', 'created_at', 'updated_at']);
  const tableColumns: TableColumnsType<TicketListItem> = columns.map(key => ({
    title: FIELD_LABELS[key], key, dataIndex: key, width: key === 'title' ? 260 : key === 'sn' ? 230 : key.endsWith('_at') ? 180 : 150,
    sorter: sortable.has(key), sortOrder: query.ordering.replace('-', '') === key ? query.ordering.startsWith('-') ? 'descend' : 'ascend' : null,
    ellipsis: true,
    render: (value: unknown, record: TicketListItem) => {
      if (key === 'sn' || key === 'title') return <Link href={`/itsm/tickets/${record.id}`} className="text-[var(--color-primary)]">{String(value || '—')}</Link>;
      if (key === 'status') { const status = STATUS.find(item => item.value === value); return <Tag color={status?.color}>{status?.label || String(value || '—')}</Tag>; }
      if (key === 'node') return record.tasks?.map(task => task.node_name || task.node_id).join('、') || '—';
      if (key === 'assignees') return [...new Set(record.tasks?.map(task => task.assignee).filter(Boolean))].map(name => <Tag key={name}>{name}</Tag>);
      if (key.endsWith('_at')) return value ? dayjs(String(value)).format('YYYY-MM-DD HH:mm') : '—';
      if (key === 'sla') return record.sla_due_at ? <Tag color={record.sla_breached ? 'error' : 'default'}>{dayjs(record.sla_due_at).format('MM-DD HH:mm')}{record.sla_breached ? ' 已超时' : ''}</Tag> : '—';
      return String(value || '—');
    },
  }));


  if (settingsError) return <Alert type="error" message={settingsError} action={<Button onClick={() => void loadSettings()}>重试</Button>} />;
  if (!settingsReady) return <Spin />;
  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <Tabs activeKey={tab} onChange={switchTab} items={[
      ...GROUPS,
      ...views.map(view => ({ key: `view:${view.id}`, label: <span className="inline-flex items-center gap-2">{view.name}<Popconfirm title={`删除分组“${view.name}”？`} description="不删除其中的工单。" onConfirm={event => { event?.stopPropagation(); return deleteGroup(view.id); }} onCancel={event => event?.stopPropagation()}><Button type="text" size="small" aria-label={`删除分组 ${view.name}`} icon={<CloseOutlined />} onClick={event => event.stopPropagation()} /></Popconfirm></span> })),
    ]} />
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">关键词<Input aria-label="工单关键词" placeholder="输入部分单号或标题" className="w-56" allowClear value={draft.q} onChange={event => setDraft({ ...draft, q: event.target.value })} onPressEnter={() => apply({ ...draft, q: draft.q.trim() })} /></label>
      <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">状态<Select aria-label="筛选状态" mode="multiple" maxTagCount="responsive" className="w-52" allowClear placeholder="全部状态" options={STATUS} value={draft.status ? draft.status.split(',') : []} onChange={value => setDraft({ ...draft, status: value.join(',') })} /></label>
      <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">提单人<div className="w-48"><UserSelector ariaLabel="筛选提单人" multiple={false} allowClear placeholder="搜索并选择提单人" value={draft.creator ? [draft.creator] : []} onChange={value => setDraft({ ...draft, creator: value[0] || '' })} /></div></label>
      <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">优先级<Input aria-label="筛选优先级" className="w-28" allowClear placeholder="优先级" value={draft.priority} onChange={event => setDraft({ ...draft, priority: event.target.value })} /></label>
      <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">标签<TicketTagSelector value={draft.tag} onChange={tag => setDraft({ ...draft, tag })} /></label>
      <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">创建时间<DatePicker.RangePicker value={draft.created_after && draft.created_before ? [dayjs(draft.created_after), dayjs(draft.created_before)] : null} onChange={value => setDraft({ ...draft, created_after: value?.[0]?.format('YYYY-MM-DD') || '', created_before: value?.[1]?.format('YYYY-MM-DD') || '' })} /></label>
      <div className="flex gap-2"><Button type="primary" onClick={() => apply({ ...draft, q: draft.q.trim(), creator: draft.creator.trim(), tag: draft.tag.trim(), priority: draft.priority.trim() })}>查询</Button>
      <Button onClick={() => apply({ ...EMPTY, tab: query.tab })}>重置</Button></div>
    </div>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm text-[var(--color-text-3)]">共 {total} 张工单{tab === 'history' ? ' · 我已处理过的工单' : ''}</span>
      <div className="flex items-center gap-2"><Button type="primary" disabled={loading || selected.length === 0 || optionsLoading || !batchOptions.includes(action)} onClick={() => { setOpinion(''); setResults(null); setBatchNames(Object.fromEntries(items.map(item => [item.id, `${item.sn} · ${item.title}`]))); setBatchOpen(true); }}>批量处理</Button><Button onClick={() => { setGroupName(''); setGroupOpen(true); }}>保存为分组</Button><Button icon={<SettingOutlined />} onClick={() => { setColumnDraft(columns); setColumnOpen(true); }}>展示字段</Button><Button aria-label="刷新列表" icon={<ReloadOutlined />} onClick={() => { setSelected([]); setRefresh(value => value + 1); }} /></div>
    </div>
    {selected.length > 0 ? <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-primary)] bg-[var(--color-bg)] p-3"><span>已选 {selected.length} 项</span><Select aria-label="批量操作类型" className="w-36" value={action} loading={optionsLoading} disabled={optionsLoading} options={ACTIONS.filter(item => batchOptions.includes(item.value))} onChange={setAction} /><Button type="text" onClick={() => setSelected([])}>取消选择</Button><span className="text-xs text-[var(--color-text-3)]">仅选择当前页，每次最多 50 项</span></div> : null}
    {loadError ? <Alert className="mb-3" type="error" message={loadError} action={<Button onClick={() => setRefresh(value => value + 1)}>重试</Button>} /> : null}
    <CustomTable<TicketListItem> scroll={{ y: 'calc(100vh - 440px)' }} rowKey="id" loading={loading} dataSource={items} columns={tableColumns}
      rowSelection={{ selectedRowKeys: selected, onChange: keys => setSelected(keys.slice(0, 50)), preserveSelectedRowKeys: false, getCheckboxProps: () => ({ disabled: loading }) }}
      pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); setSelected([]); } }}
      onChange={(_pagination, _filters, sort, extra) => { if (extra.action === 'sort') { const value = Array.isArray(sort) ? sort[0] : sort; apply({ ...query, ordering: value.order ? `${value.order === 'descend' ? '-' : ''}${String(value.columnKey)}` : '-created_at' }); } }}
      locale={{ emptyText: '暂无符合条件的工单' }} />
    <Modal title="个性化展示字段" open={columnOpen} onCancel={() => !saving && setColumnOpen(false)} footer={<div className="flex justify-between"><Button disabled={saving} onClick={() => void saveColumns(null)}>恢复默认</Button><Button type="primary" loading={saving} onClick={() => void saveColumns(columnDraft)}>保存配置</Button></div>}>
      <p className="mb-4 text-sm text-[var(--color-text-3)]">仅对当前账号生效；单号和标题始终显示。</p>
      <Checkbox.Group className="grid grid-cols-2 gap-3" value={columnDraft} options={Object.entries(FIELD_LABELS).map(([value, label]) => ({ value, label, disabled: ['sn', 'title'].includes(value) }))} onChange={value => setColumnDraft(value as string[])} />
    </Modal>
    <Modal title="保存筛选分组" open={groupOpen} onCancel={() => !saving && setGroupOpen(false)} onOk={() => void saveGroup()} confirmLoading={saving} okText="保存分组" okButtonProps={{ disabled: !groupName.trim() }}>
      <p className="mb-3 text-sm text-[var(--color-text-3)]">保存当前已应用的筛选及排序条件，分组内工单将随数据自动更新。</p><Input aria-label="分组名称" placeholder="例如：我关注的处理中工单" value={groupName} maxLength={40} onChange={event => setGroupName(event.target.value)} />
    </Modal>
    {selected.length > 0 && batchReason ? <Alert className="mb-3" type="warning" message={batchReason} /> : null}
    <Modal title={results ? '批量操作结果' : `批量${ACTIONS.find(item => item.value === action)?.label}`} open={batchOpen} closable={!batchBusy} maskClosable={!batchBusy} onCancel={() => !batchBusy && setBatchOpen(false)} footer={results ? <Button onClick={() => setBatchOpen(false)}>关闭</Button> : <Button type="primary" danger={action === 'reject'} loading={batchBusy} disabled={optionsLoading || !batchOptions.includes(action)} onClick={() => void runBatch()}>确认执行</Button>}>
      {results ? <><Alert className="mb-3" type={results.every(item => item.ok) ? 'success' : 'warning'} message={`成功 ${results.filter(item => item.ok).length} 项，失败 ${results.filter(item => !item.ok).length} 项`} /><Table size="small" rowKey="id" pagination={false} dataSource={results} columns={[{ title: '工单', render: (_value, record: BatchResult) => batchNames[record.id] || record.id }, { title: '结果', render: (_value, record: BatchResult) => record.ok ? <Tag color="success">成功</Tag> : record.error }]} /></> : <><Alert type="info" className="mb-3" message={`将对选中的 ${selected.length} 张工单执行操作，逐单校验权限、节点和必填字段。`} /><div className="mb-3 max-h-36 overflow-auto text-sm">{selected.map(id => <div key={id} className="py-1">{batchNames[Number(id)]}</div>)}</div>{!['follow', 'unfollow'].includes(action) ? <Input.TextArea aria-label="批量操作意见" placeholder="操作意见（可选）" maxLength={1000} rows={3} value={opinion} onChange={event => setOpinion(event.target.value)} /> : null}</>}
    </Modal>
  </div>;
}
