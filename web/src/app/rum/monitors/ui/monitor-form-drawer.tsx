'use client';

import { useEffect, useState } from 'react';
import { BellOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Form, Input, Select } from 'antd';

import {
  useRumQueries,
  type RumMonitorItem,
  type RumNotificationChannel,
  type RumNotificationRecipient,
  type RumNotificationTarget,
} from '@/app/rum/api';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
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

export default function MonitorFormDrawer({
  open,
  onOpenChange,
  onSaved,
  initial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  initial?: RumMonitorItem | null;
}) {
  const { t } = useTranslation();
  const { createMonitor, updateMonitor, listApplications, listNotificationChannels, searchNotificationRecipients } = useRumQueries();
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
  const [targets, setTargets] = useState<RumNotificationTarget[]>([]);
  const [channels, setChannels] = useState<RumNotificationChannel[]>([]);
  const [recipients, setRecipients] = useState<RumNotificationRecipient[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
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
      setError('');
    } else {
      setName('');
      setOrganizations([]);
      setWindowMinutes(15);
      setDurationMinutes('5');
      setNoDataAfter('3');
      setHandlers([]);
      setTargets([]);
      setMetric('error_rate');
      setSeverity('warning');
      setComparator('>=');
      setCritical('5');
      setWarn('3');
      setRenotify('');
      setError('');
    }
    void listApplications()
      .then((items) => {
        const names = items.map((a) => a.application).filter(Boolean);
        setApps(names);
        if (!initial) {
          setApplication((prev) => prev || names[0] || '');
        }
      })
      .catch(() => setApps([]));
  }, [open, initial, listApplications]);

  useEffect(() => {
    if (!open || organizations.length === 0) {
      setChannels([]);
      setRecipients([]);
      return;
    }
    void listNotificationChannels(organizations).then(setChannels).catch(() => setChannels([]));
    void searchNotificationRecipients(organizations, '').then(setRecipients).catch(() => setRecipients([]));
  }, [open, organizations, listNotificationChannels, searchNotificationRecipients]);

  function handleMetricChange(nextMetric: string) {
    setMetric(nextMetric);
    const defaults = METRIC_DEFAULTS[nextMetric];
    if (defaults) {
      setCritical(defaults.critical);
      setWarn(defaults.warn);
    }
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
        notificationTargets: targets,
      };
      if (initial) await updateMonitor(initial.id, body);
      else await createMonitor(body);
      onOpenChange(false);
      onSaved();
    } catch (err) {
      setError(rumErrorMessage(err, t));
    } finally {
      setPending(false);
    }
  }

  const unitSuffix =
    metric === 'error_rate' ? '%' : metric === 'cls_p75' ? 'Score' : metric === 'session_count' ? '' : 'ms';

  return (
    <Drawer
      open={open}
      onClose={() => onOpenChange(false)}
      destroyOnClose
      width={480}
      title={initial ? t('rum.monitors.edit', '编辑策略') : t('rum.monitors.create', '新建策略')}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)}>{t('rum.common.cancel', '取消')}</Button>
          <Button type="primary" loading={pending} onClick={() => void submit()}>
            {initial ? t('rum.common.save', '保存') : t('rum.monitors.create', '新建策略')}
          </Button>
        </div>
      }
    >
      <div className="space-y-5">
        {error ? <Alert type="error" showIcon message={error} /> : null}

        <Form layout="vertical" requiredMark={false}>
          <Form.Item label={t('rum.monitors.name', '名称')} className="mb-4">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('rum.monitors.namePlaceholder', '例如：核心交易页面错误率过高')}
              autoFocus
            />
          </Form.Item>

          <Form.Item label={t('rum.monitors.organizations', '所属组织')} className="mb-4">
            <GroupTreeSelect
              multiple
              mode="ownership"
              showSearch
              value={organizations}
              onChange={(value) => setOrganizations(Array.isArray(value) ? value : value == null ? [] : [value])}
              placeholder={t('rum.monitors.organizationsPlaceholder', '选择所属组织')}
            />
          </Form.Item>

          <Form.Item label={t('rum.applications.application', '应用')} className="mb-4">
            {apps.length > 0 ? (
              <Select
                value={application || undefined}
                onChange={setApplication}
                options={apps.map((app) => ({ value: app, label: app }))}
                className="w-full"
              />
            ) : (
              <Input
                value={application}
                onChange={(e) => setApplication(e.target.value)}
                placeholder="storefront"
              />
            )}
          </Form.Item>

          <div className="mb-4 grid grid-cols-2 gap-3">
            <Form.Item label={t('rum.monitors.metricLabel', '指标')} className="mb-0">
              <Select
                value={metric}
                onChange={handleMetricChange}
                options={METRICS.map((m) => ({
                  value: m,
                  label: t(`rum.monitors.metric.${m}`, m),
                }))}
                className="w-full"
              />
            </Form.Item>
            <Form.Item label={t('rum.monitors.severityLabel', '严重级别')} className="mb-0">
              <Select
                value={severity}
                onChange={setSeverity}
                options={SEVERITIES.map((s) => ({
                  value: s,
                  label: t(`rum.monitors.severity.${s}`, s),
                }))}
                className="w-full"
              />
            </Form.Item>
          </div>

          <Form.Item label={t('rum.monitors.comparatorLabel', '比较符')} className="mb-4">
            <Select
              value={comparator}
              onChange={setComparator}
              options={COMPARATORS.map((o) => ({
                value: o.value,
                label: t(`rum.monitors.comparator.${o.labelKey}`, o.value),
              }))}
              className="w-full"
            />
          </Form.Item>

          <div className="mb-4 grid grid-cols-2 gap-3">
            <Form.Item label={t('rum.monitors.critical', '严重阈值')} className="mb-0">
              <Input
                value={critical}
                onChange={(e) => setCritical(e.target.value)}
                suffix={<span className="text-xs text-[var(--color-text-3)]">{unitSuffix}</span>}
              />
            </Form.Item>
            <Form.Item label={t('rum.monitors.warn', '警告阈值')} className="mb-0">
              <Input
                value={warn}
                onChange={(e) => setWarn(e.target.value)}
                suffix={<span className="text-xs text-[var(--color-text-3)]">{unitSuffix}</span>}
              />
            </Form.Item>
          </div>

          <div className="mb-4 grid grid-cols-3 gap-3">
            <Form.Item label={t('rum.monitors.window', '判定窗口')} className="mb-0">
              <Select
                value={windowMinutes}
                onChange={setWindowMinutes}
                options={[5, 15, 60].map((minutes) => ({
                  value: minutes,
                  label: t('rum.monitors.windowMinutes', '{n} 分钟', { n: minutes }),
                }))}
                className="w-full"
              />
            </Form.Item>
            <Form.Item label={t('rum.monitors.duration', '持续时长')} className="mb-0">
              <Input
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(e.target.value)}
                inputMode="numeric"
                suffix={<span className="text-[var(--color-text-3)]">{t('rum.monitors.minutes', '分钟')}</span>}
              />
            </Form.Item>
            <Form.Item
              label={t('rum.monitors.noDataAfter', '无数据次数')}
              className="mb-0"
              extra={t('rum.monitors.noDataAfterHint', '连续无数据达到该次数后告警，0 表示关闭。')}
            >
              <Input value={noDataAfter} onChange={(e) => setNoDataAfter(e.target.value)} inputMode="numeric" />
            </Form.Item>
          </div>

          <Form.Item
            label={t('rum.monitors.renotifyLabel', '重复通知（分钟）')}
            className="mb-4"
            extra={t('rum.monitors.renotifyHint', '留空表示不重复通知。')}
          >
            <Input
              value={renotify}
              onChange={(e) => setRenotify(e.target.value)}
              inputMode="numeric"
              placeholder="30"
            />
          </Form.Item>

          <Form.Item label={t('rum.monitors.handlers', '处理人')} className="mb-4">
            <Select
              mode="multiple"
              className="w-full"
              value={handlers}
              onChange={setHandlers}
              options={recipients.map((item) => ({
                value: String(item.id),
                label: item.display_name ? `${item.display_name} (${item.username})` : item.username,
              }))}
              placeholder={t('rum.monitors.handlersPlaceholder', '可选，告警产生时快照这些处理人')}
            />
          </Form.Item>

          <Form.Item label={t('rum.monitors.methods', '通知渠道')} className="mb-4">
            <NotificationTargetFields
              targets={targets}
              channels={channels}
              recipients={recipients}
              onChange={setTargets}
              onSearchRecipients={(search) => {
                void searchNotificationRecipients(organizations, search).then(setRecipients).catch(() => setRecipients([]));
              }}
            />
          </Form.Item>

          <div className="space-y-1 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-2)]/40 p-3">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--color-text-3)]">
              <BellOutlined />
              <span>{t('rum.monitors.preview', '通知预览')}</span>
            </div>
            <div className="font-mono text-xs">
              {previewOutgoingTitle(application, metric, severity, critical, comparator)}
            </div>
          </div>
        </Form>
      </div>
    </Drawer>
  );
}
