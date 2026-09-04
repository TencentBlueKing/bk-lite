'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Avatar,
  Button,
  Input,
  message,
  Popconfirm,
  Space,
  Tabs,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { formatDateTime } from '@/app/apm/components/metric-format';
import Collapse from '@/components/collapse';
import TimeSelector from '@/components/time-selector';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { ALERT_LEVEL_COLORS } from '@/constants/observabilityChart';
import type {
  ApmAlert,
  ApmAlertMetricSnapshot,
  ApmAlertEvent,
  ApmAlertQuery,
  ApmEventSnapshot,
  ApmNotificationDelivery,
  ApmPolicySeverity,
} from '@/app/apm/types';
import AlertDetailDrawer from '@/app/apm/events/alerts/alert-detail-drawer';
import { useTranslation } from '@/utils/i18n';
import styles from '@/app/apm/events/event-workspace.module.scss';

type PageState = CatalogStateKind | 'ready';
type AlertView = 'active' | 'history';
const ALERT_LIST_LIMIT = 100;
const HISTORY_RANGE_MS = 604_800_000;
const HISTORY_TIME_DEFAULT = { selectValue: 10080, rangePickerVaule: null };
const SEVERITY_COLOR: Record<ApmPolicySeverity, string> = { critical: 'red', error: 'orange', warning: 'gold' };
const SEVERITY_KEY: Record<ApmPolicySeverity, string> = {
  critical: 'apm.severity.critical',
  error: 'apm.severity.error',
  warning: 'apm.severity.warning',
};
const METRIC_KEY: Record<ApmAlert['metric_type'], string> = {
  error_rate: 'apm.common.errorRate',
  p95: 'apm.common.p95Latency',
  p99: 'apm.common.p99Latency',
  throughput: 'apm.common.throughput',
  no_traffic: 'apm.alerts.noTraffic',
};

function resolveTimeParams(view: AlertView, historyTimeRange: [number, number] | null) {
  if (view === 'active') {
    return {};
  }
  if (view === 'history' && historyTimeRange) {
    return {
      started_at: new Date(historyTimeRange[0]).toISOString(),
      ended_at: new Date(historyTimeRange[1]).toISOString(),
    };
  }
  const endedAt = new Date();
  return {
    started_at: new Date(endedAt.getTime() - HISTORY_RANGE_MS).toISOString(),
    ended_at: endedAt.toISOString(),
  };
}

