'use client';

import { Fragment, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Dialog, Popup, Tabs, Toast } from 'antd-mobile';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import MobilePageHeader from '@/components/mobile-page-header';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MobileSearchBar from '@/components/mobile-search-bar';
import { useAuth } from '@/context/auth';
import { useMobileAvailability } from '@/platform/availability/context';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import { getAlert, listAlertChanges, listAlertEvents, listAlertLevels, listAssignees, performAlertAction } from '@/features/todo/adapter';
import {
  alertRequestErrorKind,
  availableAlertActions,
  isPermissionDenied,
  primaryAlertAction,
  type AlertAction,
  type AlertAssignee,
  type AlertChange,
  type AlertEvent,
  type AlertLevel,
  type TodoAlert,
} from '@/features/todo/model';
import { invalidateMobileViewSnapshots } from '@/navigation/mobile-view-cache';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/todo/todo.module.css';

type DetailStatus = 'loading' | 'ready' | 'error' | 'forbidden' | 'missing';

function TodoAlertDetailContent() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const { canAccess } = useMobileAvailability();
  const params = useSearchParams();
  const id = Number(params.get('id'));
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const [alert, setAlert] = useState<TodoAlert | null>(null);
  const [levels, setLevels] = useState<AlertLevel[]>([]);
  const [status, setStatus] = useState<DetailStatus>('loading');
  const [activeTab, setActiveTab] = useState('summary');
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [eventStatus, setEventStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [changes, setChanges] = useState<AlertChange[]>([]);
  const [changeStatus, setChangeStatus] = useState<'idle' | 'loading' | 'ready' | 'error' | 'forbidden'>('idle');
  const [pickerAction, setPickerAction] = useState<'assign' | 'reassign' | null>(null);
  const [assignees, setAssignees] = useState<AlertAssignee[]>([]);
  const [assigneeSearch, setAssigneeSearch] = useState('');
  const [selectedAssignees, setSelectedAssignees] = useState<string[]>([]);
  const [assigneeLoading, setAssigneeLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };
  const levelMap = useMemo(() => new Map(levels.map((level) => [String(level.levelId), level])), [levels]);

  const closePicker = useCallback(() => {
    setPickerAction(null);
    setSelectedAssignees([]);
    setAssigneeSearch('');
  }, []);

  const dismissPicker = useCallback(() => {
    if (!pickerAction || submitting) return false;
    closePicker();
    return true;
  }, [closePicker, pickerAction, submitting]);

  const loadDetail = useCallback(async () => {
    if (!Number.isInteger(id) || id <= 0) {
      setAlert(null);
      setStatus('missing');
      return;
    }
    setStatus('loading');
    try {
      const [detail, levelResult] = await Promise.all([getAlert(id), listAlertLevels().catch(() => [])]);
      setAlert(detail);
      setLevels(levelResult);
      setStatus('ready');
    } catch (error) {
      setAlert(null);
      setStatus(alertRequestErrorKind(error));
    }
  }, [id]);

  useEffect(() => { void loadDetail(); }, [loadDetail]);

  const loadEvents = useCallback(async () => {
    if (!alert) return;
    setEventStatus('loading');
    try { setEvents((await listAlertEvents(alert.id)).items); setEventStatus('ready'); }
    catch { setEventStatus('error'); }
  }, [alert]);

  const loadChanges = useCallback(async () => {
    if (!alert) return;
    setChangeStatus('loading');
    try { setChanges((await listAlertChanges(alert.alertId)).items); setChangeStatus('ready'); }
    catch (error) { setChangeStatus(isPermissionDenied(error) ? 'forbidden' : 'error'); }
  }, [alert]);

  useEffect(() => {
    if (activeTab === 'events' && eventStatus === 'idle') void loadEvents();
    if (activeTab === 'changes' && changeStatus === 'idle') void loadChanges();
  }, [activeTab, changeStatus, eventStatus, loadChanges, loadEvents]);

  const loadAssignees = useCallback(async (search: string) => {
    setAssigneeLoading(true);
    try { setAssignees((await listAssignees(search)).items); }
    catch { setAssignees([]); Toast.show({ icon: 'fail', content: t('todo.assigneeLoadFailed') }); }
    finally { setAssigneeLoading(false); }
  }, [t]);

  useEffect(() => {
    if (!pickerAction) return;
    const timer = window.setTimeout(() => void loadAssignees(assigneeSearch), 250);
    return () => window.clearTimeout(timer);
  }, [assigneeSearch, loadAssignees, pickerAction]);

  const runAction = async (action: AlertAction, selected: string[] = []) => {
    if (!alert || submitting) return;
    setSubmitting(true);
    try {
      const message = await performAlertAction(action, alert.alertId, selected);
      invalidateMobileViewSnapshots(cacheScope, ['todo-root']);
      Toast.show({ icon: 'success', content: message || t('todo.actionSuccess') });
      closePicker();
      await loadDetail();
      if (activeTab === 'changes') await loadChanges();
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : t('todo.actionFailed') });
      await loadDetail();
    } finally { setSubmitting(false); }
  };

  const handleAction = async (action: AlertAction) => {
    if (action === 'assign' || action === 'reassign') { setAssigneeSearch(''); setSelectedAssignees([]); setPickerAction(action); return; }
    if (action === 'acknowledge') {
      const confirmed = await Dialog.confirm({ content: t('todo.acknowledgeConfirm'), confirmText: t('todo.actions.acknowledge'), cancelText: t('common.cancel') });
      if (!confirmed) return;
    }
    if (action === 'close') {
      const confirmed = await Dialog.confirm({ content: t('todo.closeConfirm'), confirmText: t('todo.actions.close'), cancelText: t('common.cancel') });
      if (!confirmed) return;
    }
    await runAction(action);
  };

  const header = (
    <MobilePageHeader
      title={t('todo.detailTitle')}
      backHref="/todo"
      onBeforeBack={dismissPicker}
    />
  );

  if (status === 'loading') {
    return (
      <main className={styles.page}>
        {header}
        <MobileSkeleton label={t('common.loading')} variant="detail" rows={4} />
      </main>
    );
  }

  if (status !== 'ready' || !alert) {
    const recoverable = status === 'error';
    return (
      <main className={styles.page}>
        {header}
        <MobileResult
          kind={recoverable ? 'error' : 'permission'}
          title={
            status === 'forbidden'
              ? t('todo.detailForbidden')
              : status === 'missing'
                ? t('todo.detailMissing')
                : t('todo.detailLoadFailed')
          }
          description={recoverable ? t('todo.retryHint') : ''}
          actionLabel={recoverable ? t('common.retry') : undefined}
          onAction={recoverable ? () => void loadDetail() : undefined}
          action={!recoverable ? <Link className={styles.retry} href="/todo">{t('todo.backToTodo')}</Link> : undefined}
        />
      </main>
    );
  }

  const actions = availableAlertActions(alert, userInfo?.username || '', canAccess('todo', 'Edit'));
  const primaryAction = primaryAlertAction(actions);
  const secondaryActions = actions.filter((action) => action !== primaryAction);
  const level = levelMap.get(alert.levelId);
  const formatTime = (value: string) => value ? formatAccountDateTime(value, preferences) : '--';
  const resource = alert.resourceName || alert.resourceId || alert.sourceName || '--';
  const operator = alert.operatorDisplay.trim();
  const summaryStrip = [alert.duration || '--', resource, operator].filter(Boolean).join(' · ');
  const detailFields = [
    [t('todo.fields.firstEvent'), formatTime(alert.firstEventTime)],
    [t('todo.fields.lastEvent'), formatTime(alert.lastEventTime)],
    [t('todo.fields.duration'), alert.duration || '--'],
    [t('todo.fields.operator'), operator || '--'],
    [t('todo.fields.source'), alert.sourceName || '--'],
    [t('todo.fields.resourceType'), alert.resourceType || '--'],
    [t('todo.fields.resourceName'), resource],
    [t('todo.fields.notifyStatus'), alert.notifyStatus || '--'],
  ];

  const sectionState = (sectionStatus: string, retry: () => void, forbidden = false) => (
    <MobileResult kind={forbidden ? 'permission' : 'error'} title={forbidden ? t('todo.noChangePermission') : t('todo.sectionLoadFailed')} description={forbidden ? '' : t('todo.retryHint')} actionLabel={forbidden ? undefined : t('common.retry')} onAction={forbidden ? undefined : retry} compact />
  );

  return (
    <main className={styles.page}>
      {header}
      <div className={styles.detailScroll}>
        <section
          className={styles.summaryCard}
          data-status={alert.status}
        >
          <div className={styles.detailHeroTop}>
            <span
              className={styles.levelBadge}
              style={level?.color ? { color: level.color } : undefined}
            >
              <span className={styles.levelDot} />
              {level?.displayName || `L${alert.levelId}`}
            </span>
            <span className={styles.statusText}>{t(`todo.status.${alert.status}`, alert.status)}</span>
          </div>
          <h1 className={styles.detailTitle}>{alert.title}</h1>
          <div className={styles.detailFacts} aria-label={t('todo.sections.alertInfo')}>
            <span className={styles.summaryStrip}>{summaryStrip}</span>
          </div>
          <div className={styles.detailMeta}>
            <span className={styles.detailMetaItem}>
              <span className={styles.detailMetaLabel}>{t('todo.fields.source')}</span>
              <span className={styles.detailMetaValue}>{alert.sourceName || '--'}</span>
            </span>
            <span className={styles.detailMetaItem}>
              <span className={styles.detailMetaLabel}>{t('todo.fields.alertId')}</span>
              <span className={styles.detailMetaValue}>{alert.alertId}</span>
            </span>
          </div>
        </section>
        <Tabs className={styles.detailTabs} activeKey={activeTab} onChange={setActiveTab}>
          <Tabs.Tab key="summary" title={t('todo.sections.summary')} />
          <Tabs.Tab key="events" title={`${t('todo.sections.events')} (${alert.eventCount})`} />
          <Tabs.Tab key="changes" title={t('todo.sections.changes')} />
        </Tabs>
        {activeTab === 'summary' && <section className={styles.sectionCard}><div className={styles.sectionHeading}>{t('todo.sections.alertInfo')}</div><div className={styles.detailGrid}>{detailFields.map(([label, value]) => <Fragment key={label}><span className={styles.detailLabel}>{label}</span><span className={styles.detailValue}>{value}</span></Fragment>)}</div><div className={styles.contentBlock}><span className={styles.contentLabel}>{t('todo.fields.content')}</span>{alert.content || '--'}</div></section>}
        {activeTab === 'events' && (eventStatus === 'loading' ? <MobileSkeleton label={t('common.loading')} variant="list" rows={3} compact /> : eventStatus === 'error' ? sectionState(eventStatus, () => void loadEvents()) : events.length === 0 ? <MobileResult kind="empty" title={t('todo.noEvents')} compact /> : <section className={styles.sectionCard}><div className={styles.timeline}>{events.map((event) => <article className={styles.timelineItem} key={event.id}><strong className={styles.timelineTitle}>{event.title || event.eventId}</strong><span className={styles.timelineMeta}>{formatTime(event.receivedAt || event.startTime)} · {event.sourceName || '--'}</span><span className={styles.timelineBody}>{event.description || event.resourceName || '--'}</span></article>)}</div></section>)}
        {activeTab === 'changes' && (changeStatus === 'loading' ? <MobileSkeleton label={t('common.loading')} variant="list" rows={3} compact /> : changeStatus === 'forbidden' ? sectionState(changeStatus, () => undefined, true) : changeStatus === 'error' ? sectionState(changeStatus, () => void loadChanges()) : changes.length === 0 ? <MobileResult kind="empty" title={t('todo.noChanges')} compact /> : <section className={styles.sectionCard}><div className={styles.timeline}>{changes.map((change) => <article className={styles.timelineItem} key={change.id}><strong className={styles.timelineTitle}>{change.operatorObject || change.action}</strong><span className={styles.timelineMeta}>{formatTime(change.createdAt)} · {change.operator}</span><span className={styles.timelineBody}>{change.overview || '--'}</span></article>)}</div></section>)}
      </div>
      {actions.length > 0 && primaryAction && (
        <div className={styles.actionBar}>
          <button
            type="button"
            disabled={submitting}
            className={`${styles.actionButton} ${styles.actionButtonPrimary}`}
            onClick={() => void handleAction(primaryAction)}
          >
            {t(`todo.actions.${primaryAction}`)}
          </button>
          {secondaryActions.length > 0 && (
            <div className={styles.secondaryActions} aria-label={t('todo.moreActions')}>
              {secondaryActions.map((action, index) => (
                <Fragment key={action}>
                  {index > 0 ? <span className={styles.secondaryActionSep} aria-hidden="true">·</span> : null}
                  <button
                    type="button"
                    disabled={submitting}
                    className={styles.secondaryActionLink}
                    onClick={() => void handleAction(action)}
                  >
                    {t(`todo.actions.${action}`)}
                  </button>
                </Fragment>
              ))}
            </div>
          )}
        </div>
      )}
      <Popup visible={Boolean(pickerAction)} onMaskClick={() => !submitting && closePicker()} bodyStyle={{ background: 'transparent' }}>
        <div className={styles.popup}>
          <div className={styles.popupHeader}><strong className={styles.popupTitle}>{t(`todo.actions.${pickerAction || 'assign'}`)}</strong><button type="button" className={styles.popupClose} onClick={closePicker} aria-label={t('common.cancel')}>{t('common.cancel')}</button></div>
          <div className={styles.popupSearch}>
            <MobileSearchBar
              size="page"
              value={assigneeSearch}
              onChange={setAssigneeSearch}
              placeholder={t('todo.searchAssignee')}
            />
          </div>
          <div className={styles.assigneeList}>{assigneeLoading ? <MobileSkeleton label={t('common.loading')} variant="list" rows={3} compact /> : assignees.map((person) => <label className={styles.assigneeRow} key={person.username}><input type="checkbox" checked={selectedAssignees.includes(person.username)} onChange={(event) => setSelectedAssignees((current) => event.target.checked ? [...current, person.username] : current.filter((username) => username !== person.username))} /><span className={styles.assigneeCopy}><span className={styles.assigneeName}>{person.displayName}</span><span className={styles.assigneeUsername}>{person.username}</span></span></label>)}</div>
          <div className={styles.popupFooter}><button type="button" className={`${styles.actionButton} ${styles.actionButtonPrimary}`} disabled={!selectedAssignees.length || submitting} onClick={() => pickerAction && void runAction(pickerAction, selectedAssignees)}>{submitting ? t('todo.submitting') : t('common.confirm')}</button></div>
        </div>
      </Popup>
    </main>
  );
}

export default function TodoAlertDetailPage() {
  const { t } = useTranslation();
  return <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="detail" rows={4} />}><TodoAlertDetailContent /></Suspense>;
}
