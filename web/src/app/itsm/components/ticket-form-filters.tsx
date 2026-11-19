'use client';

import { useEffect, useState } from 'react';
import { Alert, Button, DatePicker, Input, InputNumber, Select, Tooltip } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketCenterFilters, TicketFilterField, TicketFilterWorkflow, TicketFormCondition, TicketFormOperator } from '../types';

const OPERATORS: Record<TicketFilterField['type'], TicketFormOperator[]> = {
  input: ['contains', 'eq'], textarea: ['contains', 'eq'], number: ['eq', 'gte', 'lte'], date: ['eq'], radio: ['eq'], select: ['eq'],
};
const OPERATOR_LABELS = { contains: '包含', eq: '等于', gte: '大于等于', lte: '小于等于' };

export const completeFormConditions = (conditions: TicketFormCondition[]) =>
  conditions.every(({ key, value }) => key && (typeof value === 'number' ? Number.isFinite(value) : value?.trim()));

export function useTicketFormFields(workflowId: string, enabled: boolean) {
  const { ticketFilterFields } = useItsmApi();
  const [result, setResult] = useState<{ id: string; fields: TicketFilterField[]; workflow?: TicketFilterWorkflow; error?: string }>();
  useEffect(() => {
    if (!enabled || !workflowId) return;
    let active = true;
    void ticketFilterFields(workflowId).then(value => {
      if (active) setResult({ id: workflowId, ...(value as { workflow: TicketFilterWorkflow; fields: TicketFilterField[] }) });
    }).catch(error => {
      if (active) setResult({ id: workflowId, fields: [], error: error instanceof Error ? error.message : '加载表单字段失败' });
    });
    return () => { active = false; };
  }, [enabled, workflowId, ticketFilterFields]);
  return {
    fields: result?.id === workflowId ? result.fields : [],
    workflow: result?.id === workflowId ? result.workflow : undefined,
    error: result?.id === workflowId ? result.error : undefined,
    loading: Boolean(workflowId && result?.id !== workflowId),
  };
}

export function TicketFormFilters({ filters, active, onChange }: {
  filters: TicketCenterFilters;
  active: boolean;
  onChange: (next: TicketCenterFilters) => void;
}) {
  const { ticketFilterWorkflows } = useItsmApi();
  const { workflow, fields, loading, error } = useTicketFormFields(filters.workflow_id, active);
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [workflows, setWorkflows] = useState<TicketFilterWorkflow[]>([]);
  const [searching, setSearching] = useState(false);
  const [workflowsError, setWorkflowsError] = useState('');
  useEffect(() => {
    if (!active || !open) return;
    let live = true;
    const timer = setTimeout(() => {
      setSearching(true);
      setWorkflowsError('');
      void ticketFilterWorkflows(keyword.trim()).then(result => {
        if (live) setWorkflows((result as { workflows: TicketFilterWorkflow[] }).workflows);
      }).catch(() => {
        if (live) { setWorkflows([]); setWorkflowsError('加载流程失败，请重新打开下拉框'); }
      }).finally(() => { if (live) setSearching(false); });
    }, keyword ? 250 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [active, open, keyword, ticketFilterWorkflows]);

  const conditions = filters.form_filters;
  const update = (index: number, change: Partial<TicketFormCondition>) =>
    onChange({ ...filters, form_filters: conditions.map((row, position) => position === index ? { ...row, ...change } : row) });
  const workflowOptions = workflow && !workflows.some(item => item.id === workflow.id) ? [workflow, ...workflows] : workflows;

  return <div className="col-span-2 flex min-w-0 flex-col gap-2 border-t border-[var(--color-border)] pt-3">
    <label className="flex flex-col gap-1 text-xs text-[var(--color-text-2)]">流程
      <Select aria-label="筛选流程" showSearch allowClear filterOption={false} placeholder="搜索有可见工单的流程"
        options={workflowOptions.map(item => ({ label: item.name, value: String(item.id) }))}
        loading={searching} notFoundContent={workflowsError || '暂无匹配流程'}
        value={filters.workflow_id || undefined} onSearch={setKeyword}
        onOpenChange={value => { setOpen(value); if (!value) { setKeyword(''); setSearching(false); } }}
        onChange={value => onChange({ ...filters, workflow_id: value || '', form_filters: [] })} />
    </label>
    {!filters.workflow_id && <span className="text-xs text-[var(--color-text-3)]">选择流程后可按表单字段筛选。</span>}
    {error && <Alert showIcon type="warning" message={error} />}
    {filters.workflow_id && !loading && !error && !fields.length && <span className="text-xs text-[var(--color-text-3)]">该流程暂无可筛选的表单字段。</span>}
    {conditions.length > 1 && <span className="text-xs text-[var(--color-text-3)]">结果须同时满足所有表单条件。</span>}
    {conditions.map((condition, index) => {
      const field = fields.find(item => item.key === condition.key);
      const operators = field ? OPERATORS[field.type] : [];
      const valueLabel = `条件值 ${index + 1}`;
      return <div key={index} className="grid min-w-0 grid-cols-[minmax(0,1fr)_112px] items-start gap-2 sm:grid-cols-[minmax(0,1fr)_112px_minmax(0,1fr)_auto]">
        <Select aria-label={`表单字段 ${index + 1}`} placeholder="字段" showSearch optionFilterProp="label" loading={loading}
          value={condition.key || undefined}
          options={fields.map(item => ({ label: item.label, value: item.key }))}
          onChange={key => {
            const selected = fields.find(item => item.key === key);
            if (selected) update(index, { key, operator: OPERATORS[selected.type][0], value: null });
          }} />
        <Select aria-label={`匹配方式 ${index + 1}`} placeholder="方式" disabled={!field} value={field ? condition.operator : undefined}
          options={operators.map(value => ({ label: OPERATOR_LABELS[value], value }))}
          onChange={operator => update(index, { operator })} />
        {field?.type === 'number' ? <InputNumber aria-label={valueLabel} className="!w-full" value={typeof condition.value === 'number' ? condition.value : null} onChange={value => update(index, { value })} />
        : field?.type === 'date' ? <DatePicker aria-label={valueLabel} className="w-full" value={condition.value ? dayjs(String(condition.value)) : null} onChange={value => update(index, { value: value?.format('YYYY-MM-DD') ?? null })} />
        : field?.options.length ? <Select aria-label={valueLabel} showSearch optionFilterProp="label" placeholder="选择值"
            options={field.options} value={condition.value ?? undefined} onChange={value => update(index, { value })} />
        : <Input aria-label={valueLabel} placeholder={field?.type === 'radio' || field?.type === 'select' ? '选项值' : '条件值'}
            disabled={!field} maxLength={200} value={condition.value ?? ''} onChange={event => update(index, { value: event.target.value })} />}
        <Tooltip title="移除条件"><Button className="justify-self-end" type="text" aria-label={`移除表单条件 ${index + 1}`} icon={<DeleteOutlined />}
          onClick={() => onChange({ ...filters, form_filters: conditions.filter((_, position) => position !== index) })} /></Tooltip>
      </div>;
    })}
    {filters.workflow_id && (loading || fields.length > 0) && <Button aria-label="添加表单条件" className="self-start" icon={<PlusOutlined />}
      disabled={loading || conditions.length >= 8}
      onClick={() => onChange({ ...filters, form_filters: [...conditions, { key: '', operator: 'eq', value: null }] })}>添加表单条件</Button>}
  </div>;
}
