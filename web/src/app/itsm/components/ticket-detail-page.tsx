'use client';

import { Alert, App, Form, Button, Empty, Input, Rate, Tag } from 'antd';
import { ItsmBackButton } from './back-button';
import { LeftOutlined, RightOutlined, ReloadOutlined, FileTextOutlined } from '@ant-design/icons';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { FormRenderer } from './form-renderer';
import { TicketHeaderSocial, TicketRelations } from './ticket-social';
import { TicketHistory } from './ticket-history';
import { TicketSla } from './ticket-sla';
import { TicketFlowBoard } from './ticket-flow-board';
import { TicketActions, type OperationInput } from './ticket-actions';
import { TicketCollaboration, formatTicketTime } from './ticket-collaboration';
import { useTranslation } from '@/utils/i18n';
import { useServiceDraft } from './use-service-draft';
import type { TicketDetail, TicketTaskItem } from '../types';

const STATUS_LABEL: Record<string, { id: string; color: string }> = {
  new: { id: 'itsm.ticket.statusNew', color: 'processing' },
  processing: { id: 'itsm.ticket.statusProcessing', color: 'warning' },
  suspended: { id: 'itsm.ticket.statusSuspended', color: 'purple' },
  finished: { id: 'itsm.ticket.statusFinished', color: 'success' },
  terminated: { id: 'itsm.ticket.statusTerminated', color: 'error' },
  cancelled: { id: 'itsm.ticket.statusCancelled', color: 'default' },
};

