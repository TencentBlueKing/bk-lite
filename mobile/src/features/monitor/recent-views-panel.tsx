'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MonitorObjectIcon from '@/features/monitor/object-icon-image';
import {
  RECENT_VIEW_SUMMARY_LIMIT,
  formatRecentViewTime,
  instanceSummaryEntries,
  resolveMonitorReportingStatus,
} from '@/features/monitor/model';
import { useRecentViews } from '@/features/monitor/use-recent-views';
import { useAuth } from '@/context/auth';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import {
  readMobileViewSnapshot,
  restoreMobileViewScroll,
  writeMobileViewSnapshot,
} from '@/navigation/mobile-view-cache';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/monitor/monitor.module.css';

interface MonitorRecentViewsViewState {
  entryKeys: string[];
}

function entryKey(objectId: number, instanceId: string) {
  return `${objectId}:${instanceId}`;
}

export default function MonitorRecentViewsPanel() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const { entries, status, reload } = useRecentViews();
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const initialSnapshot = useRef(readMobileViewSnapshot<MonitorRecentViewsViewState>(cacheScope, 'monitor-recent'));
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };
  const viewedAtLabels = {
    justNow: t('monitor.viewedAtJustNow'),
    minutes: t('monitor.viewedAtMinutes'),
    hours: t('monitor.viewedAtHours'),
    yesterday: t('monitor.viewedAtYesterday'),
  };

  useEffect(() => {
    restoreMobileViewScroll(scrollRef.current, initialSnapshot.current?.scrollTop);
  }, []);

  useEffect(() => {
    if (status !== 'ready') return;
    writeMobileViewSnapshot<MonitorRecentViewsViewState>(
      cacheScope,
      'monitor-recent',
      { entryKeys: entries.map((entry) => entryKey(entry.object.id, entry.instance.id)) },
      scrollRef.current?.scrollTop || 0,
    );
  }, [cacheScope, entries, status]);

  return (
    <div className={styles.recentPanel}>
      <div
        className={styles.scroll}
        ref={scrollRef}
        onScroll={(event) => {
          if (status !== 'ready') return;
          writeMobileViewSnapshot<MonitorRecentViewsViewState>(
            cacheScope,
            'monitor-recent',
            { entryKeys: entries.map((entry) => entryKey(entry.object.id, entry.instance.id)) },
            event.currentTarget.scrollTop,
          );
        }}
      >
        <MobilePullToRefresh
          disabled={status === 'loading'}
          onRefresh={() => reload(undefined, true).catch(() => undefined)}
        >
          <div className={styles.refreshContent}>
            {status === 'loading' ? (
              <MobileSkeleton label={t('common.loading')} variant="list" rows={4} />
            ) : status === 'error' ? (
              <MobileResult
                kind="error"
                title={t('monitor.recentLoadFailed')}
                description={t('monitor.retryHint')}
                actionLabel={t('common.retry')}
                onAction={() => void reload().catch(() => undefined)}
              />
            ) : entries.length === 0 ? (
              <MobileResult
                kind="empty"
                title={t('monitor.noRecentViews')}
                description={t('monitor.noRecentViewsHint')}
              />
            ) : (
              <div className={styles.recentList}>
                {entries.map(({ item, object, instance, metricUnits }) => {
                  const reportingStatus = resolveMonitorReportingStatus(instance.status);
                  const summaryEntries = instanceSummaryEntries(
                    object,
                    instance,
                    RECENT_VIEW_SUMMARY_LIMIT,
                    metricUnits,
                  );
                  const detailParams = new URLSearchParams({
                    objectId: String(object.id),
                    objectName: object.displayName,
                    objectIcon: object.icon || '',
                    instanceId: instance.id,
                    instanceName: instance.name,
                    idValues: JSON.stringify(instance.idValues),
                    interval: String(instance.interval || ''),
                    status: instance.status,
                    lastReportedAt: String(instance.lastReportedAt || ''),
                    returnTab: 'recent',
                  });
                  return (
                    <Link
                      key={entryKey(object.id, instance.id)}
                      className={styles.recentRow}
                      href={`/monitor/detail?${detailParams.toString()}`}
                    >
                      <MonitorObjectIcon
                        className={styles.recentRowIcon}
                        icon={object.icon}
                        size={26}
                      />
                      <span className={styles.recentBody}>
                        <span className={styles.recentTitleRow}>
                          <span className={styles.instanceName}>
                            {instance.name}
                          </span>
                          <span className={styles.recentViewedAt}>
                            {formatRecentViewTime(
                              item.viewedAt,
                              preferences,
                              viewedAtLabels,
                            )}
                          </span>
                        </span>
                        {reportingStatus === 'unavailable' && instance.lastReportedAt ? (
                          <span className={styles.recentLastReported}>
                            {t('monitor.lastReportedLabel', undefined, {
                              time: formatAccountDateTime(
                                new Date(instance.lastReportedAt * 1000).toISOString(),
                                preferences,
                              ),
                            })}
                          </span>
                        ) : null}
                        <span className={styles.recentMetaLine}>
                          <span className={styles.recentMetaObject}>
                            {object.displayName}
                          </span>
                          {reportingStatus ? (
                            <>
                              <span className={styles.recentMetaSep} aria-hidden>
                                ·
                              </span>
                              <span
                                className={styles.recentStatusText}
                                data-status={reportingStatus}
                              >
                                {t(`monitor.reportingStatus.${reportingStatus}`)}
                              </span>
                            </>
                          ) : null}
                        </span>
                        {summaryEntries.length > 0 ? (
                          <span className={styles.recentMetricsLine}>
                            {summaryEntries.map((entry, index) => (
                              <span
                                key={`${entry.label}-${index}`}
                                className={styles.recentMetricItem}
                              >
                                <span className={styles.recentMetricLabel}>
                                  {entry.label}
                                </span>{' '}
                                <span className={styles.recentMetricValue}>
                                  {entry.value}
                                </span>
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </span>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </MobilePullToRefresh>
      </div>
    </div>
  );
}
