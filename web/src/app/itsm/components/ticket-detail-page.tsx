'use client';

import { Alert, App, Form, Button, Empty, Tag } from 'antd';
import { EditableDesignerName } from './editable-designer-name';
import { ItsmBackButton } from './back-button';
import { TICKET_LIST_RETURN } from './ticket-list-view';
import { LeftOutlined, RightOutlined, ReloadOutlined, FileTextOutlined, PrinterOutlined } from '@ant-design/icons';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { FormRenderer } from './form-renderer';
import { TicketHeaderSocial, TicketRelations } from './ticket-social';
import { TicketHistory } from './ticket-history';
import { useItsmRuntimeSettings } from '../settings/runtime-settings';
import { TicketSla } from './ticket-sla';
import { TicketTriggerRecords } from './ticket-trigger-records';
import { TicketSurveyPanel } from './ticket-survey';
import { TicketFlowBoard } from './ticket-flow-board';
import { TicketEngineRecovery } from './ticket-engine-recovery';
import { TicketActions, type OperationInput } from './ticket-actions';
import { TicketCollaboration, formatTicketTime } from './ticket-collaboration';
import { useTranslation } from '@/utils/i18n';
import { useServiceDraft } from './use-service-draft';
import type { AutoExecutionReview, TicketDetail, TicketTaskItem } from '../types';

const STATUS_LABEL: Record<string, { id: string; color: string }> = {
  new: { id: 'itsm.ticket.statusNew', color: 'processing' },
  processing: { id: 'itsm.ticket.statusProcessing', color: 'warning' },
  suspended: { id: 'itsm.ticket.statusSuspended', color: 'purple' },
  finished: { id: 'itsm.ticket.statusFinished', color: 'success' },
  terminated: { id: 'itsm.ticket.statusTerminated', color: 'error' },
  cancelled: { id: 'itsm.ticket.statusCancelled', color: 'default' },
};

export default function TicketDetailPage({ serviceId, fromTicketCenter }: { serviceId?: number; fromTicketCenter?: boolean }) {
  const params = useParams<{ id: string }>();
  const ticketId = Number(params.id);
  return <TicketContent key={serviceId ? `service-${serviceId}` : ticketId} ticketId={ticketId} serviceId={serviceId} fromTicketCenter={fromTicketCenter} />;
}