export default function ApmAlertsPage() {
  const { t } = useTranslation();
  const {
    closeAlert,
    getAlertDistribution,
    getAlerts,
    getAlertSnapshots,
    getEventEvidence,
    getNotificationDeliveries,
    retryNotificationDelivery,
    isLoading: authLoading,
  } = useApmApi();
  const [allAlerts, setAllAlerts] = useState<ApmAlert[]>([]);
  const [distribution, setDistribution] = useState<
    Array<{ time: string; critical: number; error: number; warning: number }>
  >([]);
  const [state, setState] = useState<PageState>('loading');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [chartExpanded, setChartExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<AlertView>('active');
  const [historyTimeRange, setHistoryTimeRange] = useState<[number, number] | null>(null);
  const [keyword, setKeyword] = useState('');
  const [submittedKeyword, setSubmittedKeyword] = useState('');
  const [selected, setSelected] = useState<ApmAlert | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<ApmAlertEvent | null>(null);
  const [eventEvidence, setEventEvidence] = useState<ApmEventSnapshot | null>(null);
  const [metricSnapshot, setMetricSnapshot] = useState<ApmAlertMetricSnapshot | null>(null);
  const [metricSnapshotLoading, setMetricSnapshotLoading] = useState(false);
  const [metricSnapshotError, setMetricSnapshotError] = useState<CatalogStateKind | null>(null);
  const [deliveries, setDeliveries] = useState<ApmNotificationDelivery[]>([]);
  const [retryingDeliveryId, setRetryingDeliveryId] = useState<string | null>(null);
  const [eventEvidenceLoading, setEventEvidenceLoading] = useState(false);
  const loadSequence = useRef(0);
  const snapshotLoadSequence = useRef(0);

  const load = useCallback(() => {
    if (authLoading) return;
    const sequence = loadSequence.current + 1;
    loadSequence.current = sequence;
    setIsRefreshing(true);
    setState((current) => current === 'ready' ? current : 'loading');
    const timeParams = resolveTimeParams(activeTab, historyTimeRange);
    const query: ApmAlertQuery = {
      ...timeParams,
      status_group: activeTab,
      limit: ALERT_LIST_LIMIT,
      keyword: submittedKeyword,
    };
    Promise.all([getAlerts(query), getAlertDistribution({ ...timeParams, status_group: activeTab })])
      .then(([items, buckets]) => {
        if (sequence !== loadSequence.current) return;
        setAllAlerts(items);
        setDistribution(buckets);
        setState(items.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (sequence === loadSequence.current) setState(catalogErrorKind(error));
      })
      .finally(() => {
        if (sequence === loadSequence.current) setIsRefreshing(false);
      });
  }, [activeTab, authLoading, getAlertDistribution, getAlerts, historyTimeRange, submittedKeyword]);

  useEffect(() => load(), [load]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSubmittedKeyword(keyword.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  const alerts = allAlerts;
  const distributionTotals = useMemo(
    () => distribution.reduce(
      (totals, bucket) => ({
        critical: totals.critical + bucket.critical,
        error: totals.error + bucket.error,
        warning: totals.warning + bucket.warning,
      }),
      { critical: 0, error: 0, warning: 0 },
    ),
    [distribution],
  );

  const chooseEvent = useCallback(
    (alert: ApmAlert, event: ApmAlertEvent) => {
      setSelectedEvent(event);
      setEventEvidence(null);
      setDeliveries([]);
      setEventEvidenceLoading(true);
      Promise.all([
        getEventEvidence(alert.id, event.event_id),
        getNotificationDeliveries({ event_id: event.event_id }),
      ])
        .then(([snapshots, deliveryItems]) => {
          setEventEvidence(snapshots[0] ?? null);
          setDeliveries(deliveryItems);
        })
        .finally(() => setEventEvidenceLoading(false));
    },
    [getEventEvidence, getNotificationDeliveries],
  );

  const resetDrawerState = useCallback(() => {
    snapshotLoadSequence.current += 1;
    setSelected(null);
    setSelectedEvent(null);
    setEventEvidence(null);
    setMetricSnapshot(null);
    setMetricSnapshotError(null);
    setMetricSnapshotLoading(false);
    setEventEvidenceLoading(false);
    setDeliveries([]);
    setRetryingDeliveryId(null);
  }, []);

  const openDrawer = (alert: ApmAlert) => {
    const snapshotSequence = snapshotLoadSequence.current + 1;
    snapshotLoadSequence.current = snapshotSequence;
    setSelected(alert);
    setMetricSnapshot(null);
    setMetricSnapshotError(null);
    setMetricSnapshotLoading(true);
    getAlertSnapshots(alert.id)
      .then((snapshot) => {
        if (snapshotSequence !== snapshotLoadSequence.current) return;
        setMetricSnapshot(snapshot);
      })
      .catch((error) => {
        if (snapshotSequence === snapshotLoadSequence.current) {
          setMetricSnapshotError(catalogErrorKind(error));
        }
      })
      .finally(() => {
        if (snapshotSequence === snapshotLoadSequence.current) setMetricSnapshotLoading(false);
      });
    const event = alert.events.at(-1) ?? null;
    if (event) chooseEvent(alert, event);
  };

  const handleRetryDelivery = async (deliveryId: string) => {
    setRetryingDeliveryId(deliveryId);
    try {
      await retryNotificationDelivery(deliveryId);
      message.success(t('apm.alerts.retrySuccess', '已重新投递'));
      if (selected && selectedEvent) chooseEvent(selected, selectedEvent);
    } catch {
      message.error(t('apm.alerts.retryFailed', '重投失败，请稍后重试'));
    } finally {
      setRetryingDeliveryId(null);
    }
  };

  const handleCloseAlert = async (alert: ApmAlert) => {
    await closeAlert(alert.id);
    message.success(t('apm.alerts.closed', '告警已关闭'));
    if (selected?.id === alert.id) {
      resetDrawerState();
    }
    load();
  };

  const handleViewChange = (key: string) => {
    const nextView = key as AlertView;
    if (nextView === activeTab) return;
    if (nextView === 'history') {
      setHistoryTimeRange(null);
    }
    setActiveTab(nextView);
    setAllAlerts([]);
    setDistribution([]);
    setState('loading');
    resetDrawerState();
  };

  const columns: TableColumnsType<ApmAlert> = [
    {
      title: t('apm.alerts.level', '级别'),
      dataIndex: 'severity',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value) => {
        const severity = value as ApmPolicySeverity;
        return <Tag bordered={false} className="m-0" color={SEVERITY_COLOR[severity]}>{t(SEVERITY_KEY[severity])}</Tag>;
      },
    },
    {
      title: t('apm.alerts.triggeredAt', '触发时间'),
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (value) => (
        <span className={styles.alertTimeCell}>
          {formatDateTime(value, false)}
        </span>
      ),
    },
    {
      title: t('apm.alerts.alertTitle', '告警标题'),
      dataIndex: 'title',
      ellipsis: true,
      render: (_, item) => (
        <Button
          type="link"
          size="small"
          className={styles.alertTitleLink}
          title={item.title}
          onClick={(event) => {
            event.stopPropagation();
            openDrawer(item);
          }}
        >
          {item.title}
        </Button>
      ),
    },
    {
      title: t('apm.policies.metric', '指标'),
      dataIndex: 'metric_type',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      render: (value, item) => (
        <Tag bordered={false} className="m-0" color={SEVERITY_COLOR[item.severity]}>{t(METRIC_KEY[value as ApmAlert['metric_type']])}</Tag>
      ),
    },
    {
      title: t('apm.alerts.serviceEndpoint', '服务 / 端点'),
      render: (_, item) => (
        <div className={styles.alertServiceCell}>
          <span className={styles.alertServiceName} title={item.service_name}>{item.service_name}</span>
          <Typography.Text type="secondary" className={styles.alertServiceScope} title={item.endpoint || t('apm.alerts.allEndpoints', '全部端点')}>
            {item.endpoint || t('apm.alerts.allEndpoints', '全部端点')}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('apm.alerts.notification', '通知'),
      dataIndex: 'notification_status',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      render: (value) => {
        const status = (value || 'none') as NonNullable<ApmAlert['notification_status']>;
        if (status === 'none') return <Typography.Text type="secondary">{t('apm.alerts.notificationNone', '未通知')}</Typography.Text>;
        const color = status === 'delivered' ? 'success' : status === 'pending' ? 'processing' : 'warning';
        return (
          <Tag
            bordered={false}
            className="m-0"
            color={status === 'failed' ? 'error' : color}
            icon={status === 'delivered' ? <CheckOutlined /> : undefined}
          >
            {t(`apm.alerts.notification${status[0].toUpperCase()}${status.slice(1)}`)}
          </Tag>
        );
      },
    },
    {
      title: t('apm.alerts.operator', '处置人'),
      dataIndex: 'operator',
      width: APM_TABLE_COLUMN_WIDTHS.organization,
      ellipsis: true,
      render: (value) => value ? (
        <Space size={8} className={styles.alertOperatorCell}>
          <Avatar size={24}>{String(value).slice(0, 1).toUpperCase()}</Avatar>
          <Typography.Text ellipsis={{ tooltip: String(value) }}>{String(value)}</Typography.Text>
        </Space>
      ) : <Typography.Text type="secondary">--</Typography.Text>,
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'actions',
      width: APM_TABLE_COLUMN_WIDTHS.actionPair,
      fixed: 'right',
      render: (_, item) => (
        <Space size={4} className={styles.alertOperationCell}>
          <Button
            type="link"
            size="small"
            onClick={(event) => {
              event.stopPropagation();
              openDrawer(item);
            }}
          >
            {t('apm.alerts.detailAction', '详情')}
          </Button>
          <Popconfirm
            title={t('apm.alerts.closeConfirm', '确定关闭此告警？')}
            description={t('apm.alerts.closeConfirmDescription', '关闭后会追加人工关闭事件，确认继续？')}
            okText={t('apm.alerts.confirmAction', '确定')}
            cancelText={t('common.cancel', '取消')}
            disabled={item.status !== 'active'}
            onConfirm={() => handleCloseAlert(item)}
          >
            <Button
              type="link"
              danger
              size="small"
              disabled={item.status !== 'active'}
              onClick={(event) => event.stopPropagation()}
            >
              {t('apm.common.close', '关闭')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title={t('apm.alerts.title', '告警')}
      description={t('apm.alerts.lifecycleDescription', 'Alert 聚合完整生命周期；Event 记录触发、升级、恢复与人工关闭。')}
      dependency="control"
    >
      <ApmSurface>
        <div className="flex flex-col gap-4">
        <Tabs
          className={styles.alertsViewTabs}
          activeKey={activeTab}
          onChange={handleViewChange}
          items={[
            { key: 'active', label: t('apm.alerts.active', '活跃告警') },
            { key: 'history', label: t('apm.alerts.history', '历史告警') },
          ]}
        />

        <section className={`${styles.alertsContent} flex flex-col gap-4`} aria-label={t('apm.alerts.workspace', '告警工作区')}>
          <section className={styles.alertsToolbar} aria-label={t('apm.alerts.filters', '告警筛选')}>
            <div className={styles.alertsToolbarActions}>
              <Input
                allowClear
                aria-label={t('apm.alerts.listSearchAria', '搜索告警')}
                placeholder={t('apm.alerts.searchPlaceholder', '搜索告警标题 / 服务 / 规则')}
                prefix={<SearchOutlined aria-hidden="true" />}
                value={keyword}
                onChange={(event) => {
                  const value = event.target.value;
                  setKeyword(value);
                  if (!value) setSubmittedKeyword('');
                }}
                onPressEnter={() => setSubmittedKeyword(keyword.trim())}
              />
              {activeTab === 'history' ? (
                <TimeSelector
                  className={styles.alertsHistoryTimeSelector}
                  defaultValue={HISTORY_TIME_DEFAULT}
                  onlyTimeSelect
                  onChange={(values) => {
                    if (values.length === 2) {
                      setHistoryTimeRange([values[0], values[1]]);
                    }
                  }}
                />
              ) : null}
              <Button icon={<ReloadOutlined />} loading={isRefreshing} onClick={load}>
                {t('apm.common.refresh', '刷新')}
              </Button>
            </div>
          </section>

          <section className={styles.alertsDistribution} aria-label={t('apm.alerts.distributionSection', '告警分布')}>
            <Collapse
              title={t('apm.alerts.distributionChart', '分布图')}
              isOpen={chartExpanded && distribution.length > 0}
              onToggle={(open) => {
                if (distribution.length > 0) setChartExpanded(open);
              }}
              titleClassName={styles.alertsDistributionCollapseTitle}
              contentClassName={styles.alertsDistributionCollapseContent}
              icon={(
                <div
                  className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs"
                  aria-label={t('apm.alerts.severityCounts', '三级告警数量')}
                >
                  {(['critical', 'error', 'warning'] as const).map((level, index) => {
                    const count = distributionTotals[level];
                    const idle = count === 0;
                    return (
                      <span key={level} className="inline-flex items-center gap-2.5">
                        {index > 0 ? (
                          <span className="text-[var(--color-text-4)]" aria-hidden="true">·</span>
                        ) : null}
                        <span
                          className={`inline-flex items-center gap-1.5 ${
                            idle ? 'text-[var(--color-text-4)]' : 'text-[var(--color-text-3)]'
                          }`}
                        >
                          <span
                            aria-hidden="true"
                            className={`h-1.5 w-1.5 rounded-full ${idle ? 'opacity-50' : ''}`}
                            style={{ background: ALERT_LEVEL_COLORS[level] }}
                          />
                          {t(SEVERITY_KEY[level])}
                          {' '}
                          <span className={`tabular-nums ${idle ? '' : 'font-medium text-[var(--color-text-1)]'}`}>
                            {count}
                          </span>
                        </span>
                      </span>
                    );
                  })}
                </div>
              )}
            >
              {distribution.length ? (
                <div
                  className={styles.alertsDistributionChart}
                  role="img"
                  aria-label={t('apm.alerts.distributionDetailAria', '{view} alert event distribution grouped by critical, error, and warning', {
                    view: t(activeTab === 'active' ? 'apm.alerts.active' : 'apm.alerts.history'),
                  })}
                >
                  <TimeSeriesComposedChart
                    data={distribution}
                    xDataKey="time"
                    getXLabel={(item) => formatDateTime(String(item.time), false)}
                    series={[
                      {
                        name: t('apm.severity.critical', '严重'),
                        type: 'bar',
                        dataKey: 'critical',
                        color: ALERT_LEVEL_COLORS.critical,
                        stack: 'severity',
                        barGradient: false,
                        barMaxWidth: 32,
                        barBorderRadius: [0, 0, 0, 0],
                      },
                      {
                        name: t('apm.severity.error', '错误'),
                        type: 'bar',
                        dataKey: 'error',
                        color: ALERT_LEVEL_COLORS.error,
                        stack: 'severity',
                        barGradient: false,
                        barMaxWidth: 32,
                        barBorderRadius: [0, 0, 0, 0],
                      },
                      {
                        name: t('apm.severity.warning', '警告'),
                        type: 'bar',
                        dataKey: 'warning',
                        color: ALERT_LEVEL_COLORS.warning,
                        stack: 'severity',
                        barGradient: false,
                        barMaxWidth: 32,
                        barBorderRadius: [3, 3, 0, 0],
                      },
                    ]}
                  />
                </div>
              ) : null}
            </Collapse>
          </section>

          <section className={styles.alertsTableSection} aria-label={t('apm.alerts.list', '告警列表')}>
            {state === 'ready' && alerts.length ? (
              <>
                <ApmDataTable
                  rowKey="id"
                  columns={columns}
                  dataSource={alerts}
                  pagination={{ pageSize: 20 }}
                />
                {alerts.length >= ALERT_LIST_LIMIT ? (
                  <Typography.Text type="secondary" className="mt-2 block">
                    {t('apm.alerts.limitHint', '最多显示 {limit} 条，请缩小筛选范围', { limit: ALERT_LIST_LIMIT })}
                  </Typography.Text>
                ) : null}
              </>
            ) : (
              <CatalogState
                kind={state === 'ready' ? 'empty' : state}
                description={t(
                  activeTab === 'active' ? 'apm.alerts.emptyActive' : 'apm.alerts.emptyHistory',
                  activeTab === 'active' ? '暂无活跃告警数据' : '暂无历史告警数据',
                )}
                onRetry={state === 'empty' || state === 'ready' ? undefined : load}
              />
            )}
          </section>
        </section>
        </div>
      </ApmSurface>
      <AlertDetailDrawer
        open={Boolean(selected)}
        alert={selected}
        metricSnapshot={metricSnapshot}
        metricSnapshotLoading={metricSnapshotLoading}
        metricSnapshotError={metricSnapshotError}
        selectedEvent={selectedEvent}
        eventEvidence={eventEvidence}
        eventEvidenceLoading={eventEvidenceLoading}
        deliveries={deliveries}
        retryingDeliveryId={retryingDeliveryId}
        onClose={resetDrawerState}
        onCloseAlert={handleCloseAlert}
        onRetrySnapshot={openDrawer}
        onSelectEvent={chooseEvent}
        onRetryDelivery={handleRetryDelivery}
      />
    </ApmRouteShell>
  );
}
