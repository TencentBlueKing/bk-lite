'use client';
import { ItsmDrawer as Modal } from '@/app/itsm/components/interaction-surfaces';

import { Button, Form, Select, message } from 'antd';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import type { FormFieldSchema, FormSchema, WorkflowListItem } from '../types';
import { FormRenderer } from './form-renderer';

interface SubRow { ticket_id?: number; sn?: string; form_data: Record<string, unknown> }

export function SubProcessBinding({ value, onChange }: { value?: number; onChange: (value: number) => void }) {
  const api = useItsmApi();
  const [items, setItems] = useState<WorkflowListItem[]>([]);
  useEffect(() => {
    if (!api.ready) return;
    void api.listWorkflows().then((data) => setItems((data as { items: WorkflowListItem[] }).items.filter((item) => item.current_version_id))).catch(() => message.error('加载流程失败'));
  }, [api.ready, api.listWorkflows]);
  return <Select aria-label="绑定子流程" placeholder="选择已发布流程" value={value} options={items.map((item) => ({ label: item.name, value: item.current_version_id as number }))} onChange={onChange} />;
}

export function SubProcessField({ field, value = [], onChange, disabled = false }: {
  field: FormFieldSchema; value?: SubRow[]; onChange?: (value: SubRow[]) => void; disabled?: boolean;
}) {
  const api = useItsmApi();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const formValues = Form.useWatch([], form);
  const [schema, setSchema] = useState<FormSchema>({ version: 1, fields: [] });
  const [fieldPerm, setFieldPerm] = useState<Record<string, 'hidden' | 'read' | 'edit'>>({});
  const versionId = Number(field.props?.workflow_version_id || 0);
  const rows = Array.isArray(value) ? value : [];
  const add = async () => {
    try {
      const result = await api.ticketForm(versionId) as { schema: FormSchema; field_perm: typeof fieldPerm };
      setSchema(result.schema);
      setFieldPerm(result.field_perm);
      form.resetFields();
      setOpen(true);
    } catch { message.error('无法加载子流程表单'); }
  };
  return <div className="flex flex-col gap-2 rounded border border-[var(--color-border)] p-3">
    {rows.map((row, index) => <div key={row.ticket_id || index} className="flex items-center justify-between gap-2">
      {row.ticket_id ? <Link href={`/itsm/tickets/${row.ticket_id}`}>{row.sn} · {String(row.form_data?.title || '子单')}</Link> : <span>{String(row.form_data?.title || `子申请 ${index + 1}`)} · 待提交</span>}
      {!disabled && !row.ticket_id && <Button type="link" danger onClick={() => onChange?.(rows.filter((_, i) => i !== index))}>移除</Button>}
    </div>)}
    {!disabled && <Button disabled={!versionId || rows.length >= 20} onClick={() => { void add(); }}>新增子申请</Button>}
    {!versionId && <span className="text-xs text-[var(--color-text-3)]">请先在表单设计中绑定子流程</span>}
    <Modal formValue={formValues || {}} title="填写子申请" okText="添加子申请" open={open} onCancel={() => setOpen(false)} onOk={() => {
      return form.validateFields().then((values) => { onChange?.([...rows, { form_data: values }]); setOpen(false); }).catch(() => undefined);
    }}>
      <FormRenderer form={form} schema={schema} fieldPerm={fieldPerm} hideSubmit onSubmit={() => undefined} />
    </Modal>
  </div>;
}
