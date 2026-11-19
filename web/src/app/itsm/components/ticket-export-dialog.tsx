'use client';

import { useEffect, useState } from 'react';
import { Alert, Button, Checkbox, Radio, Select, Spin } from 'antd';
import { ItsmModal } from './interaction-surfaces';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketCenterFilters, TicketExportCatalog } from '../types';

export function TicketExportDialog({ filters, selected, total, onClose, onSubmitted }: {
  filters: TicketCenterFilters;
  selected: number[];
  total: number;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const { exportTickets, ticketExportFields } = useItsmApi();
  const [scope, setScope] = useState(selected.length ? 'selected' : 'filtered');
  const [catalog, setCatalog] = useState<TicketExportCatalog>();
  const [formCatalog, setFormCatalog] = useState<{ id: string; data?: TicketExportCatalog; error?: string }>();
  const [columns, setColumns] = useState<string[]>();
  const [workflowId, setWorkflowId] = useState(filters.workflow_id);
  const [formColumns, setFormColumns] = useState<string[]>([]);
  const [keyword, setKeyword] = useState('');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const count = scope === 'selected' ? selected.length : total;

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      setSearching(true);
      setError('');
      void ticketExportFields(filters.workflow_id ? { workflow_id: filters.workflow_id } : { q: keyword.trim() }).then(data => {
        if (!active) return;
        setCatalog(data);
        setColumns(current => current ?? data.default_columns);
        if (filters.workflow_id) setFormCatalog({ id: filters.workflow_id, data });
      }).catch(() => {
        if (active) setError('加载可导出字段失败。');
      }).finally(() => { if (active) setSearching(false); });
    }, keyword ? 250 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [ticketExportFields, keyword, filters.workflow_id, refresh]);

  useEffect(() => {
    if (!workflowId || filters.workflow_id) return;
    let active = true;
    void ticketExportFields({ workflow_id: workflowId }).then(data => {
      if (active) setFormCatalog({ id: workflowId, data });
    }).catch(() => {
      if (active) setFormCatalog({ id: workflowId, error: '加载表单字段失败，请重新选择流程。' });
    });
    return () => { active = false; };
  }, [ticketExportFields, workflowId, filters.workflow_id]);

  const currentForm = formCatalog?.id === workflowId ? formCatalog : undefined;
  const formFields = currentForm?.data?.fields || [];
  const workflows = catalog?.workflows || [];
  const workflow = currentForm?.data?.workflow;
  const workflowOptions = workflow && !workflows.some(item => item.id === workflow.id) ? [workflow, ...workflows] : workflows;
  const updateColumns = (key: string, checked: boolean) => {
    setColumns(previous => checked ? [...(previous ?? []), key] : previous?.filter(item => item !== key));
  };
  const submitExport = async () => {
    if (!columns) return;
    await exportTickets(filters, formColumns, scope === 'selected' ? selected : undefined, {
      columns,
      ...(formColumns.length && !filters.workflow_id ? { form_workflow_id: workflowId } : {}),
    });
    onSubmitted();
  };

  return <ItsmModal open title="导出工单" width={760} okText="提交导出" onOk={submitExport} onCancel={onClose}
    styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
    okButtonProps={{ disabled: !columns || !count || count > 5000 }}>
    <div className="flex flex-col gap-4">
      <Radio.Group value={scope} onChange={event => setScope(event.target.value)}
        options={[
          { value: 'filtered', label: `当前筛选结果（${total}）` },
          { value: 'selected', label: `已选工单（${selected.length}）`, disabled: !selected.length },
        ]} />
      {count > 5000 && <Alert type="warning" showIcon message="一次最多导出 5000 张工单，请缩小筛选范围或勾选要导出的工单。" />}
      {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => setRefresh(value => value + 1)}>重试</Button>} />}
      {!catalog && !error && <Spin />}
      {catalog && <section aria-label="工单字段">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="m-0 text-sm font-semibold">工单字段</h3>
          <div className="flex gap-2">
            <Button size="small" type="link" onClick={() => setColumns(catalog.groups.flatMap(group => group.columns.map(item => item.key)))}>全选</Button>
            <Button size="small" type="link" onClick={() => setColumns(catalog.default_columns)}>恢复默认</Button>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {catalog.groups.map(group => <fieldset key={group.key} className="min-w-0 rounded border border-[var(--color-border)] px-3 pb-3">
            <legend className="mb-2 w-auto px-1 text-xs font-semibold">{group.label}</legend>
            <div className="grid grid-cols-2 gap-x-2 gap-y-2">
              {group.columns.map(item => <Checkbox key={item.key} checked={columns?.includes(item.key)} disabled={item.key === 'sn'}
                onChange={event => updateColumns(item.key, event.target.checked)}>{item.label}</Checkbox>)}
            </div>
          </fieldset>)}
        </div>
      </section>}
      <section aria-label="表单字段" className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
        <h3 className="m-0 text-sm font-semibold">表单字段</h3>
        {!filters.workflow_id && <Select aria-label="导出表单流程" showSearch allowClear filterOption={false} value={workflowId || undefined}
          placeholder="搜索流程以选择对应表单字段" loading={searching}
          options={workflowOptions.map(item => ({ value: String(item.id), label: item.name }))}
          onSearch={setKeyword} onOpenChange={open => { if (!open) setKeyword(''); }}
          onChange={value => { setWorkflowId(value || ''); setFormColumns([]); setFormCatalog(undefined); }} />}
        {workflowId && <Select aria-label="导出表单字段" mode="multiple" allowClear showSearch maxCount={30}
          filterOption={(input, option) => `${option?.label} ${option?.value}`.toLowerCase().includes(input.toLowerCase())}
          loading={!currentForm} value={formColumns} options={formFields.map(field => ({ value: field.key, label: field.label }))}
          placeholder="选择要导出的表单字段" notFoundContent="暂无可导出的表单字段" onChange={setFormColumns} />}
        {currentForm?.error && <Alert type="warning" showIcon message={currentForm.error} />}
        {!filters.workflow_id && workflowId && <p className="m-0 text-xs text-[var(--color-text-3)]">其他流程的工单在这些表单列留空。</p>}
      </section>
    </div>
  </ItsmModal>;
}