export default function TicketDetailPage({ serviceId }: { serviceId?: number }) {
  const params = useParams<{ id: string }>();
  const ticketId = Number(params.id);
  const { t } = useTranslation();
  const api = useItsmApi();
  const { message } = App.useApp();
  const [existingTicket, setTicket] = useState<TicketDetail | null>(null);
  const [form] = Form.useForm();
  const draft = useServiceDraft(serviceId, form);
  const ticket = serviceId ? draft.ticket : existingTicket;
  const [operationBusy, setBusy] = useState(false);
  const busy = operationBusy || draft.busy;
  const [logsOpen, setLogsOpen] = useState(true);
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState('');

  const load = useCallback(async () => {
    const data = await api.getTicket(ticketId) as TicketDetail;
    setTicket(data);
  }, [api.getTicket, ticketId]);

  useEffect(() => {
    if (ticket) form.setFieldsValue(ticket.form_data);
  }, [ticket, form]);

  useEffect(() => {
    if (!api.ready || !ticketId) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load, ticketId]);

  useEffect(() => {
    if (serviceId || !ticket || ['finished', 'cancelled', 'terminated', 'suspended'].includes(ticket.status)) return;
    const hasRunningStep = ticket.history?.some(item => item.action === 'auto' && item.state === 'current');
    if (ticket.tasks.length && !hasRunningStep) return;
    const timer = window.setInterval(() => { void load().catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [ticket, load, serviceId]);

  const operate = async (action: string, task?: TicketTaskItem, extra?: OperationInput) => {
    setBusy(true);
    try {
      await api.operateTicket(ticketId, {
        task_id: task?.id,
        action,
        target: extra?.target || '',
        opinion: extra?.opinion || '',
        return_node_id: extra?.return_node_id,
        form_data: ['submit', 'approve', 'reject', 'save'].includes(action) ? await form.validateFields() : undefined,
      });
      message.success(t('itsm.ticket.operateOk'));
      await load();
      return true;
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return false;
      message.error(error instanceof Error ? error.message : t('itsm.ticket.operateFailed'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const retryAuto = async (executionId: number) => {
    setBusy(true);
    try {
      await api.retryAutoNode(ticketId, executionId);
      message.success('已请求重试');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '请求重试失败');
    } finally {
      setBusy(false);
    }
  };

  if (serviceId && draft.error) return <Alert type="error" message={draft.error} action={<Button onClick={() => void draft.load()}>重试</Button>} />;

  if (!ticket) {
    return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-8 text-center text-sm text-[var(--color-text-3)]">{t('itsm.ticket.detailLoading')}</div>;
  }

  const status = STATUS_LABEL[ticket.status];

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">
      <header className="sticky top-0 z-20 shrink-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <ItsmBackButton href={serviceId ? "/itsm/portal" : "/itsm/tickets"} label={serviceId ? "返回服务门户" : "返回工单列表"} />
            <Tag color={status?.color || 'default'}>{serviceId ? '待提单' : status ? t(status.id) : ticket.status}</Tag>
            <span className="shrink-0 text-sm font-semibold text-[var(--color-text-2)]">{ticket.sn}</span>
            <h1 title={ticket.title} className="!m-0 truncate !text-sm !font-semibold text-[var(--color-text-1)]">{ticket.title}</h1>{!serviceId && <TicketHeaderSocial ticketId={ticketId} sn={ticket.sn} />}
          </div>
          <div className="flex flex-wrap items-center gap-2">{serviceId ? <><Button disabled={busy} onClick={() => void draft.save(false)}>保存草稿</Button><Button type="primary" loading={busy} onClick={() => void draft.save(true)}>提交申请</Button></> : <><Button type="text" icon={<ReloadOutlined />} disabled={busy} onClick={() => { void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : '刷新失败')); }}>刷新</Button><TicketActions ticket={ticket} busy={busy} operate={operate} /></>}</div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-3)]">
          <span>提单人：<span className="text-[var(--color-text-1)]">{ticket.creator}</span></span>
          {!serviceId && <span>提单时间：{formatTicketTime(ticket.created_at)}</span>}
          <span>流程：{ticket.workflow_name || '—'}</span>
          <span>当前节点：{ticket.nodes.filter((node) => node.state === 'current' || node.state === 'failed').map((node) => node.name).join('、') || '—'}</span>
          <span>当前处理人：{serviceId ? ticket.creator : Array.from(new Set(ticket.tasks.map((task) => task.assignee).filter(Boolean))).join('、') || '—'}</span>
        </div>
      </header>

      {ticket.nodes.length ? <div className="shrink-0"><TicketFlowBoard nodes={ticket.nodes} edges={ticket.edges || []} /></div> : null}

      <div className={`grid min-h-0 flex-1 grid-cols-1 gap-0 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] ${logsOpen ? 'grid-rows-2 xl:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_400px]' : 'grid-rows-[minmax(0,1fr)_48px] xl:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_48px]'}`}>
        <div role="region" aria-label="工单表单" tabIndex={0} className="h-full min-h-0 min-w-0 overflow-y-auto overscroll-contain p-5">
          <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">{t('itsm.ticket.form')}</div>
          <div className="mb-3 flex flex-wrap gap-3 text-xs text-[var(--color-text-3)]">{ticket.sla?.map((item) => <span key={item.target}>{item.target === 'response' ? '响应期限' : '解决期限'}：{formatTicketTime(item.due_at)}{item.paused ? ' · 已暂停' : item.breached ? ' · 已超时' : item.finished_at ? ' · 已达标' : ''}</span>)}</div>
          <FormRenderer fetchContext={serviceId ? { service_id: serviceId } : { ticket_id: ticketId }} form={form} schema={{ version: 1, fields: ticket.fields }} initialValues={ticket.form_data} fieldPerm={serviceId ? draft.fieldPerm : ticket.tasks.find((task) => task.can_operate)?.field_perm} readOnly={!serviceId && !ticket.tasks.some((task) => task.can_operate)} hideSubmit onSubmit={() => undefined} />
        </div>

        <aside aria-label="工单协作" className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-l border-[var(--color-border)]">
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
            {logsOpen ? <span className="flex items-center gap-2 text-sm font-medium"><FileTextOutlined />工单协作</span> : null}
            <Button size="small" type="text" aria-label={logsOpen ? '收起协作侧栏' : '展开协作侧栏'} icon={logsOpen ? <RightOutlined /> : <LeftOutlined />} onClick={() => setLogsOpen(!logsOpen)} />
          </div>
          <div className={`${logsOpen ? '' : 'hidden'} min-h-0 flex-1 overflow-hidden px-4 pb-4`}>
        <>{serviceId ? <Empty className="mt-10" image={Empty.PRESENTED_IMAGE_SIMPLE} description="提交后可查看流转记录、评论和附件" /> : <TicketCollaboration ticketId={ticketId} historyFirst extraTabs={[
          { key: 'history', label: '流转日志', children: <>
            {ticket.history?.length ? (
              <TicketHistory items={ticket.history} nodes={ticket.nodes} retry={retryAuto} busy={busy} />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noLogs')} />}

          </> },
          { key: 'survey', label: '满意度', children: ticket.survey ? <div className="flex flex-col gap-3 py-3"><Rate disabled value={ticket.survey.score} /><p>{ticket.survey.comment || '已完成评价'}</p></div> : ticket.can_survey ? <div className="flex max-w-xl flex-col items-start gap-3 py-3">
              <Rate aria-label="满意度评分" value={score} allowClear={false} onChange={setScore} />
              <Input.TextArea aria-label="评价内容" placeholder="请填写评价意见（选填）" value={comment} maxLength={500} onChange={(event) => setComment(event.target.value)} rows={3} />
              <Button type="primary" loading={busy} onClick={() => { setBusy(true); void api.submitSurvey(ticketId, { score, comment }).then(() => load()).catch((error: unknown) => message.error(error instanceof Error ? error.message : '评价失败')).finally(() => setBusy(false)); }}>提交评价</Button>
            </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="工单完成后由提单人评价" /> },
          { key: 'relations', label: '关联单', children: <TicketRelations ticketId={ticketId} /> },
          ...(ticket.sla?.length ? [{ key: 'sla', label: 'SLA', children: <TicketSla records={ticket.sla} /> }] : []),
        ]}
        />}</>
          </div>
        </aside>
      </div>


    </div>
  );
}
