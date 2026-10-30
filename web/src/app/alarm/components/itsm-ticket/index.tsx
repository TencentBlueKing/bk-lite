'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Descriptions, Input, Modal, Skeleton, Tag } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

interface Ticket {
  rule_id: number;
  rule_name: string;
  workflow_key: string;
  execution_id: number;
  execution_status: string;
  message: string;
  notification: string;
  ticket_id: string | null;
  ticket_number: string;
  ticket_title: string;
  status_label: string;
  last_synced_at: string | null;
  sync_error: string;
  is_closed?: boolean;
  comment_error?: string;
  close_result: string;
  close_error: string;
  allowed_actions: string[];
}
interface Preview { ticket_id: string; ticket_title: string; ticket_number: string; status_label: string }
interface Props { alertId: string; alertStatus?: string; readonly?: boolean }
const endpoint = '/alerts/api/action_execution/';

export default function ItsmTicket({ alertId, alertStatus, readonly = false }: Props) {
  const { get, post } = useApiClient();
  const { t } = useTranslation();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [modal, setModal] = useState<'retry' | 'reconcile' | null>(null);
  const [ticketId, setTicketId] = useState('');
  const [evidence, setEvidence] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const requestKey = useRef<string | null>(null);
  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    if (!alertId) return;
    const version = ++requestVersion.current;
    setLoading(true);
    try {
      const data = await get<Ticket | null>(endpoint + 'itsm_ticket/', { params: { alert_id: alertId } });
      if (version === requestVersion.current) { setTicket(data); setError(false); }
    } catch { if (version === requestVersion.current) setError(true); }
    finally { if (version === requestVersion.current) setLoading(false); }
  }, [alertId, get]);
  useEffect(() => {
    setTicket(null); setModal(null); requestKey.current = null;
    void load();
    return () => { requestVersion.current += 1; };
  }, [load]);
  const resendComment = async () => {
    setBusy(true);
    setSubmitError(false);
    try {
      await post(endpoint + 'itsm_recomment/', { alert_id: alertId }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
      await load();
    } catch {
      setSubmitError(true);
    } finally {
      setBusy(false);
    }
  };
  const submit = async () => {
    if (!ticket) return;
    setBusy(true);
    setSubmitError(false);
    try {
      if (modal === 'retry') {
        requestKey.current ||= crypto.randomUUID();
        await post(endpoint + 'manual_trigger/', { alert_id: alertId, rule_id: ticket.rule_id }, { headers: { 'Idempotency-Key': requestKey.current } });
        requestKey.current = null;
      } else {
        const result = await post<{ preview?: Preview }>(endpoint + 'itsm_reconcile/', {
          alert_id: alertId, execution_id: ticket.execution_id, ticket_id: ticketId, evidence, confirm: !!preview,
        });
        if (result.preview) { setPreview(result.preview); return; }
      }
      setModal(null);
      await load();
    } catch { setSubmitError(true); } finally { setBusy(false); }
  };
  return (
    <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]">
      <div className="flex items-center justify-between gap-2 bg-[var(--color-fill-1)] px-4 py-2.5">
        <h3 className="m-0 text-[13px] font-semibold">{t('itsm.title')}</h3>
        <Button size="small" onClick={() => void load()} loading={loading}>{t('common.refresh')}</Button>
      </div>
      <div className="p-4">
        {loading ? <Skeleton active paragraph={{ rows: 2 }} /> : error ? <Alert type="error" message={t('itsm.loadFailed')} /> : !ticket ? <span>{t('itsm.notLinked')}</span> : <>
          <Tag>{ticket.is_closed ? t('itsm.ticketClosed') : ticket.ticket_id ? ticket.status_label || t('itsm.awaitingSync') : t(`itsm.${ticket.execution_status}`)}</Tag>
          <Descriptions size="small" column={1} className="mt-3" items={[
            { key: 'rule', label: t('itsm.rule'), children: ticket.rule_name },
            ...(ticket.ticket_id ? [
              { key: 'title', label: t('itsm.ticketTitle'), children: ticket.ticket_title || '—' },
              { key: 'id', label: t('itsm.ticketId'), children: ticket.ticket_id },
              { key: 'number', label: t('itsm.number'), children: ticket.ticket_number || '—' },
              { key: 'sync', label: t('itsm.lastSync'), children: ticket.last_synced_at || '—' },
            ] : []),
          ]} />
          {!ticket.ticket_id && ticket.message && <Alert className="mt-3" type="info" message={ticket.message} />}
          {ticket.close_error && <Alert className="mt-3" type="error" message={ticket.close_error} />}
          {ticket.close_result && ticket.close_result !== 'unprocessed' && <p className="mt-2">{t('itsm.closeResult')}: {t(`itsm.close_${ticket.close_result}`)}</p>}
          {ticket.sync_error && <Alert className="mt-3" type="warning" message={ticket.sync_error} description={t('itsm.stale')} />}
          {ticket.comment_error && <Alert className="mt-3" type="error" message={ticket.comment_error} />}
          {ticket.notification && <p className="mt-2 text-[var(--color-text-3)]">{t('itsm.notification')}: {ticket.notification === 'queued' ? t('itsm.notificationQueued') : ticket.notification}</p>}
          {!readonly && <div className="mt-3 flex gap-2">
            {ticket.allowed_actions?.includes('recomment') && <Button onClick={() => void resendComment()}>{t('itsm.recomment')}</Button>}
            {ticket.allowed_actions?.includes('retry') && <Button onClick={() => setModal('retry')}>{t('itsm.retry')}</Button>}
            {ticket.allowed_actions?.includes('reconcile') && <Button onClick={() => { setModal('reconcile'); setPreview(null); setTicketId(''); setEvidence(''); }}>{t('itsm.reconcile')}</Button>}
          </div>}
        </>}
      </div>
      <Modal open={!!modal} title={t(modal === 'retry' ? 'itsm.retry' : 'itsm.reconcile')} onCancel={() => setModal(null)}
        onOk={() => void submit()} confirmLoading={busy} okText={t(modal === 'reconcile' && !preview ? 'itsm.lookup' : 'common.confirm')}
        okButtonProps={{ disabled: modal === 'reconcile' && (!ticketId.trim() || (!!preview && !evidence.trim())) }}>
        {submitError && <Alert type="error" message={t('itsm.submitFailed')} />}
        {modal === 'retry' ? <>
          <p>{t('itsm.retryHint')} {ticket?.workflow_key}</p>
          {alertStatus && !['unassigned', 'pending', 'processing'].includes(alertStatus) && <Alert type="warning" message={t('itsm.endedHint')} />}
        </> : <div className="flex flex-col gap-3">
          <Alert type="info" message={t('itsm.reconcileHint')} />
          <Input aria-label={t('itsm.ticketId')} placeholder={t('itsm.ticketId')} value={ticketId} maxLength={128} onChange={e => { setTicketId(e.target.value); setPreview(null); }} />
          {preview && <>
            <Descriptions column={1} items={[
              { key: 'title', label: t('itsm.ticketTitle'), children: preview.ticket_title },
              { key: 'number', label: t('itsm.number'), children: preview.ticket_number },
              { key: 'status', label: t('itsm.status'), children: preview.status_label },
            ]} />
            <Input.TextArea aria-label={t('itsm.evidence')} placeholder={t('itsm.evidence')} value={evidence} maxLength={500} onChange={e => setEvidence(e.target.value)} />
          </>}
        </div>}
      </Modal>
    </section>
  );
}
