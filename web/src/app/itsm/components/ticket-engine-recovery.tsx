'use client';

import { Alert, App, Button, Input } from 'antd';
import { useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { ticketActionLabel } from '../constants/node-catalog';
import type { TicketDetail } from '../types';
import { ItsmModal } from './interaction-surfaces';

export function TicketEngineRecovery({ ticket, refresh }: { ticket: TicketDetail; refresh: () => Promise<void> }) {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const start = ticket.start_recovery;
  const manual = ticket.manual_recovery;
  if (!start && !manual && !ticket.engine_pending) return null;

  const recover = async (confirmed = false) => {
    setBusy(true);
    try {
      if (start) {
        if (confirmed && !start.sent_at) return;
        await api.recoverStart(ticket.id, confirmed ? { id: start.id, action: 'confirmed_not_started', sent_at: start.sent_at!, reason: reason.trim() } : { id: start.id, action: 'check' });
      } else if (confirmed) {
        if (!manual?.token || !manual.sent_at) return;
        await api.recoverOperation(ticket.id, { decision: 'abandon', token: manual.token, sent_at: manual.sent_at, verified: true, reason: reason.trim() });
      } else {
        const result = await api.recoverOperation(ticket.id);
        if (result.status === 'pending') message.info('引擎尚未确认，已保留原提交，系统将继续核对。');
      }
      setOpen(false);
      await refresh();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '核对失败，请刷新后重试');
    } finally {
      setBusy(false);
    }
  };
  const action = start ? (start.kind === 'reopen' ? '重新打开' : '提单') : manual ? ticketActionLabel(manual.action) : '流程启动';
  return <>
    <Alert type="warning" showIcon message={`${action}结果待核对`} description="系统正在与流程引擎核对结果。核对完成后可继续处理这张工单。"
      action={<div className="flex flex-wrap gap-2">
        {(start || manual?.can_check) && <Button loading={busy} onClick={() => void recover()}>核对引擎结果</Button>}
        {(start?.can_confirm || manual?.can_abandon) && <Button danger disabled={busy} onClick={() => { setReason(''); setOpen(true); }}>{start ? '确认未启动并重发' : '确认操作未受理'}</Button>}
      </div>} />
    {(start?.can_confirm || manual?.can_abandon) && <ItsmModal title={start ? '确认流程未启动' : '确认操作未受理'} open={open} formValue={reason} onCancel={() => setOpen(false)}
      okText={start ? '重新发送启动请求' : '解除待核对状态'} okButtonProps={{ disabled: !reason.trim(), danger: true }} confirmLoading={busy}
      onOk={() => recover(true)}>
      {start ? <p>请用业务键 <code>{start.business_key}</code> 核对引擎历史与出站请求。确认没有对应实例，且原请求已结束后，再重新发送。</p> : <p>请核对原待办、引擎历史和出站请求。确认原请求已结束且引擎未受理后，可以解除待核对状态，返回工单重新操作。</p>}
      <label htmlFor="start-recovery-reason">核对依据</label>
      <Input.TextArea id="start-recovery-reason" rows={3} value={reason} maxLength={1000} onChange={e => setReason(e.target.value)} />
    </ItsmModal>}
  </>;
}
