'use client';

import { ItsmListEntry } from '@/app/itsm/components/list-entry';
import { ItsmModal as Modal } from '@/app/itsm/components/interaction-surfaces';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { Key } from 'react';
import dayjs from 'dayjs';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import { Alert, App, Button, Checkbox, DatePicker, Input, Popconfirm, Popover, Tooltip, Select, Spin, Table, Tabs, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { CloseOutlined, DownloadOutlined, FilterOutlined, HistoryOutlined, PlusOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { UserSelector } from './user-selector';
import { TicketTagSelector } from './ticket-tag-selector';
import { TicketFormFilters, completeFormConditions } from './ticket-form-filters';
import { TicketExportDialog } from './ticket-export-dialog';
import { TicketExportHistory } from './ticket-export-history';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketCenterFilters as Filters, TicketListItem } from '../types';

const DEFAULT_COLUMNS = ['sn', 'title', 'status', 'creator', 'node', 'created_at'];
const FIELD_LABELS: Record<string, string> = { sn: '单号', title: '标题', status: '状态', creator: '提单人', node: '当前节点', assignees: '当前处理人', workflow: '流程', created_at: '创建时间', updated_at: '更新时间', priority: '优先级', sla: 'SLA截止时间' };
const STATUS = [
  { value: 'new', label: '新建', color: 'processing' }, { value: 'processing', label: '处理中', color: 'warning' },
  { value: 'suspended', label: '已挂起', color: 'purple' }, { value: 'finished', label: '已完成', color: 'success' },
  { value: 'terminated', label: '已终止', color: 'error' }, { value: 'cancelled', label: '已撤回', color: 'default' },
];
const GROUPS = [{ key: 'all', label: '全部工单' }, { key: 'mine', label: '我的待办' }, { key: 'created', label: '我发起的' }, { key: 'following', label: '我关注的' }, { key: 'history', label: '我的历史' }];
const ACTIONS = [{ value: 'follow', label: '关注' }, { value: 'unfollow', label: '取消关注' }, { value: 'submit', label: '提交' }, { value: 'approve', label: '审批通过' }, { value: 'reject', label: '审批拒绝' }, { value: 'claim', label: '认领' }, { value: 'urge', label: '催办' }, { value: 'suspend', label: '挂起' }, { value: 'resume', label: '恢复' }];
const EMPTY: Filters = { q: '', status: '', creator: '', priority: '', tag: '', created_after: '', created_before: '', tab: 'all', ordering: '-created_at', workflow_id: '', form_filters: [] };
interface SavedView { id: number; name: string; filters: Partial<Filters> }
interface Settings { columns: string[]; views: SavedView[] }
interface BatchResult { id: number; ok: boolean; error?: string }
interface BatchOptions {
  actions: string[];
  reason: string;
  required_opinion_actions?: string[];
}
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试';

export function TicketWorkbench({ initialTab = 'all' }: { initialTab?: string }) {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [columns, setColumns] = useState(DEFAULT_COLUMNS);
  const [columnDraft, setColumnDraft] = useState(DEFAULT_COLUMNS);
  const [views, setViews] = useState<SavedView[]>([]);
  const [settingsReady, setSettingsReady] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [tab, setTab] = useState(initialTab);
  const [query, setQuery] = useState<Filters>({ ...EMPTY, tab: initialTab });
  const [draft, setDraft] = useState<Filters>({ ...EMPTY, tab: initialTab });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [canExport, setCanExport] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportHistoryOpen, setExportHistoryOpen] = useState(false);
  const [items, setItems] = useState<TicketListItem[]>([]);
  const [batchAvailability, setBatchAvailability] = useState<{ selection: Key[]; options: BatchOptions }>();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<Key[]>([]);
  const [columnOpen, setColumnOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [groupName, setGroupName] = useState('');
  const [groupFilters, setGroupFilters] = useState<Filters>({ ...EMPTY, tab: initialTab });
  const [saving, setSaving] = useState(false);
  const [action, setAction] = useState('follow');
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const batchLock = useRef(false);
  const [opinion, setOpinion] = useState('');
  const batchOpinionId = useId();
  const [results, setResults] = useState<BatchResult[] | null>(null);
  const [batchNames, setBatchNames] = useState<Record<number, string>>({});
  const availability = batchAvailability?.selection === selected ? batchAvailability.options : undefined;
  const batchOptions = availability?.actions ?? [];
  const optionsLoading = selected.length > 0 && !availability;
  const opinionRequired = availability?.required_opinion_actions?.includes(action) ?? false;
  const batchActionAvailable = !optionsLoading && batchOptions.includes(action);
  const canConfirmBatch = batchActionAvailable && (!opinionRequired || Boolean(opinion.trim()));

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
      const result = value as { items: TicketListItem[]; count: number; can_export: boolean };
      setItems(result.items); setTotal(result.count); setCanExport(result.can_export === true);
    }).catch((error: unknown) => { if (active) { setLoadError(errorText(error)); setItems([]); setTotal(0); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api.ready, api.listTickets, settingsReady, query, columns, page, pageSize, refresh]);

  useEffect(() => {
    if (!selected.length) return;
    let active = true;
    void api.batchOptions(selected.map(Number)).then(value => {
      if (!active) return;
      const options = value as BatchOptions;
      setBatchAvailability({ selection: selected, options });
      setAction(current => options.actions.includes(current) ? current : options.actions[0] || '');
    }).catch((error: unknown) => {
      if (active) setBatchAvailability({ selection: selected, options: { actions: [], reason: errorText(error) } });
    });
    return () => { active = false; };
  }, [selected, api.batchOptions]);

  const apply = (next: Filters) => { setQuery({ ...next }); setDraft(next); setPage(1); setSelected([]); };
  const applyDraft = () => {
    if (!completeFormConditions(draft.form_filters)) {
      setFilterOpen(true);
      message.warning('请填写完整的表单筛选条件');
      return;
    }
    apply({ ...draft, q: draft.q.trim() });
    setFilterOpen(false);
  };
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
      const saved = await api.saveTicketGroup(groupName.trim(), { ...groupFilters }) as SavedView;
      setViews(current => [...current, saved]); setTab(`view:${saved.id}`); apply({ ...EMPTY, ...saved.filters }); setGroupOpen(false); setGroupName('');
    } catch (error) { message.error(errorText(error)); } finally { setSaving(false); }
  };
  const deleteGroup = async (id: number) => {
    try {
      await api.deleteTicketGroup(id); setViews(current => current.filter(view => view.id !== id));
      if (tab === `view:${id}`) { setTab('all'); apply(EMPTY); }
    } catch (error) { message.error(errorText(error)); }
  };
  const runBatch = async () => {
    if (batchLock.current || !canConfirmBatch) return;
    batchLock.current = true; setBatchBusy(true);
    try {
      const result = await api.batchTickets(selected.map(Number), action, opinion.trim()) as { items: BatchResult[] };
      setResults(result.items); setSelected([]); setRefresh(value => value + 1);
    } catch (error) { message.error(errorText(error)); } finally { batchLock.current = false; setBatchBusy(false); }
  };

  const sortable = new Set(['sn', 'title', 'status', 'creator', 'created_at', 'updated_at']);
  const tableColumns: TableColumnsType<TicketListItem> = columns.map(key => ({
    title: FIELD_LABELS[key], key, dataIndex: key, width: key === 'title' ? 260 : key === 'sn' ? 230 : key.endsWith('_at') ? 180 : 150,
    sorter: sortable.has(key), sortOrder: query.ordering.replace('-', '') === key ? query.ordering.startsWith('-') ? 'descend' : 'ascend' : null,
    ellipsis: true,
    render: (value: unknown, record: TicketListItem) => {
      if (key === 'sn' || key === 'title') return <ItsmListEntry href={`/itsm/tickets/${record.id}`}>{String(value || '—')}</ItsmListEntry>;
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
  return <div className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <Tabs type="line" className="[&_.ant-tabs-nav]:!bg-transparent [&_.ant-tabs-tab]:!bg-transparent" tabBarExtraContent={<Tooltip title="保存当前筛选为分组"><Button type="text" aria-label="保存为分组" icon={<PlusOutlined />} onClick={() => { setGroupName(''); setGroupFilters({ ...draft }); setGroupOpen(true); }} /></Tooltip>} activeKey={tab} onChange={switchTab} items={[
      ...GROUPS,
      ...views.map(view => ({ key: `view:${view.id}`, label: <span className="inline-flex items-center gap-2">{view.name}<Popconfirm title={`删除分组“${view.name}”？`} description="不删除其中的工单。" onConfirm={event => { event?.stopPropagation(); return deleteGroup(view.id); }} onCancel={event => event?.stopPropagation()}><Button type="text" size="small" aria-label={`删除分组 ${view.name}`} icon={<CloseOutlined />} onClick={event => event.stopPropagation()} /></Popconfirm></span> })),
    ]} />
    <ToolbarSplitShell trailing={<>

        <Select aria-label="筛选状态" mode="multiple" maxTagCount="responsive" className="w-40" allowClear placeholder="全部状态" options={STATUS} value={draft.status ? draft.status.split(',') : []} onChange={value => setDraft({ ...draft, status: value.join(',') })} />
        <Popover trigger="click" placement="bottomRight" open={filterOpen} onOpenChange={setFilterOpen} title="更多筛选" content={<div className="grid max-h-[65vh] w-[min(500px,calc(100vw-48px))] grid-cols-2 gap-3 overflow-auto pr-1">
          <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">提单人<UserSelector ariaLabel="筛选提单人" multiple={false} allowClear placeholder="搜索并选择提单人" value={draft.creator ? [draft.creator] : []} onChange={value => setDraft({ ...draft, creator: value[0] || '' })} /></label>
          <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">标签<TicketTagSelector value={draft.tag} onChange={tag => setDraft({ ...draft, tag })} /></label>
          <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">优先级<Input aria-label="筛选优先级" allowClear placeholder="优先级" value={draft.priority} onChange={event => setDraft({ ...draft, priority: event.target.value })} /></label>
          <label className="col-span-2 flex flex-col gap-1 text-xs text-[var(--color-text-2)]">创建时间<DatePicker.RangePicker value={draft.created_after && draft.created_before ? [dayjs(draft.created_after), dayjs(draft.created_before)] : null} onChange={value => setDraft({ ...draft, created_after: value?.[0]?.format('YYYY-MM-DD') || '', created_before: value?.[1]?.format('YYYY-MM-DD') || '' })} /></label>
          <TicketFormFilters filters={draft} active={filterOpen} onChange={setDraft} />
          <Button className="col-span-2" type="primary" disabled={!completeFormConditions(draft.form_filters)} onClick={applyDraft}>应用筛选</Button>
        </div>}><Button aria-label="更多筛选" icon={<FilterOutlined />} type={draft.creator || draft.tag || draft.priority || draft.created_after || draft.created_before || draft.workflow_id ? 'primary' : 'default'}>筛选</Button></Popover>
        <Input aria-label="工单关键词" placeholder="输入部分单号或标题" className="!w-60" allowClear value={draft.q} onChange={event => setDraft({ ...draft, q: event.target.value })} onPressEnter={applyDraft} />
        <Button onClick={applyDraft}>查询</Button>
        <Button onClick={() => { apply({ ...EMPTY, ...(views.find(view => `view:${view.id}` === tab)?.filters || { tab: query.tab }) }); setFilterOpen(false); }}>重置</Button>
        <Tooltip title="刷新"><Button aria-label="刷新列表" icon={<ReloadOutlined />} onClick={() => { setSelected([]); setRefresh(value => value + 1); }} /></Tooltip>
      {canExport && <>
        <Button aria-label="导出记录" icon={<HistoryOutlined />} onClick={() => setExportHistoryOpen(true)}>导出记录</Button>
        <Button aria-label="导出" icon={<DownloadOutlined />} disabled={loading || total === 0} onClick={() => setExportOpen(true)}>导出</Button>
      </>}
      <Button type="primary" disabled={loading || !batchActionAvailable} onClick={() => { setOpinion(''); setResults(null); setBatchNames(Object.fromEntries(items.map(item => [item.id, `${item.sn} · ${item.title}`]))); setBatchOpen(true); }}>批量处理</Button>
    </>} />
    {selected.length > 0 ? <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-primary)] bg-[var(--color-bg)] p-3"><span>已选 {selected.length} 项</span><Select aria-label="批量操作类型" className="w-36" value={action} loading={optionsLoading} disabled={optionsLoading} options={ACTIONS.filter(item => batchOptions.includes(item.value))} onChange={setAction} /><Button type="text" onClick={() => setSelected([])}>取消选择</Button><span className="text-xs text-[var(--color-text-3)]">仅选择当前页，每次最多 50 项</span></div> : null}
    {loadError ? <Alert className="mb-3" type="error" message={loadError} action={<Button onClick={() => setRefresh(value => value + 1)}>重试</Button>} /> : null}
    <div className="relative [&_thead_th:last-child]:!pr-12">
    <Tooltip title="展示字段"><Button className="!absolute right-1 top-3 z-10" type="text" aria-label="展示字段" icon={<SettingOutlined />} onClick={() => { setColumnDraft(columns); setColumnOpen(true); }} /></Tooltip>
    <CustomTable<TicketListItem> scroll={{ y: selected.length ? 'calc(100vh - 460px)' : 'calc(100vh - 360px)' }} rowKey="id" loading={loading} dataSource={items} columns={tableColumns}
      rowSelection={{ selectedRowKeys: selected, onChange: keys => setSelected(keys.slice(0, 50)), preserveSelectedRowKeys: false, getCheckboxProps: () => ({ disabled: loading }) }}
      pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); setSelected([]); } }}
      onChange={(_pagination, _filters, sort, extra) => { if (extra.action === 'sort') { const value = Array.isArray(sort) ? sort[0] : sort; apply({ ...query, ordering: value.order ? `${value.order === 'descend' ? '-' : ''}${String(value.columnKey)}` : '-created_at' }); } }}
      locale={{ emptyText: '暂无符合条件的工单' }} />
    </div>
    <Modal confirmLoading={saving} formValue={columnDraft} title="个性化展示字段" open={columnOpen} onCancel={() => !saving && setColumnOpen(false)} footer={<div className="flex justify-between"><Button disabled={saving} onClick={() => void saveColumns(null)}>恢复默认</Button><Button type="primary" loading={saving} onClick={() => void saveColumns(columnDraft)}>保存配置</Button></div>}>
      <p className="mb-4 text-sm text-[var(--color-text-3)]">仅对当前账号生效；单号和标题始终显示。</p>
      <Checkbox.Group className="grid grid-cols-2 gap-3" value={columnDraft} options={Object.entries(FIELD_LABELS).map(([value, label]) => ({ value, label, disabled: ['sn', 'title'].includes(value) }))} onChange={value => setColumnDraft(value as string[])} />
    </Modal>
    <Modal formValue={{groupName,groupFilters}} title="新增筛选分组" width={600} open={groupOpen} onCancel={() => !saving && setGroupOpen(false)} onOk={() => void saveGroup()} confirmLoading={saving} okText="保存分组" okButtonProps={{ disabled: !groupName.trim() || !completeFormConditions(groupFilters.form_filters) }}>
      <p className="mb-3 text-sm text-[var(--color-text-3)]">工单需同时满足以下条件；同一状态字段内可匹配任一选项。保存后自动更新分组结果。</p>
      <div className="grid grid-cols-2 gap-4">
        <label className="col-span-2 flex flex-col gap-1">分组名称<Input aria-label="分组名称" placeholder="例如：我关注的处理中工单" value={groupName} maxLength={40} onChange={event => setGroupName(event.target.value)} /></label>
        <label className="flex flex-col gap-1">工单范围<Select aria-label="分组范围" value={groupFilters.tab} options={GROUPS.map(group => ({ value: group.key, label: group.label }))} onChange={value => setGroupFilters({ ...groupFilters, tab: value })} /></label>
        <label className="flex flex-col gap-1">状态<Select aria-label="分组状态" mode="multiple" allowClear placeholder="全部状态" options={STATUS} value={groupFilters.status ? groupFilters.status.split(',') : []} onChange={value => setGroupFilters({ ...groupFilters, status: value.join(',') })} /></label>
        <label className="col-span-2 flex flex-col gap-1">关键词<Input aria-label="分组关键词" allowClear placeholder="部分单号或标题" value={groupFilters.q} onChange={event => setGroupFilters({ ...groupFilters, q: event.target.value })} /></label>
        <label className="flex flex-col gap-1">提单人<UserSelector ariaLabel="分组提单人" multiple={false} allowClear value={groupFilters.creator ? [groupFilters.creator] : []} onChange={value => setGroupFilters({ ...groupFilters, creator: value[0] || '' })} /></label>
        <label className="flex flex-col gap-1">标签<TicketTagSelector value={groupFilters.tag} onChange={value => setGroupFilters({ ...groupFilters, tag: value })} /></label>
        <label className="flex flex-col gap-1">优先级<Input aria-label="分组优先级" allowClear value={groupFilters.priority} onChange={event => setGroupFilters({ ...groupFilters, priority: event.target.value })} /></label>
        <label className="col-span-2 flex flex-col gap-1">创建时间<DatePicker.RangePicker value={groupFilters.created_after && groupFilters.created_before ? [dayjs(groupFilters.created_after), dayjs(groupFilters.created_before)] : null} onChange={value => setGroupFilters({ ...groupFilters, created_after: value?.[0]?.format('YYYY-MM-DD') || '', created_before: value?.[1]?.format('YYYY-MM-DD') || '' })} /></label>
        <TicketFormFilters filters={groupFilters} active={groupOpen} onChange={setGroupFilters} />
      </div>
    </Modal>
    {exportOpen && <TicketExportDialog filters={query} selected={selected.map(Number)} total={total}
      onClose={() => setExportOpen(false)} onSubmitted={() => {
        setExportOpen(false);
        setExportHistoryOpen(true);
        message.success('已提交导出任务');
      }} />}
    {exportHistoryOpen && <TicketExportHistory onClose={() => setExportHistoryOpen(false)} />}
    {selected.length > 0 && availability?.reason ? <Alert className="mb-3" type="warning" message={availability.reason} /> : null}
    <Modal confirmLoading={batchBusy} formValue={results ? undefined : opinion} title={results ? '批量操作结果' : `批量${ACTIONS.find(item => item.value === action)?.label}`} open={batchOpen} closable={!batchBusy} maskClosable={!batchBusy} onCancel={() => !batchBusy && setBatchOpen(false)} footer={results ? <Button onClick={() => setBatchOpen(false)}>关闭</Button> : <Button type="primary" danger={action === 'reject'} loading={batchBusy} disabled={!canConfirmBatch} onClick={() => void runBatch()}>确认执行</Button>}>
      {results ? <><Alert className="mb-3" type={results.every(item => item.ok) ? 'success' : 'warning'} message={`成功 ${results.filter(item => item.ok).length} 项，失败 ${results.filter(item => !item.ok).length} 项`} /><Table size="small" rowKey="id" pagination={false} dataSource={results} columns={[{ title: '工单', render: (_value, record: BatchResult) => batchNames[record.id] || record.id }, { title: '结果', render: (_value, record: BatchResult) => record.ok ? <Tag color="success">成功</Tag> : record.error }]} /></> : <><Alert type="info" className="mb-3" message={`将对选中的 ${selected.length} 张工单执行操作，逐单校验权限、节点和必填字段。`} /><div className="mb-3 max-h-36 overflow-auto text-sm">{selected.map(id => <div key={id} className="py-1">{batchNames[Number(id)]}</div>)}</div>{!['follow', 'unfollow'].includes(action) ? <div className="flex flex-col gap-2">
        <label htmlFor={batchOpinionId}>批量操作意见{opinionRequired && <span className="text-[var(--color-text-3)]">（必填）</span>}</label>
        <Input.TextArea id={batchOpinionId} aria-label="批量操作意见" required={opinionRequired} placeholder={opinionRequired ? '填写处理意见' : '填写处理意见（选填）'}
          maxLength={1000} rows={3} value={opinion} onChange={event => setOpinion(event.target.value)} />
      </div> : null}</>}
    </Modal>
  </div>;
}