function TicketContent({ ticketId, serviceId, fromTicketCenter }: { ticketId: number; serviceId?: number; fromTicketCenter?: boolean }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { settings } = useItsmRuntimeSettings();
  const api = useItsmApi();
  const { message } = App.useApp();
  const [existingTicket, setTicket] = useState<TicketDetail | null>(null);
  const [triggerLogRevision, setTriggerLogRevision] = useState(0);
  const [form] = Form.useForm();
  const draftTitle = Form.useWatch('title', form);
  const draft = useServiceDraft(serviceId, form, fromTicketCenter);
  const ticket = serviceId ? draft.ticket : existingTicket;
  const [operationBusy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const busy = operationBusy || draft.busy || loading;
  const [logsOpen, setLogsOpen] = useState(true);

  const sequence = useRef(0);
  const selectedTaskId = useRef<number>(undefined);
  const load = useCallback(async (taskId = selectedTaskId.current, background = false) => {
    const request = ++sequence.current;
    if (!background) setLoading(true);
    setLoadError(undefined);
    try {
      const data = await api.getTicket(ticketId, taskId) as TicketDetail;
      if (request !== sequence.current) return;
      selectedTaskId.current = data.tasks.find(task => task.can_operate && task.id === data.selected_task_id)?.id;
      setTicket(data);
      setTriggerLogRevision(revision => revision + 1);
    } catch (cause) {
      if (request !== sequence.current || background) return;
      const status = (cause as { status?: number })?.status;
      const unavailable = status === 403 || status === 404;
      setTicket(null);
      setLoadError(unavailable ? '工单不存在或当前账号没有访问权限' : cause instanceof Error ? cause.message : '加载工单失败');
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [api.getTicket, ticketId]);

  const formData = ticket?.form_data;
  useEffect(() => {
    if (formData) {
      form.resetFields();
      form.setFieldsValue(formData);
    }
  }, [formData, form]);

  useEffect(() => {
    if (api.ready && ticketId && !serviceId) void load();
    return () => { sequence.current++; };
  }, [api.ready, load, ticketId, serviceId]);

  useEffect(() => {
    if (busy || serviceId || !ticket) return;
    const recovering = ticket.engine_pending || ticket.manual_recovery || ticket.start_recovery;
    if (!recovering && ['finished', 'cancelled', 'terminated', 'suspended'].includes(ticket.status)) return;
    const hasRunningStep = ticket.history?.some(item => item.executing || (item.action === 'auto' && item.state === 'current'));
    if (!recovering && ticket.tasks.length && !hasRunningStep) return;
    const timer = window.setInterval(() => { void load(undefined, true); }, 5000);
    return () => window.clearInterval(timer);
  }, [ticket, load, serviceId, busy]);

  const operate = async (action: string, task?: TicketTaskItem, extra?: OperationInput) => {
    setBusy(true);
    try {
      await api.operateTicket(ticketId, {
        task_id: task?.id,
        action,
        reopen_from: action === 'reopen' ? ticket?.reopen_from ?? undefined : undefined,
        target: extra?.target || '',
        opinion: extra?.opinion || '',
        return_node_id: extra?.return_node_id,
        form_data: ['submit', 'approve', 'reject', 'save'].includes(action) ? await form.validateFields() : undefined,
      });
      message.success(t('itsm.ticket.operateOk'));
      if (!['claim', 'save'].includes(action)) selectedTaskId.current = undefined;
      await load();
      return true;
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return false;
      message.error(error instanceof Error ? error.message : t('itsm.ticket.operateFailed'));
      if ([409, 502, 503, 504].includes((error as { status?: number })?.status ?? 0)) {
        selectedTaskId.current = undefined;
        await load(undefined, true);
      }
      return false;
    } finally {
      setBusy(false);
    }
  };

  const reconcileAuto = async (executionId: number, review: AutoExecutionReview) => {
    await api.reconcileAutoNode(ticketId, executionId, review);
    message.success('已记录核对结果');
    await load();
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

  if (loadError && !serviceId) return <Alert type="error" message={loadError} action={<div className="flex gap-2">
    <ItsmBackButton href={fromTicketCenter ? TICKET_LIST_RETURN : '/itsm/tickets'} label="返回工单列表" />
    <Button onClick={() => { selectedTaskId.current = undefined; void load(); }}>重试</Button>
  </div>} />;

  if (!ticket) {
    return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-8 text-center text-sm text-[var(--color-text-3)]">{t('itsm.ticket.detailLoading')}</div>;
  }

  const selectedTask = ticket.tasks.find(task => task.id === ticket.selected_task_id && task.can_operate);
  const titleField = serviceId && ticket.fields.find(field => field.key === 'title' && field.type === 'input');
  const draftTitleEditable = titleField && (!titleField.state || titleField.state === 'default')
    && !titleField.fetch && !titleField.visibleWhen && !ticket.form_rules?.some(rule => rule.field === 'title' && rule.type !== 'required')
    && ['edit', 'editable', 'required'].includes(draft.fieldPerm.title || draft.fieldPerm['*'] || 'edit');
  const status = STATUS_LABEL[ticket.status];
  const backToPortal = serviceId && !fromTicketCenter;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">
      <header className="sticky top-0 z-20 shrink-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <ItsmBackButton href={backToPortal ? "/itsm/portal" : fromTicketCenter ? TICKET_LIST_RETURN : "/itsm/tickets"} label={t(backToPortal ? "itsm.ticket.backToPortal" : "itsm.ticket.backToList")} />
            <Tag color={status?.color || 'default'}>{serviceId ? '待提单' : status ? t(status.id) : ticket.status}</Tag>
            <span className="shrink-0 text-sm font-semibold text-[var(--color-text-2)]">{ticket.sn}</span>
            {(serviceId ? draftTitleEditable : ticket.can_rename) ? (
              <EditableDesignerName name={serviceId ? (typeof draftTitle === 'string' ? draftTitle : '') : ticket.title}
                fallback={ticket.title} label="工单标题" maxLength={200} disabled={busy}
                onSave={async title => {
                  if (serviceId) {
                    form.setFieldValue('title', title);
                  } else {
                    await api.renameTicket(ticketId, title);
                    setTicket(current => current && { ...current, title });
                  }
                }} />
            ) : <h1 title={ticket.title} className="!m-0 truncate !text-sm !font-semibold text-[var(--color-text-1)]">{ticket.title}</h1>}
            {!serviceId && <TicketHeaderSocial ticketId={ticketId} sn={ticket.sn} />}
          </div>
          <div className="flex flex-wrap items-center gap-2">{serviceId ? <><Button disabled={busy} onClick={() => void draft.save(false)}>保存草稿</Button><Button type="primary" loading={busy} onClick={() => void draft.save(true)}>提交申请</Button></> : <><Button type="text" icon={<ReloadOutlined />} disabled={busy} onClick={() => { void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : '刷新失败')); }}>刷新</Button><Button type="text" icon={<PrinterOutlined />} onClick={() => router.push(`/itsm/tickets/${ticketId}/print${fromTicketCenter ? "?from=tickets" : ""}`)}>{t("itsm.print.action")}</Button><TicketActions ticket={ticket} busy={busy || Boolean(ticket.engine_pending || ticket.manual_recovery || ticket.start_recovery)} operate={operate} onTaskChange={taskId => void load(taskId)} /></>}</div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-3)]">
          <span>提单人：<span className="text-[var(--color-text-1)]">{ticket.creator}</span></span>
          {!serviceId && <span>提单时间：{formatTicketTime(ticket.created_at)}</span>}
          <span>流程：{ticket.workflow_name || '—'}</span>
          <span>当前节点：{ticket.nodes.filter((node) => node.state === 'current' || node.state === 'failed').map((node) => node.name).join('、') || Array.from(new Set(ticket.tasks.map(task => task.node_name).filter(Boolean))).join('、') || '—'}</span>
          {selectedTask && !ticket.nodes.some(node => node.id === selectedTask.node_id && node.state === 'current') && <span>当前待办：{selectedTask.node_name}</span>}
          <span>当前处理人：{serviceId ? ticket.creator : Array.from(new Set(ticket.tasks.map((task) => task.assignee).filter(Boolean))).join('、') || '—'}</span>
        </div>
      </header>

      {!serviceId && (ticket.engine_pending || ticket.manual_recovery || ticket.start_recovery) && <TicketEngineRecovery
        key={ticket.start_recovery ? `${ticket.start_recovery.id}-${ticket.start_recovery.sent_at}` : ticket.manual_recovery?.token || 'operation'}
        ticket={ticket} refresh={() => { selectedTaskId.current = undefined; return load(); }} />}
      {ticket.nodes.length ? <div className="shrink-0"><TicketFlowBoard nodes={ticket.nodes} edges={ticket.edges || []} /></div> : null}

      <div className={`grid min-h-0 flex-1 grid-cols-1 gap-0 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] ${logsOpen ? 'grid-rows-2 xl:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_400px]' : 'grid-rows-[minmax(0,1fr)_48px] xl:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_48px]'}`}>
        <div role="region" aria-label="工单表单" tabIndex={0} className="h-full min-h-0 min-w-0 overflow-y-auto overscroll-contain p-5">
          <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">{t('itsm.ticket.form')}</div>
          <div className="mb-3 flex flex-wrap gap-3 text-xs text-[var(--color-text-3)]">{ticket.sla?.map((item) => <span key={item.target}>{item.target === 'response' ? '响应期限' : '解决期限'}：{formatTicketTime(item.due_at)}{item.paused ? ' · 已暂停' : item.breached ? ' · 已超时' : item.finished_at ? ' · 已达标' : ''}</span>)}</div>
          <FormRenderer fetchContext={serviceId ? { service_id: serviceId } : { ticket_id: ticketId, task_id: selectedTask?.id }} form={form} schema={{ version: 1, fields: ticket.fields, rules: ticket.form_rules }} initialValues={ticket.form_data} fieldPerm={serviceId ? draft.fieldPerm : selectedTask?.field_perm} readOnly={!serviceId && (!selectedTask || loading)} hideSubmit onSubmit={() => undefined} />
        </div>

        <aside aria-label="工单协作" className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-l border-[var(--color-border)]">
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
            {logsOpen ? <span className="flex items-center gap-2 text-sm font-medium"><FileTextOutlined />工单协作</span> : null}
            <Button size="small" type="text" aria-label={logsOpen ? '收起协作侧栏' : '展开协作侧栏'} icon={logsOpen ? <RightOutlined /> : <LeftOutlined />} onClick={() => setLogsOpen(!logsOpen)} />
          </div>
          <div className={`${logsOpen ? '' : 'hidden'} min-h-0 flex-1 overflow-hidden px-4 pb-4`}>
        <>{serviceId ? <Empty className="mt-10" image={Empty.PRESENTED_IMAGE_SIMPLE} description="提交后可查看流转记录、评论和附件" /> : <TicketCollaboration ticketId={ticketId} historyFirst extraTabs={[
          ...(settings.show_process_log ? [{ key: 'history', label: '流转日志', children: <>
            {ticket.history?.length ? (
              <TicketHistory items={ticket.history} nodes={ticket.nodes} retry={retryAuto} reconcile={reconcileAuto} busy={busy} />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noLogs')} />}

          </> }] : []),
          { key: 'survey', label: '满意度', children: <TicketSurveyPanel key={ticketId} result={ticket.survey} template={ticket.survey_template}
            canSurvey={Boolean(ticket.can_survey)} onSubmit={async answers => {
              await api.submitSurvey(ticketId, answers);
              await load();
            }} /> },
          { key: 'relations', label: '关联单', children: <TicketRelations ticketId={ticketId} /> },
          { key: 'triggers', label: t('itsm.rule.trigger'), destroyOnHidden: true,
            children: <TicketTriggerRecords key={ticketId} ticketId={ticketId} refreshKey={triggerLogRevision} /> },
          ...(ticket.sla?.length ? [{ key: 'sla', label: 'SLA', children: <TicketSla records={ticket.sla} /> }] : []),
        ]}
        />}</>
          </div>
        </aside>
      </div>


    </div>
  );
}
