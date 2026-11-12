'use client';

import { Button, Dropdown, Empty, Input, Tabs, Tag, Timeline, Upload, message } from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../../api/useItsmApi';
import { FormRenderer } from '../../components/form-renderer';
import { TicketFlowBoard } from '../../components/ticket-flow-board';
import { UserSelector } from '../../components/user-selector';
import { useTranslation } from '@/utils/i18n';
import type { TicketDetail, TicketTaskItem } from '../../types';
import { actionOf } from '../actions';

const STATUS_LABEL: Record<string, { id: string; color: string }> = {
  new: { id: 'itsm.ticket.statusNew', color: 'processing' },
  processing: { id: 'itsm.ticket.statusProcessing', color: 'warning' },
  suspended: { id: 'itsm.ticket.statusSuspended', color: 'purple' },
  finished: { id: 'itsm.ticket.statusFinished', color: 'success' },
  terminated: { id: 'itsm.ticket.statusTerminated', color: 'error' },
  cancelled: { id: 'itsm.ticket.statusCancelled', color: 'default' },
};

export default function TicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticketId = Number(params.id);
  const { t } = useTranslation();
  const api = useItsmApi();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<string[]>([]);
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState('');
  const [note, setNote] = useState('');
  const [notes, setNotes] = useState<Array<{ id: number; operator: string; content: string }>>([]);
  const [files, setFiles] = useState<Array<{ id: number; name: string }>>([]);
  const [followers, setFollowers] = useState<string[]>([]);
  const [following, setFollowing] = useState(false);
  const [tags, setTags] = useState<Array<{ id: number; name: string }>>([]);
  const [tagName, setTagName] = useState('');
  const [relations, setRelations] = useState<Array<{ id: number; related_id: number; related_sn: string }>>([]);
  const [relatedId, setRelatedId] = useState('');

  const loadCollaboration = useCallback(async () => {
    const [commentData, fileData, followData, tagData, relationData] = await Promise.all([
      api.listComments(ticketId) as Promise<{ items?: Array<{ id: number; operator: string; content: string }> }>,
      api.listAttachments(ticketId) as Promise<{ items?: Array<{ id: number; name: string }> }>,
      api.listFollowers(ticketId) as Promise<{ items?: string[]; following?: boolean }>,
      api.listTags(ticketId) as Promise<{ items?: Array<{ id: number; name: string }> }>,
      api.listRelations(ticketId) as Promise<{ items?: Array<{ id: number; related_id: number; related_sn: string }> }>,
    ]);
    setNotes(commentData.items || []);
    setFiles(fileData.items || []);
    setFollowers(followData.items || []);
    setFollowing(Boolean(followData.following));
    setTags(tagData.items || []);
    setRelations(relationData.items || []);
  }, [api.listAttachments, api.listComments, api.listFollowers, api.listRelations, api.listTags, ticketId]);

  const load = useCallback(async () => {
    const data = await api.getTicket(ticketId) as TicketDetail;
    setTicket(data);
  }, [api.getTicket, ticketId]);

  useEffect(() => {
    if (!api.ready || !ticketId) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
    void loadCollaboration().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.rule.collabFailed')));
  }, [api.ready, load, loadCollaboration, ticketId]);

  const operate = async (action: string, task?: TicketTaskItem, extra?: { return_mode?: string }) => {
    setBusy(true);
    try {
      await api.operateTicket(ticketId, {
        task_id: task?.id,
        action,
        target: target[0] || '',
        opinion: action,
        return_mode: extra?.return_mode,
      });
      message.success(t('itsm.ticket.operateOk'));
      setTarget([]);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.ticket.operateFailed'));
    } finally {
      setBusy(false);
    }
  };

  if (!ticket) {
    return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-8 text-center text-sm text-[var(--color-text-3)]">{t('itsm.ticket.detailLoading')}</div>;
  }

  const status = STATUS_LABEL[ticket.status];
  const closed = ticket.status === 'finished' || ticket.status === 'cancelled' || ticket.status === 'terminated';
  const moreItems = [
    ticket.status === 'suspended'
      ? { key: 'resume', label: t('itsm.ticket.resume'), onClick: () => { void operate('resume'); } }
      : !closed ? { key: 'suspend', label: t('itsm.ticket.suspend'), onClick: () => { void operate('suspend'); } } : null,
    !closed ? { key: 'withdraw', label: t('itsm.ticket.withdraw'), onClick: () => { void operate('withdraw'); } } : null,
    ticket.status === 'new' ? { key: 'respond', label: t('itsm.ticket.respond'), onClick: () => { void operate('respond'); } } : null,
    ticket.tasks.length ? { key: 'urge', label: t('itsm.ticket.urge'), onClick: () => { void operate('urge'); } } : null,
    !closed ? { key: 'terminate', label: t('itsm.ticket.terminate'), onClick: () => { void operate('terminate'); } } : null,
    !closed ? { key: 'close', label: t('itsm.ticket.close'), onClick: () => { void operate('close'); } } : null,
    closed ? { key: 'reopen', label: t('itsm.ticket.reopen'), onClick: () => { void operate('reopen'); } } : null,
  ].filter((item): item is { key: string; label: string; onClick: () => void } => Boolean(item));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link href="/itsm/tickets" className="shrink-0 text-sm text-[var(--color-primary)]">{t('itsm.common.back')}</Link>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold leading-tight text-[var(--color-text-1)]">{ticket.title}</div>
            <div className="mt-1 text-xs text-[var(--color-text-3)]">{ticket.sn} · {ticket.creator}</div>
          </div>
        </div>
        <Tag color={status?.color || 'default'}>{status ? t(status.id) : ticket.status}</Tag>
      </div>

      {ticket.nodes.length ? <TicketFlowBoard nodes={ticket.nodes} edges={ticket.edges || []} /> : null}

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
          <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">{t('itsm.ticket.form')}</div>
          <FormRenderer schema={{ version: 1, fields: ticket.fields }} initialValues={ticket.form_data} readOnly onSubmit={() => undefined} />
        </div>

        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.ticket.process')}</span>
              {moreItems.length ? <Dropdown menu={{ items: moreItems }}><Button size="small">{t('itsm.common.more')}</Button></Dropdown> : null}
            </div>
            {(ticket.sla || []).map((item) => (
              <div key={item.target} className="mb-2 text-xs text-[var(--color-text-3)]">
                {item.target === 'response' ? t('itsm.ticket.responseDue') : t('itsm.ticket.resolveDue')} {item.due_at.replace('T', ' ').slice(5, 16)}
                {item.paused ? ` · ${t('itsm.ticket.paused')}` : ''}
                {item.finished_at ? ` · ${item.breached ? t('itsm.ticket.overdue') : t('itsm.ticket.met')}` : ''}
              </div>
            ))}
            {ticket.tasks.length ? ticket.tasks.map((task) => (
              <div key={task.id} className="mb-3 flex flex-col gap-2 border-t border-[var(--color-border)] pt-3 first:border-0 first:pt-0">
                <div className="text-xs text-[var(--color-text-2)]">{task.node_name || task.node_id} · {task.assignee || t('itsm.ticket.unassigned')}</div>
                <div className="flex flex-wrap gap-2">
                  {task.status === 'pending' ? <Button size="small" loading={busy} onClick={() => { void operate('claim', task); }}>{t('itsm.ticket.claim')}</Button> : null}
                  <Button size="small" type="primary" loading={busy} onClick={() => { void operate(actionOf(task.node_id), task); }}>{actionOf(task.node_id) === 'approve' ? t('itsm.ticket.pass') : t('itsm.ticket.submitAction')}</Button>
                  {task.node_id.includes('approve') ? <Button size="small" danger loading={busy} onClick={() => { void operate('reject', task); }}>{t('itsm.ticket.reject')}</Button> : null}
                </div>
                {task.node_id !== 'submit' ? (
                  <div className="flex flex-wrap gap-2">
                    <Button size="small" loading={busy} onClick={() => { void operate('return', task, { return_mode: 'submit' }); }}>{t('itsm.ticket.returnSubmit')}</Button>
                    <Button size="small" loading={busy} onClick={() => { void operate('return', task, { return_mode: 'previous' }); }}>{t('itsm.ticket.returnPrevious')}</Button>
                  </div>
                ) : null}
              </div>
            )) : closed && !ticket.survey ? (
              <div className="flex flex-col gap-2">
                <Input className="w-24" value={String(score)} onChange={(event) => setScore(Number(event.target.value) || 1)} />
                <Input placeholder={t('itsm.ticket.commentPlaceholder')} value={comment} onChange={(event) => setComment(event.target.value)} />
                <Button type="primary" size="small" loading={busy} onClick={() => {
                  setBusy(true);
                  void api.submitSurvey(ticketId, { score, comment }).then(() => load()).catch((error: unknown) => {
                    message.error(error instanceof Error ? error.message : t('itsm.ticket.surveyFailed'));
                  }).finally(() => setBusy(false));
                }}>{t('itsm.ticket.submitSurvey')}</Button>
              </div>
            ) : ticket.survey ? (
              <div className="text-xs text-[var(--color-text-2)]">{t('itsm.ticket.score', undefined, { score: String(ticket.survey.score), comment: ticket.survey.comment })}</div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noTask')} />
            )}
            {ticket.tasks.length ? (
              <div className="mt-3 flex flex-col gap-2">
                <UserSelector multiple={false} placeholder={t('itsm.ticket.transferTo')} value={target} onChange={setTarget} />
                <Button size="small" disabled={!target[0]} loading={busy} onClick={() => { void operate('transfer', ticket.tasks[0]); }}>{t('itsm.ticket.transfer')}</Button>
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
            <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">{t('itsm.ticket.logs')}</div>
            {ticket.logs.length ? (
              <Timeline
                items={ticket.logs.map((item, index) => ({
                  key: `${item.action}-${index}`,
                  children: (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs font-medium text-[var(--color-text-1)]">{item.operator} · {item.action}</span>
                      {item.message ? <span className="text-xs text-[var(--color-text-3)]">{item.message}</span> : null}
                    </div>
                  ),
                }))}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noLogs')} />}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 pb-4">
        <Tabs
          items={[
            {
              key: 'comments',
              label: notes.length ? `${t('itsm.ticket.comments')} ${notes.length}` : t('itsm.ticket.comments'),
              children: (
                <div className="flex flex-col gap-3">
                  {notes.length ? notes.map((item) => (
                    <div key={item.id} className="rounded border border-[var(--color-border)] px-3 py-2 text-sm">
                      <div className="text-xs text-[var(--color-text-3)]">{item.operator}</div>
                      <div className="mt-1 text-[var(--color-text-1)]">{item.content}</div>
                    </div>
                  )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noComments')} />}
                  <div className="flex gap-2">
                    <Input value={note} placeholder={t('itsm.ticket.writeComment')} onChange={(event) => setNote(event.target.value)} />
                    <Button type="primary" onClick={() => {
                      if (!note.trim()) return;
                      void api.addComment(ticketId, note.trim()).then(() => { setNote(''); return loadCollaboration(); }).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.commentFailed')));
                    }}>{t('itsm.ticket.publish')}</Button>
                  </div>
                </div>
              ),
            },
            {
              key: 'files',
              label: t('itsm.ticket.files'),
              children: (
                <div className="flex flex-col gap-2">
                  {files.length ? files.map((item) => <div key={item.id} className="text-sm text-[var(--color-text-1)]">{item.name}</div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noFiles')} />}
                  <Upload customRequest={async (options) => {
                    const file = options.file as File;
                    try {
                      const signed = await api.presignAttachment(file.name) as { url: string; object_name: string };
                      const response = await fetch(signed.url, { method: 'PUT', body: file });
                      if (!response.ok) throw new Error(t('itsm.ticket.uploadFailed'));
                      await api.addAttachment(ticketId, { object_name: signed.object_name, name: file.name, size: file.size });
                      await loadCollaboration();
                      options.onSuccess?.({});
                    } catch (error) {
                      message.error(error instanceof Error ? error.message : t('itsm.ticket.uploadFailed'));
                      options.onError?.(error as Error);
                    }
                  }}>
                    <Button>{t('itsm.ticket.upload')}</Button>
                  </Upload>
                </div>
              ),
            },
            {
              key: 'people',
              label: t('itsm.ticket.people'),
              children: (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2 text-sm text-[var(--color-text-2)]">
                    <span>{t('itsm.ticket.followers', undefined, { names: followers.join('、') || t('itsm.ticket.noFollowers') })}</span>
                    <Button size="small" onClick={() => { void api.toggleFollow(ticketId).then(() => loadCollaboration()).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.followFailed'))); }}>{following ? t('itsm.ticket.unfollow') : t('itsm.ticket.follow')}</Button>
                  </div>
                  <div className="flex flex-wrap gap-2">{tags.map((item) => <Tag key={item.id}>{item.name}</Tag>)}</div>
                  <div className="flex gap-2">
                    <Input className="w-40" value={tagName} placeholder={t('itsm.ticket.tagName')} onChange={(event) => setTagName(event.target.value)} />
                    <Button onClick={() => {
                      if (!tagName.trim()) return;
                      void api.addTag(ticketId, tagName.trim()).then(() => { setTagName(''); return loadCollaboration(); }).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.tagFailed')));
                    }}>{t('itsm.ticket.addTag')}</Button>
                  </div>
                </div>
              ),
            },
            {
              key: 'relations',
              label: t('itsm.ticket.relations'),
              children: (
                <div className="flex flex-col gap-2">
                  {relations.length ? relations.map((item) => (
                    <Link key={item.id} href={`/itsm/tickets/${item.related_id}`} className="text-sm text-[var(--color-primary)]">{item.related_sn}</Link>
                  )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noRelations')} />}
                  <div className="flex gap-2">
                    <Input className="w-40" value={relatedId} placeholder={t('itsm.ticket.relatedId')} onChange={(event) => setRelatedId(event.target.value)} />
                    <Button onClick={() => {
                      const related = Number(relatedId);
                      if (!related) return;
                      void api.addRelation(ticketId, related).then(() => { setRelatedId(''); return loadCollaboration(); }).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.relateFailed')));
                    }}>{t('itsm.ticket.relate')}</Button>
                  </div>
                </div>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
