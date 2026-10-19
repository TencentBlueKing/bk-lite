'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Alert, Button, Empty, Form, Input, Select, Steps, Switch } from 'antd';

import {
  useRumQueries,
  type RumMonitorItem,
  type RumNotificationChannel,
  type RumNotificationRecipient,
  type RumNotificationTarget,
} from '@/app/rum/api';
import { RumBone } from '@/app/rum/components/rum-skeleton';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import NotificationTargetFields from '@/app/rum/monitors/ui/notification-target-fields';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';

const METRICS = [
  'error_rate',
  'lcp_p75',
  'inp_p75',
  'cls_p75',
  'fcp_p75',
  'ttfb_p75',
  'session_count',
] as const;

const SEVERITIES = ['info', 'warning', 'critical'] as const;

const COMPARATORS = [
  { value: '>=', labelKey: 'gte' },
  { value: '>', labelKey: 'gt' },
  { value: '<=', labelKey: 'lte' },
  { value: '<', labelKey: 'lt' },
] as const;

const METRIC_DEFAULTS: Record<string, { warn: string; critical: string }> = {
  error_rate: { warn: '3', critical: '5' },
  lcp_p75: { warn: '2500', critical: '4000' },
  inp_p75: { warn: '200', critical: '500' },
  cls_p75: { warn: '0.1', critical: '0.25' },
  fcp_p75: { warn: '1800', critical: '3000' },
  ttfb_p75: { warn: '800', critical: '1800' },
  session_count: { warn: '', critical: '' },
};

const controlClass = 'w-full max-w-[560px]';
const sentenceSelectClass = '!w-[176px] !max-w-[176px]';
const sentenceInputClass = '!w-[140px] !max-w-[140px]';

function previewOutgoingTitle(
  application: string,
  metric: string,
  severity: string,
  critical: string,
  comparator: string,
): string {
  const object = application.trim() || '—';
  const kind = metric.trim() || '—';
  const sev = severity.trim() || '—';
  const n = Number(critical);
  const value = Number.isFinite(n) ? String(n) : '—';
  return `[${sev}] ${object} ${kind}=${value}（阈 ${comparator}${value}）`;
}

