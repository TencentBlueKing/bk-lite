'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  CheckOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  CopyOutlined,
  InfoCircleOutlined,
  LineChartOutlined,
  PlayCircleOutlined,
  RightOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Alert, Button, Empty, message, Tag, Tooltip, type TableColumnsType } from 'antd';

import {
  useRumQueries,
  type RumErrorDetail,
  type RumErrorOccurrence,
} from '@/app/rum/api';
import RumPermission from '@/app/rum/components/rum-permission';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import RumBackButton, { RumDetailTitle } from '@/app/rum/components/rum-back-button';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import { RumErrorDetailSkeleton } from '@/app/rum/components/rum-skeleton';
import Sparkline from '@/app/apm/components/home/sparkline';
import { toneSemanticPalette, type CwvTone } from '@/app/rum/lib/cwv';
import SemanticBadge from '@/components/semantic-badge';
import { degradationReason } from '@/app/rum/lib/degradation';
import { truncateMiddle } from '@/app/rum/lib/format';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { isProtectedRumMessage } from '@/app/rum/sessions/lib/timeline-error';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import EvidenceStack, { formatFullStackTrace } from '@/app/rum/errors/ui/evidence-stack';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';

const statusTone: Record<string, CwvTone> = {
  resolved: 'success',
  ignored: 'neutral',
  open: 'warning',
  reviewed: 'neutral',
};

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function RumErrorDetailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { range, application, searchParams } = useRumSearchParams();
  const fingerprint = searchParams.get('fingerprint') || '';
  const app = application || searchParams.get('application') || '';
  const { getErrorDetail, updateErrorIssue, restoreSourceMap, authReady } = useRumQueries();

  const [detail, setDetail] = useState<RumErrorDetail | null>(null);
  const [pending, setPending] = useState(true);
  const [acting, setActing] = useState(false);
  const [copiedFingerprint, setCopiedFingerprint] = useState(false);
  const [copiedStack, setCopiedStack] = useState(false);
  const [sourceMapOutcome, setSourceMapOutcome] = useState<'resolved' | 'missing_artifact' | ''>('');

  const load = useCallback(async () => {
    if (!fingerprint) {
      setPending(false);
      return;
    }
    setPending(true);
    try {
      let loaded = await getErrorDetail(fingerprint, { range, application: app });
      if (!loaded.controlUnavailable && !loaded.analyticsUnavailable) {
        try {
          const frames = JSON.parse(loaded.sampleFrames || '[]');
          if (Array.isArray(frames) && frames.length > 0) {
            const restored = await restoreSourceMap(loaded.application, loaded.lastRelease || '', frames);
            loaded = { ...loaded, sampleFrames: JSON.stringify(restored.frames) };
            if (restored.outcome === 'resolved') {
              setSourceMapOutcome('resolved');
            } else if (restored.outcome === 'missing_artifact') {
              setSourceMapOutcome('missing_artifact');
            } else {
              setSourceMapOutcome('');
            }
          }
        } catch {
          setSourceMapOutcome('');
        }
      }
      setDetail(loaded);
    } catch {
      setDetail(null);
    } finally {
      setPending(false);
    }
  }, [app, fingerprint, getErrorDetail, range, restoreSourceMap]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      void load().then(() => {
        if (isCancelled()) return;
      });
    },
    [load],
  );

  const degrade = degradationReason(detail);
  const statusLabel = detail?.status || 'open';
  const rawTitle = detail?.sampleMessage || detail?.normalizedMessage || '';
  const protectedMessage = isProtectedRumMessage(rawTitle);
  const title = protectedMessage
    ? detail?.errorType || t('rum.errors.untitled', '异常错误')
    : rawTitle || t('rum.errors.detail.title', '错误详情');

  const triageActions = useMemo(() => {
    if (statusLabel === 'open') {
      return [
        ['resolved', t('rum.errors.triage.resolve', '解决'), true],
        ['reviewed', t('rum.errors.triage.markReviewed', '已审阅'), false],
        ['ignored', t('rum.errors.triage.ignore', '忽略'), false],
      ] as const;
    }
    if (statusLabel === 'reviewed') {
      return [
        ['resolved', t('rum.errors.triage.resolve', '解决'), true],
        ['ignored', t('rum.errors.triage.ignore', '忽略'), false],
        ['open', t('rum.errors.triage.reopen', '重开'), false],
      ] as const;
    }
    if (statusLabel === 'resolved') {
      return [['open', t('rum.errors.triage.reopen', '重开'), false]] as const;
    }
    return [
      ['open', t('rum.errors.triage.reopen', '重开'), false],
      ['resolved', t('rum.errors.triage.resolve', '解决'), true],
    ] as const;
  }, [statusLabel, t]);

  async function triage(nextStatus: string) {
    if (!detail) return;
    setActing(true);
    try {
      await updateErrorIssue(detail.fingerprint, { status: nextStatus });
      setDetail({ ...detail, status: nextStatus });
      void message.success(t('common.saved', '状态已更新'));
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(false);
    }
  }

  const stackFramesCount = useMemo(() => {
    if (!detail?.sampleFrames) return 0;
    try {
      const parsed = JSON.parse(detail.sampleFrames);
      return Array.isArray(parsed) ? parsed.length : 0;
    } catch {
      return 0;
    }
  }, [detail?.sampleFrames]);

  const handleCopyFingerprint = useCallback(() => {
    if (!fingerprint) return;
    void navigator.clipboard.writeText(fingerprint).then(() => {
      setCopiedFingerprint(true);
      void message.success(t('common.copied', '已复制错误指纹'));
      setTimeout(() => setCopiedFingerprint(false), 2000);
    });
  }, [fingerprint, t]);

  const handleCopyFullStack = useCallback(() => {
    if (!detail) return;
    const fullStack = formatFullStackTrace(detail.sampleFrames, `${detail.errorType || 'Error'}: ${rawTitle}`);
    void navigator.clipboard.writeText(fullStack).then(() => {
      setCopiedStack(true);
      void message.success(t('rum.errors.detail.stackCopied', '已复制完整堆栈'));
      setTimeout(() => setCopiedStack(false), 2000);
    });
  }, [detail, rawTitle, t]);

  const occurrenceColumns: TableColumnsType<RumErrorOccurrence> = useMemo(
    () => [
      {
        title: t('rum.sessions.session', '会话'),
        dataIndex: 'sessionId',
        key: 'sessionId',
        render: (value: string) => (
          <div className="flex items-center gap-1.5 font-mono text-xs">
            <Link
              href={`/rum/sessions/${encodeURIComponent(value)}?application=${encodeURIComponent(detail?.application || app)}&range=${range}`}
              className="text-[var(--color-primary)] hover:underline"
              title={value}
              onClick={(e) => e.stopPropagation()}
            >
              {truncateMiddle(value, 20)}
            </Link>
          </div>
        ),
      },
      {
        title: t('rum.sessions.user', '用户'),
        dataIndex: 'userId',
        key: 'userId',
        render: (value: string) => (
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-2)]">
            <UserOutlined className="text-[11px] text-[var(--color-text-4)]" />
            <span>{value || '—'}</span>
          </div>
        ),
      },
      {
        title: t('rum.errors.lastSeen', '最近出现'),
        dataIndex: 'timestamp',
        key: 'timestamp',
        render: (value: string) => (
          <span className="text-xs tabular-nums text-[var(--color-text-2)]">{formatWhen(value)}</span>
        ),
      },
      {
        title: t('rum.common.actions', '操作'),
        key: 'actions',
        width: 100,
        fixed: 'right',
        render: (_, row) =>
          row.hasReplay ? (
            <Link
              href={`/rum/sessions/${encodeURIComponent(row.sessionId)}/replay?application=${encodeURIComponent(detail?.application || app)}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-[var(--color-primary)] hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              <PlayCircleOutlined className="text-xs" />
              <span>{t('rum.sessions.replayAction', '回放')}</span>
            </Link>
          ) : (
            <Link
              href={`/rum/sessions/${encodeURIComponent(row.sessionId)}?application=${encodeURIComponent(detail?.application || app)}&range=${range}`}
              className="inline-flex items-center gap-1 text-xs text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
              onClick={(e) => e.stopPropagation()}
            >
              <span>{t('rum.sessions.viewSession', '查看会话')}</span>
              <RightOutlined className="text-[10px]" />
            </Link>
          ),
      },
    ],
    [app, detail?.application, range, t],
  );

  const backHref = `/rum/errors?range=${range}${app ? `&application=${encodeURIComponent(app)}` : ''}`;

  if (!fingerprint) {
    return (
      <Alert
        type="info"
        showIcon
        message={t('rum.errors.detail.missingFingerprint', '缺少错误指纹')}
        action={<RumBackButton onClick={() => router.push('/rum/errors')} />}
      />
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto">
      {/* 顶部主标题栏 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <RumDetailTitle
          title={
            <div className="flex flex-wrap items-center gap-2">
              <h1
                className="m-0 max-w-[min(100%,44rem)] truncate text-base font-semibold text-[var(--color-text-1)]"
                title={title}
              >
                {title}
              </h1>
              {detail?.errorType && detail.errorType !== title ? (
                <Tag className="m-0 border-0 bg-[var(--color-fill-2)] font-mono text-xs text-[var(--color-text-2)]">
                  {detail.errorType}
                </Tag>
              ) : null}
              {protectedMessage ? (
                <Tag className="m-0 border-0 bg-[var(--color-fill-2)] text-xs text-[var(--color-text-3)]">
                  {t('rum.errors.privateMessage', '消息已隐私化')}
                </Tag>
              ) : null}
            </div>
          }
          afterTitle={
            detail ? (
              <SemanticBadge
                label={t(`rum.errors.statusLabel.${statusLabel}`, statusLabel)}
                {...toneSemanticPalette(statusTone[statusLabel] || 'neutral')}
              />
            ) : null
          }
          onBack={() => router.push(backHref)}
          subtitle={
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--color-text-3)]">
              <span className="font-medium text-[var(--color-text-2)]">{detail?.application || app}</span>
              <span aria-hidden>·</span>
              <div className="flex items-center gap-1 font-mono">
                <span title={fingerprint}>{truncateMiddle(fingerprint, 28)}</span>
                <Tooltip title={copiedFingerprint ? t('common.copied', '已复制') : t('rum.errors.copyFingerprint', '复制错误指纹')}>
                  <button
                    type="button"
                    onClick={handleCopyFingerprint}
                    className="inline-flex size-5 items-center justify-center rounded text-[var(--color-text-3)] transition-colors hover:bg-[var(--color-fill-1)] hover:text-[var(--color-text-1)]"
                    aria-label="copy-fingerprint"
                  >
                    {copiedFingerprint ? <CheckOutlined className="text-[var(--color-success)] text-xs" /> : <CopyOutlined className="text-xs" />}
                  </button>
                </Tooltip>
              </div>
              {detail?.lastSeen ? (
                <>
                  <span aria-hidden>·</span>
                  <span>{t('rum.errors.lastSeen', '最近出现')}: {formatWhen(detail.lastSeen)}</span>
                </>
              ) : null}
            </div>
          }
        />

        {/* 顶部操作区 */}
        {detail ? (
          <RumPermission
            resource="errors"
            action="Operate"
            className="inline-flex items-center gap-2"
          >
            {triageActions.map(([next, label, isPrimary]) => (
              <Button
                key={next}
                type={isPrimary ? 'primary' : 'default'}
                loading={acting}
                disabled={acting}
                onClick={() => void triage(next)}
              >
                {label}
              </Button>
            ))}
          </RumPermission>
        ) : null}
      </div>

      {degrade ? <PipelineDegradedBanner reason={degrade} /> : null}
      {pending && !detail ? <RumErrorDetailSkeleton /> : null}
      {!pending && !detail ? <Empty description={t('rum.errors.empty', '没有错误样本')} /> : null}

      {detail ? (
        <>
          {/* 顶部 4 列核心指标卡 */}
          <RumMetricGrid
            cells={[
              {
                label: t('rum.errors.count', '次数'),
                value: String(detail.count),
                tone: detail.count > 0 ? 'danger' : 'neutral',
              },
              {
                label: t('rum.errors.sessions', '会话'),
                value: String(detail.affectedSessions),
                tone: detail.affectedSessions > 0 ? 'info' : 'neutral',
              },
              {
                label: t('rum.errors.users', '用户数'),
                value: String(detail.affectedUsers),
                tone: detail.affectedUsers > 0 ? 'info' : 'neutral',
              },
              {
                label: t('rum.errors.lastSeen', '最近出现'),
                value: formatWhen(detail.lastSeen),
              },
            ]}
          />

          {/* 响应式左右分析区：左侧核心证据（堆栈 + 出现记录） + 右侧诊断与趋势面板 */}
          <div className="flex min-w-0 flex-col items-start gap-4 lg:flex-row">
            {/* 左侧主要区域 */}
            <div className="flex min-w-0 flex-1 flex-col gap-4 w-full">
              {/* 卡片 1: 异常堆栈追踪 */}
              <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <CodeOutlined className="text-sm text-[var(--color-primary)]" />
                    <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                      {t('rum.errors.detail.stack', '堆栈追踪')}
                    </h2>
                    {stackFramesCount > 0 ? (
                      <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-2 text-xs font-semibold tabular-nums text-[var(--color-primary)]">
                        {stackFramesCount}
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    {sourceMapOutcome === 'resolved' ? (
                      <Tag color="success" className="m-0 border-0 text-[11px]">
                        {t('rum.errors.detail.stackRestored', '堆栈已通过 Source Map 还原')}
                      </Tag>
                    ) : sourceMapOutcome === 'missing_artifact' ? (
                      <Tooltip title={t('rum.errors.detail.missingMapHint', '上传构建 Source Map 产物可将混淆代码还原至源码精确行列')}>
                        <Tag color="warning" className="m-0 cursor-help border-0 text-[11px]">
                          {t('rum.errors.detail.stackMissingMap', '缺少 Source Map 产物')}
                        </Tag>
                      </Tooltip>
                    ) : null}
                    {stackFramesCount > 0 ? (
                      <Button
                        size="small"
                        icon={copiedStack ? <CheckOutlined className="text-[var(--color-success)]" /> : <CopyOutlined />}
                        onClick={handleCopyFullStack}
                      >
                        {copiedStack ? t('common.copied', '已复制') : t('rum.errors.detail.copyStack', '复制堆栈')}
                      </Button>
                    ) : null}
                  </div>
                </div>
                <EvidenceStack raw={detail.sampleFrames} embedded />
              </section>

              {/* 卡片 2: 最近出现记录 */}
              <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <ClockCircleOutlined className="text-sm text-[var(--color-primary)]" />
                    <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                      {t('rum.errors.detail.occurrences', '最近出现记录')}
                    </h2>
                    {detail.occurrences.length > 0 ? (
                      <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-2 text-xs font-semibold tabular-nums text-[var(--color-primary)]">
                        {detail.occurrences.length}
                      </span>
                    ) : null}
                  </div>
                  <span className="text-xs text-[var(--color-text-4)]">
                    {t('rum.errors.detail.sampleHint', '采样最近发生的异常会话上下文')}
                  </span>
                </div>
                <CustomTable
                  rowKey="eventId"
                  size="middle"
                  pagination={false}
                  dataSource={detail.occurrences}
                  columns={occurrenceColumns}
                  locale={{ emptyText: t('rum.errors.detail.occurrencesEmpty', '暂无出现记录') }}
                />
              </section>
            </div>

            {/* 右侧上下文与诊断面板 */}
            <div className="flex w-full shrink-0 flex-col gap-4 lg:w-[320px] xl:w-[340px]">
              {/* 卡片 3: 出现趋势 */}
              {detail.sparkline?.length ? (
                <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                  <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <LineChartOutlined className="text-sm text-[var(--color-primary)]" />
                      <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                        {t('rum.errors.detail.trend', '出现趋势')}
                      </h2>
                    </div>
                    <span className="text-[11px] text-[var(--color-text-4)]">
                      {range === '1h'
                        ? t('rum.range.1h', '最近 1 小时')
                        : range === '24h'
                          ? t('rum.range.24h', '最近 24 小时')
                          : t('rum.range.current', '当前区间')}
                    </span>
                  </div>
                  <div className="space-y-3 p-3.5">
                    <div className="rounded-md border border-[var(--color-border-1)]/60 bg-[var(--color-fill-1)]/20 p-2">
                      <Sparkline data={detail.sparkline} height={80} color="var(--color-primary)" kind="area" />
                    </div>
                    <div className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 text-xs">
                      <span className="text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.errors.detail.peakCount', '周期最高频次')}</span>
                      <span className="font-mono font-semibold tabular-nums text-[var(--color-text-1)]">
                        {Math.max(...detail.sparkline, 0)} {t('rum.errors.detail.times', '次')}
                      </span>
                    </div>
                  </div>
                </section>
              ) : null}

              {/* 卡片 4: 问题属性与诊断信息 */}
              <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                <div className="flex items-center gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                  <InfoCircleOutlined className="text-sm text-[var(--color-primary)]" />
                  <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                    {t('rum.errors.detail.attributes', '问题属性与诊断')}
                  </h2>
                </div>
                <div className="space-y-2 p-3 text-xs">
                  <div className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
                    <span className="text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.filter.application', '所属应用')}</span>
                    <span className="font-medium text-[var(--color-text-1)]">{detail.application || app || '—'}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
                    <span className="text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.errors.type', '异常类型')}</span>
                    <code className="font-mono text-xs font-semibold text-[var(--color-text-1)]">{detail.errorType || 'Error'}</code>
                  </div>
                  <div className="flex items-center justify-between gap-2 rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
                    <span className="shrink-0 text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.errors.fingerprint', '错误指纹')}</span>
                    <div className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--color-text-2)]">
                      <span className="truncate max-w-[170px]" title={detail.fingerprint}>{detail.fingerprint}</span>
                      <Tooltip title={copiedFingerprint ? t('common.copied', '已复制') : t('rum.errors.copyFingerprint', '复制')}>
                        <button
                          type="button"
                          onClick={handleCopyFingerprint}
                          className="inline-flex size-4 shrink-0 items-center justify-center rounded text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
                          aria-label="copy-fingerprint-meta"
                        >
                          {copiedFingerprint ? (
                            <CheckOutlined className="text-[10px] text-[var(--color-success)]" />
                          ) : (
                            <CopyOutlined className="text-[10px]" />
                          )}
                        </button>
                      </Tooltip>
                    </div>
                  </div>
                  <div className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
                    <span className="text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.errors.status', '当前状态')}</span>
                    <SemanticBadge
                      label={t(`rum.errors.statusLabel.${statusLabel}`, statusLabel)}
                      {...toneSemanticPalette(statusTone[statusLabel] || 'neutral')}
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
                    <span className="text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.releases.release', '发布版本')}</span>
                    <span className="font-mono text-[var(--color-text-2)]">{detail.lastRelease || '—'}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
                    <span className="text-[11px] font-medium text-[var(--color-text-3)]">{t('rum.errors.lastSeen', '最近出现')}</span>
                    <span className="font-mono tabular-nums text-[var(--color-text-2)]">{formatWhen(detail.lastSeen)}</span>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
