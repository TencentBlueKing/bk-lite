'use client';

import { Form, Button, Input, Select, Tabs, Tag, message } from 'antd';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/components/custom-table';
import ListPageHeader from '@/components/list-page-header';
import OperateModal from '@/components/operate-modal';
import Link from 'next/link';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../api/useItsmApi';
import { FieldRow } from '../components/field-row';
import { FormRenderer } from '../components/form-renderer';
import type { FormSchema, TicketListItem, WorkflowListItem } from '../types';

const STATUS_OPTIONS = [
  { value: 'new', labelKey: 'itsm.ticket.statusNew', color: 'processing' },
  { value: 'processing', labelKey: 'itsm.ticket.statusProcessing', color: 'warning' },
  { value: 'suspended', labelKey: 'itsm.ticket.statusSuspended', color: 'purple' },
  { value: 'finished', labelKey: 'itsm.ticket.statusFinished', color: 'success' },
  { value: 'terminated', labelKey: 'itsm.ticket.statusTerminated', color: 'error' },
  { value: 'cancelled', labelKey: 'itsm.ticket.statusCancelled', color: 'default' },
];

const statusOf = (value: string) => STATUS_OPTIONS.find((item) => item.value === value);

export default function TicketsPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const router = useRouter();
  const [form] = Form.useForm();
  const [schema, setSchema] = useState<FormSchema>({ version: 1, fields: [] });
  const [fieldPerm, setFieldPerm] = useState<Record<string, 'hidden' | 'read' | 'edit'>>({});
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [tab, setTab] = useState('all');
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState({ q: '', creator: '', priority: '', tag: '', status: '' });
  const [draft, setDraft] = useState({ creator: '', priority: '', tag: '', status: '' });
  const [open, setOpen] = useState(false);
  const [versionId, setVersionId] = useState<number | undefined>();

  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const ticketData = await api.listTickets({ ...query, page, page_size: 20, tab });
    setTotal((ticketData as { count?: number }).count || 0);
    setTickets((ticketData as { items?: TicketListItem[] }).items || []);
  }, [api.listTickets, query, page, tab]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => {
      message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed'));
    });
  }, [api.ready, load]);

  const createTicket = async () => {
    if (!versionId || !schema.fields.length) return;
    setBusy(true);
    try {
      const created = await api.createTicket({
        workflow_version_id: versionId,
        form_data: await form.validateFields(),
      }) as { id: number };
      setOpen(false);
      router.push(`/itsm/tickets/${created.id}`);
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return;
      message.error(error instanceof Error ? error.message : t('itsm.ticket.createFailed'));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { setPage(1); }, [query, tab]);
  useEffect(() => {
    if (!open) return;
    void api.listTicketWorkflows().then((data) => {
      const items = (data as { items: WorkflowListItem[] }).items;
      setWorkflows(items);
      setVersionId((current) => current || items[0]?.current_version_id || undefined);
    }).catch(() => message.error('加载可申请流程失败'));
  }, [open, api.listTicketWorkflows]);

  useEffect(() => {
    if (!open || !versionId) return;
    setSchema({ version: 1, fields: [] });
    void api.ticketForm(versionId).then((data) => {
      const result = data as { schema: FormSchema; field_perm: Record<string, 'hidden' | 'read' | 'edit'> };
      setSchema(result.schema);
      setFieldPerm(result.field_perm);
      form.resetFields();
    }).catch(() => message.error('加载提单表单失败'));
  }, [api.ticketForm, versionId, open, form]);

  return (
    <div className="flex flex-col">
      <ListPageHeader
        title={t('itsm.ticket.center')}
        actions={(
          <>
            <Input.Search
              allowClear
              className="w-60"
              placeholder={t('itsm.ticket.search')}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={(value) => setQuery((current) => ({ ...current, q: value.trim() }))}
            />
            <Button type="primary" onClick={() => setOpen(true)}>{t('itsm.ticket.submit')}</Button>
          </>
        )}
      />
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <Tabs
            className="min-w-0"
            activeKey={tab}
            onChange={setTab}
            items={[
              { key: 'all', label: t('itsm.ticket.all') },
              { key: 'mine', label: t('itsm.ticket.mine') },
            ]}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Select
              allowClear
              className="w-28"
              placeholder={t('itsm.ticket.status')}
              value={draft.status || undefined}
              options={STATUS_OPTIONS.map((item) => ({ value: item.value, label: t(item.labelKey) }))}
              onChange={(value) => setDraft((current) => ({ ...current, status: value || '' }))}
            />
            <Input className="w-28" placeholder={t('itsm.ticket.creator')} value={draft.creator} onChange={(event) => setDraft((current) => ({ ...current, creator: event.target.value }))} />
            <Input className="w-28" placeholder={t('itsm.ticket.priority')} value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: event.target.value }))} />
            <Input className="w-28" placeholder={t('itsm.ticket.tag')} value={draft.tag} onChange={(event) => setDraft((current) => ({ ...current, tag: event.target.value }))} />
            <Button onClick={() => setQuery((current) => ({ ...current, ...draft, creator: draft.creator.trim(), priority: draft.priority.trim(), tag: draft.tag.trim() }))}>{t('itsm.common.search')}</Button>
          </div>
        </div>
        <CustomTable
          rowKey="id"
          dataSource={tickets}
          pagination={{ current: page, pageSize: 20, total, showSizeChanger: false, onChange: setPage }}
          locale={{ emptyText: tab === 'mine' ? t('itsm.ticket.emptyMine') : t('itsm.ticket.emptyAll') }}
          columns={[
            {
              title: t('itsm.ticket.sn'),
              dataIndex: 'sn',
              key: 'sn',
              width: 160,
              render: (value: string, record: TicketListItem) => (
                <Link href={`/itsm/tickets/${record.id}`} className="text-[var(--color-primary)]">{value}</Link>
              ),
            },
            { title: t('itsm.ticket.title'), dataIndex: 'title', key: 'title', ellipsis: true },
            {
              title: t('itsm.ticket.status'),
              dataIndex: 'status',
              key: 'status',
              width: 100,
              render: (value: string) => {
                const status = statusOf(value);
                return <Tag color={status?.color}>{status ? t(status.labelKey) : value}</Tag>;
              },
            },
            { title: t('itsm.ticket.creator'), dataIndex: 'creator', key: 'creator', width: 120 },
            {
              title: t('itsm.ticket.node'),
              key: 'node',
              width: 180,
              render: (_value: unknown, record: TicketListItem) => record.tasks.map((task) => task.node_name || task.node_id).join('、') || '—',
            },
            {
              title: t('itsm.ticket.sla'),
              key: 'sla',
              width: 160,
              render: (_value: unknown, record: TicketListItem) => {
                if (!record.sla_due_at) {
                  return '—';
                }
                return record.sla_breached
                  ? <Tag color="error">{record.sla_due_at.replace('T', ' ').slice(5, 16)} {t('itsm.ticket.overdue')}</Tag>
                  : <span className="text-[var(--color-text-2)]">{record.sla_due_at.replace('T', ' ').slice(5, 16)}</span>;
              },
            },
            {
              title: t('itsm.ticket.action'),
              key: 'action',
              width: 80,
              render: (_value: unknown, record: TicketListItem) => (
                <Link href={`/itsm/tickets/${record.id}`} className="text-[var(--color-primary)]">{t('itsm.ticket.handle')}</Link>
              ),
            },
          ]}
        />
      </div>
      <OperateModal title={t('itsm.ticket.createTitle')} open={open} confirmLoading={busy} onCancel={() => setOpen(false)} onOk={() => { void createTicket(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.ticket.flow')}>
            <Select
              className="w-full"
              placeholder={workflows.length ? t('itsm.ticket.pickWorkflow') : t('itsm.ticket.noWorkflow')}
              value={versionId}
              options={workflows.map((item) => ({ value: item.current_version_id as number, label: item.name }))}
              onChange={setVersionId}
            />
          </FieldRow>
          <FormRenderer form={form} schema={schema} fieldPerm={fieldPerm} hideSubmit onSubmit={() => undefined} />
        </div>
      </OperateModal>
    </div>
  );
}