export default function MonitorPolicyEditor({ monitorId }: { monitorId?: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const editing = Boolean(monitorId);
  const {
    listMonitors,
    createMonitor,
    updateMonitor,
    listApplications,
    listNotificationChannels,
    searchNotificationRecipients,
    authReady,
  } = useRumQueries();
  const [ready, setReady] = useState(!editing);
  const [missing, setMissing] = useState(false);
  const [initial, setInitial] = useState<RumMonitorItem | null>(null);
  const [name, setName] = useState('');
  const [application, setApplication] = useState('');
  const [apps, setApps] = useState<string[]>([]);
  const [metric, setMetric] = useState('error_rate');
  const [severity, setSeverity] = useState('warning');
  const [comparator, setComparator] = useState('>=');
  const [critical, setCritical] = useState('5');
  const [warn, setWarn] = useState('3');
  const [organizations, setOrganizations] = useState<number[]>([]);
  const [windowMinutes, setWindowMinutes] = useState(15);
  const [durationMinutes, setDurationMinutes] = useState('5');
  const [noDataAfter, setNoDataAfter] = useState('3');
  const [renotify, setRenotify] = useState('');
  const [handlers, setHandlers] = useState<string[]>([]);
  const [noticeEnabled, setNoticeEnabled] = useState(false);
  const [targets, setTargets] = useState<RumNotificationTarget[]>([]);
  const [channels, setChannels] = useState<RumNotificationChannel[]>([]);
  const [recipients, setRecipients] = useState<RumNotificationRecipient[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      if (!monitorId) return;
      void listMonitors()
        .then((items) => {
          if (isCancelled()) return;
          const found = items.find((item) => item.id === monitorId) ?? null;
          setInitial(found);
          setMissing(!found);
          setReady(true);
        })
        .catch(() => {
          if (isCancelled()) return;
          setMissing(true);
          setReady(true);
        });
    },
    [monitorId, listMonitors],
  );

  useEffect(() => {
    if (!ready || missing) return;
    if (initial) {
      setName(initial.name);
      setApplication(initial.application);
      setMetric(initial.metric);
      setSeverity(initial.severity || 'warning');
      setComparator(initial.comparator || '>=');
      const isErrRate = initial.metric === 'error_rate';
      setCritical(isErrRate ? String(initial.criticalThreshold * 100) : String(initial.criticalThreshold));
      setWarn(isErrRate ? String(initial.warnThreshold * 100) : String(initial.warnThreshold));
      setOrganizations(initial.organizations ?? []);
      setWindowMinutes(initial.evaluationWindowMinutes || 15);
      setDurationMinutes(String(Math.max(0, Math.round((initial.forDurationSec ?? 300) / 60))));
      setNoDataAfter(String(initial.noDataAfter ?? 3));
      setRenotify(initial.renotifyMinutes ? String(initial.renotifyMinutes) : '');
      setHandlers((initial.handlers || []).map(String));
      setTargets(initial.notificationTargets ?? []);
      setNoticeEnabled((initial.notificationTargets ?? []).length > 0);
      setError('');
      return;
    }
    setName('');
    setOrganizations([]);
    setWindowMinutes(15);
    setDurationMinutes('5');
    setNoDataAfter('3');
    setHandlers([]);
    setNoticeEnabled(false);
    setTargets([]);
    setMetric('error_rate');
    setSeverity('warning');
    setComparator('>=');
    setCritical('5');
    setWarn('3');
    setRenotify('');
    setError('');
  }, [ready, missing, initial]);

  useEffect(() => {
    if (!ready) return;
    void listApplications()
      .then((items) => {
        const names = items.map((item) => item.application).filter(Boolean);
        setApps(names);
        if (!initial) {
          setApplication((prev) => prev || names[0] || '');
        }
      })
      .catch(() => setApps([]));
  }, [ready, initial, listApplications]);

  useEffect(() => {
    if (!ready || organizations.length === 0) {
      setChannels([]);
      setRecipients([]);
      return;
    }
    void listNotificationChannels(organizations).then(setChannels).catch(() => setChannels([]));
    void searchNotificationRecipients(organizations, '').then(setRecipients).catch(() => setRecipients([]));
  }, [ready, organizations, listNotificationChannels, searchNotificationRecipients]);

  function handleMetricChange(nextMetric: string) {
    setMetric(nextMetric);
    const defaults = METRIC_DEFAULTS[nextMetric];
    if (defaults) {
      setCritical(defaults.critical);
      setWarn(defaults.warn);
    }
  }

  function leave() {
    router.push('/rum/monitors');
  }

  async function submit() {
    setPending(true);
    setError('');
    try {
      if (!name.trim() || !application.trim() || organizations.length === 0) {
        setError(t('rum.monitors.required', '请填写名称、应用与所属组织'));
        return;
      }
      let criticalValue = Number(critical);
      let warnValue = Number(warn);
      if (!Number.isFinite(criticalValue) || !Number.isFinite(warnValue)) {
        setError(t('rum.monitors.required', '请填写名称与应用'));
        return;
      }
      if (metric === 'error_rate') {
        criticalValue /= 100;
        warnValue /= 100;
      }
      const renotifyValue = renotify.trim() === '' ? undefined : Number(renotify);
      const duration = Number(durationMinutes);
      const noDataCount = Number(noDataAfter);
      if (noticeEnabled && targets.length === 0) {
        setError(t('rum.monitors.channelRequiredWhenEnabled', '启用通知后请至少选择一个通知渠道'));
        return;
      }
      if (noticeEnabled && targets.some((target) => (
        target.deliveryMode !== 'alert_event_copy'
        && target.recipientMode !== 'none'
        && target.recipients.length === 0
      ))) {
        setError(t('rum.monitors.recipientsRequiredForChannel', '所选通知渠道需要配置通知对象'));
        return;
      }
      const body = {
        name: name.trim(),
        application: application.trim(),
        organizations,
        metric,
        severity,
        comparator,
        criticalThreshold: criticalValue,
        warnThreshold: warnValue,
        evaluationWindowMinutes: windowMinutes,
        forDurationSec: Number.isFinite(duration) ? Math.max(0, Math.round(duration * 60)) : 300,
        noDataAfter: Number.isFinite(noDataCount) ? Math.max(0, Math.round(noDataCount)) : 3,
        renotifyMinutes: Number.isFinite(renotifyValue) ? renotifyValue : undefined,
        enabled: initial?.enabled ?? true,
        handlers: handlers.map((item) => (/^\d+$/.test(item) ? Number(item) : item)),
        notificationTargets: noticeEnabled ? targets : [],
      };
      if (initial) await updateMonitor(initial.id, body);
      else await createMonitor(body);
      leave();
    } catch (err) {
      setError(rumErrorMessage(err, t));
    } finally {
      setPending(false);
    }
  }

  const unitSuffix =
    metric === 'error_rate' ? '%' : metric === 'cls_p75' ? 'Score' : metric === 'session_count' ? '' : 'ms';
  const metricName = t(`rum.monitors.metric.${metric}`, metric);
  const pageTitle = initial
    ? initial.name
    : t('rum.monitors.create', '新建策略');

  const stepItems = [
    {
      title: t('rum.monitors.basic', '基本信息'),
      status: 'process' as const,
      description: (
        <div className="max-w-[840px] py-3">
          <Form.Item label={t('rum.monitors.name', '名称')}>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('rum.monitors.namePlaceholder', '例如：核心交易页面错误率过高')}
              autoFocus
              className={controlClass}
            />
          </Form.Item>
          <Form.Item label={t('rum.monitors.organizations', '所属组织')}>
            <div className={controlClass}>
              <GroupTreeSelect
                multiple
                mode="ownership"
                showSearch
                value={organizations}
                onChange={(value) => setOrganizations(Array.isArray(value) ? value : value == null ? [] : [value])}
                placeholder={t('rum.monitors.organizationsPlaceholder', '选择所属组织')}
              />
            </div>
          </Form.Item>
          <Form.Item label={t('rum.monitors.handlers', '处理人')}>
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              className={controlClass}
              disabled={organizations.length === 0}
              value={handlers}
              onChange={setHandlers}
              options={recipients.map((item) => ({
                value: String(item.id),
                label: item.display_name ? `${item.display_name} (${item.username})` : item.username,
              }))}
              placeholder={organizations.length
                ? t('rum.monitors.handlersPlaceholder', '从策略所属组织选择处理人')
                : t('rum.monitors.selectOrganizationFirst', '请先选择所属组织')}
            />
          </Form.Item>
          <Form.Item label={t('rum.applications.application', '应用')}>
            {apps.length > 0 ? (
              <Select
                value={application || undefined}
                onChange={setApplication}
                options={apps.map((app) => ({ value: app, label: app }))}
                className={controlClass}
              />
            ) : (
              <Input
                value={application}
                onChange={(event) => setApplication(event.target.value)}
                placeholder="storefront"
                className={controlClass}
              />
            )}
          </Form.Item>
        </div>
      ),
    },
    {
      title: t('rum.monitors.metricLabel', '指标'),
      status: 'process' as const,
      description: (
        <div className="max-w-[840px] py-3">
          <Form.Item label={t('rum.monitors.metricLabel', '指标')}>
            <Select
              value={metric}
              onChange={handleMetricChange}
              options={METRICS.map((item) => ({
                value: item,
                label: t(`rum.monitors.metric.${item}`, item),
              }))}
              className={controlClass}
            />
          </Form.Item>
          <Form.Item label={t('rum.monitors.window', '判定窗口')}>
            <Select
              value={windowMinutes}
              onChange={setWindowMinutes}
              options={[5, 15, 60].map((minutes) => ({
                value: minutes,
                label: t('rum.monitors.windowMinutes', '{n} 分钟', { n: minutes }),
              }))}
              className={controlClass}
            />
          </Form.Item>
        </div>
      ),
    },
    {
      title: t('rum.monitors.conditionStep', '告警条件'),
      status: 'process' as const,
      description: (
        <div className="max-w-[840px] py-3">
          <Form.Item label={t('rum.monitors.condition', '条件')}>
            <div className="flex min-h-10 flex-wrap items-center gap-2">
              <span className="text-[var(--color-text-3)]">
                {t('rum.monitors.whenMetric', '当 {metric}', { metric: metricName })}
              </span>
              <Select
                aria-label={t('rum.monitors.comparatorLabel', '比较符')}
                value={comparator}
                onChange={setComparator}
                options={COMPARATORS.map((item) => ({
                  value: item.value,
                  label: t(`rum.monitors.comparator.${item.labelKey}`, item.value),
                }))}
                className={sentenceSelectClass}
              />
              <Input
                aria-label={t('rum.monitors.critical', '严重阈值')}
                value={critical}
                onChange={(event) => setCritical(event.target.value)}
                suffix={<span className="text-xs text-[var(--color-text-3)]">{unitSuffix}</span>}
                className={sentenceInputClass}
              />
              <span className="text-[var(--color-text-3)]">{t('rum.monitors.duration', '持续时长')}</span>
              <Input
                aria-label={t('rum.monitors.duration', '持续时长')}
                value={durationMinutes}
                onChange={(event) => setDurationMinutes(event.target.value)}
                inputMode="numeric"
                suffix={<span className="text-[var(--color-text-3)]">{t('rum.monitors.minutes', '分钟')}</span>}
                className={sentenceInputClass}
              />
            </div>
          </Form.Item>
          <Form.Item label={t('rum.monitors.severityLabel', '严重级别')}>
            <Select
              value={severity}
              onChange={setSeverity}
              options={SEVERITIES.map((item) => ({
                value: item,
                label: t(`rum.monitors.severity.${item}`, item),
              }))}
              className={controlClass}
            />
          </Form.Item>
          <Form.Item label={t('rum.monitors.warn', '警告阈值')}>
            <Input
              value={warn}
              onChange={(event) => setWarn(event.target.value)}
              suffix={<span className="text-xs text-[var(--color-text-3)]">{unitSuffix}</span>}
              className={controlClass}
            />
          </Form.Item>
          <Form.Item
            label={t('rum.monitors.noDataAfter', '无数据次数')}
            extra={t('rum.monitors.noDataAfterHint', '连续无数据达到该次数后告警，0 表示关闭。')}
          >
            <Input
              value={noDataAfter}
              onChange={(event) => setNoDataAfter(event.target.value)}
              inputMode="numeric"
              className={controlClass}
            />
          </Form.Item>
          <Form.Item
            label={t('rum.monitors.renotifyLabel', '重复通知')}
            extra={t('rum.monitors.renotifyHint', '留空表示不重复通知。')}
          >
            <Input
              value={renotify}
              onChange={(event) => setRenotify(event.target.value)}
              inputMode="numeric"
              placeholder="30"
              suffix={<span className="text-xs text-[var(--color-text-3)]">{t('rum.monitors.minutes', '分钟')}</span>}
              className={controlClass}
            />
          </Form.Item>
        </div>
      ),
    },
    {
      title: t('rum.monitors.noticeStep', '通知'),
      status: 'process' as const,
      description: (
        <div className="max-w-[840px] py-3">
          <Form.Item label={t('rum.monitors.notice', '通知')}>
            <Switch
              checked={noticeEnabled}
              aria-label={t('rum.monitors.enableNotification', '启用通知')}
              onChange={(checked) => {
                setNoticeEnabled(checked);
                if (!checked) setTargets([]);
              }}
            />
            <div className="mt-2.5 text-[var(--color-text-3)]">
              {t('rum.monitors.noticeHint', '选择告警触发时的通知方式和接收人。')}
            </div>
          </Form.Item>
          {noticeEnabled ? (
            <NotificationTargetFields
              targets={targets}
              channels={channels}
              recipients={recipients}
              handlers={handlers}
              organizationsReady={organizations.length > 0}
              onChange={setTargets}
              onSearchRecipients={(search) => {
                void searchNotificationRecipients(organizations, search).then(setRecipients).catch(() => setRecipients([]));
              }}
            />
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mb-3">
          <nav aria-label={t('rum.monitors.breadcrumb', '页面路径')} className="flex min-w-0 items-center gap-1.5">
            <Link
              href="/rum/monitors"
              aria-label={t('rum.monitors.backAria', '返回告警策略')}
              className="shrink-0 text-sm text-[var(--color-text-3)] no-underline transition-colors hover:text-[var(--color-primary)]"
            >
              {t('rum.monitors.title', '告警策略')}
            </Link>
            <span className="shrink-0 text-[var(--color-text-3)]" aria-hidden="true">/</span>
            <h1 className="mb-0 truncate text-base font-semibold">{ready && !missing ? pageTitle : t('rum.monitors.edit', '编辑策略')}</h1>
          </nav>
        </div>

        {!ready ? (
          <div className="flex max-w-[840px] flex-col gap-4 py-2">
            <RumBone className="!w-48" />
            <RumBone className="!w-full" />
            <RumBone className="!w-full" />
            <RumBone className="!w-2/3" />
          </div>
        ) : missing ? (
          <Empty description={t('rum.monitors.notFound', '没有找到这条策略')}>
            <Button onClick={leave}>{t('rum.monitors.title', '告警策略')}</Button>
          </Empty>
        ) : (
          <Form
            layout="horizontal"
            requiredMark={false}
            labelCol={{ flex: '120px' }}
            wrapperCol={{ flex: '1 1 0' }}
            className="[&_.ant-form-item]:mb-[18px] [&_.ant-form-item-label]:!w-[120px] [&_.ant-form-item-label]:!max-w-[120px] [&_.ant-form-item-label>label]:whitespace-nowrap"
          >
            {error ? <Alert type="error" showIcon message={error} className="mb-4" /> : null}
            <div className="grid items-start gap-6 min-[1280px]:grid-cols-[minmax(680px,860px)_minmax(280px,1fr)]">
              <div className="min-w-0">
                <Steps
                  direction="vertical"
                  current={0}
                  items={stepItems}
                  className="[&_.ant-steps-item-description]:!max-w-none [&_.ant-steps-item-title]:!text-base [&_.ant-steps-item-title]:!font-semibold"
                />
                <div className="sticky bottom-0 z-10 flex justify-end gap-2 border-t border-[var(--color-border-1)] bg-[var(--color-bg)] py-4">
                  <Button onClick={leave}>{t('rum.common.cancel', '取消')}</Button>
                  <Button type="primary" loading={pending} onClick={() => void submit()}>
                    {initial ? t('rum.common.save', '保存') : t('rum.monitors.create', '新建策略')}
                  </Button>
                </div>
              </div>
              <aside className="min-w-0 min-[1280px]:sticky min-[1280px]:top-4">
                <h2 className="mb-2 text-sm font-semibold">{t('rum.monitors.preview', '通知预览')}</h2>
                <p className="break-all font-mono text-xs leading-5 text-[var(--color-text-1)]">
                  {previewOutgoingTitle(application, metric, severity, critical, comparator)}
                </p>
              </aside>
            </div>
          </Form>
        )}
      </div>
    </div>
  );
}
