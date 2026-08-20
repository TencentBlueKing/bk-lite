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
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
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
import styles from '@/app/apm/events/event-workspace.module.scss';

type PageState = CatalogStateKind | 'ready';
type AlertView = 'active' | 'history';
const ALERT_LIST_LIMIT = 100;
const HISTORY_RANGE_MS = 604_800_000;
const HISTORY_TIME_DEFAULT = { selectValue: 10080, rangePickerVaule: null };
const SEVERITY_COLOR: Record<ApmPolicySeverity, string> = { critical: 'red', error: 'orange', warning: 'gold' };
const SEVERITY_LABEL: Record<ApmPolicySeverity, string> = { critical: '严重', error: '错误', warning: '警告' };
const METRIC_LABEL: Record<ApmAlert['metric_type'], string> = {
  error_rate: '错误率',
  p95: 'P95 时延',
  p99: 'P99 时延',
  throughput: '吞吐',
  no_traffic: '无流量',
};
const NOTIFICATION_LABEL = {
  none: '未通知',
  pending: '投递中',
  delivered: '已通知',
  partial: '部分失败',
  failed: '投递失败',
} as const;

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
      message.success('已重新投递');
      if (selected && selectedEvent) chooseEvent(selected, selectedEvent);
    } catch {
      message.error('重投失败，请稍后重试');
    } finally {
      setRetryingDeliveryId(null);
    }
  };

  const handleCloseAlert = async (alert: ApmAlert) => {
    await closeAlert(alert.id);
    message.success('告警已关闭');
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

  const chartRows = useMemo(() => {
    const series = eventEvidence?.payload?.series ?? [];
    const threshold = eventEvidence?.evaluation_snapshot.threshold;
    const eventAt = new Date(eventEvidence?.occurred_at ?? 0).getTime();
    let closest = -1;
    let distance = Number.POSITIVE_INFINITY;
    series.forEach((point, index) => {
      const next = Math.abs(new Date(point.timestamp).getTime() - eventAt);
      if (next < distance) {
        closest = index;
        distance = next;
      }
    });
    return series.map((point, index) => ({
      timestamp: point.timestamp,
      value: point.value,
      threshold: threshold == null ? null : Number(threshold),
      event:
        index === closest && eventEvidence?.evaluation_snapshot.value != null
          ? Number(eventEvidence.evaluation_snapshot.value)
          : null,
    }));
  }, [eventEvidence]);
  const snapshotTimeFormat = useMemo(() => {
    const minuteLabels = chartRows.map((row) => dayjs(row.timestamp).format('HH:mm'));
    return new Set(minuteLabels).size < minuteLabels.length ? 'HH:mm:ss' : 'HH:mm';
  }, [chartRows]);

  const columns: TableColumnsType<ApmAlert> = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value) => {
        const severity = value as ApmPolicySeverity;
        return <Tag bordered={false} className="m-0" color={SEVERITY_COLOR[severity]}>{SEVERITY_LABEL[severity]}</Tag>;
      },
    },
    {
      title: '触发时间',
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (value) => (
        <span className={styles.alertTimeCell}>
          {dayjs(value).format('YYYY-MM-DD HH:mm')}
        </span>
      ),
    },
    {
      title: '告警标题',
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
      title: '指标',
      dataIndex: 'metric_type',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      render: (value, item) => (
        <Tag bordered={false} className="m-0" color={SEVERITY_COLOR[item.severity]}>{METRIC_LABEL[value as ApmAlert['metric_type']]}</Tag>
      ),
    },
    {
      title: '服务 / 端点',
      render: (_, item) => (
        <div className={styles.alertServiceCell}>
          <span className={styles.alertServiceName} title={item.service_name}>{item.service_name}</span>
          <Typography.Text type="secondary" className={styles.alertServiceScope} title={item.endpoint || '全部端点'}>
            {item.endpoint || '全部端点'}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: '通知',
      dataIndex: 'notification_status',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      render: (value) => {
        const status = (value || 'none') as NonNullable<ApmAlert['notification_status']>;
        if (status === 'none') return <Typography.Text type="secondary">{NOTIFICATION_LABEL.none}</Typography.Text>;
        const color = status === 'delivered' ? 'success' : status === 'pending' ? 'processing' : 'warning';
        return (
          <Tag
            bordered={false}
            className="m-0"
            color={status === 'failed' ? 'error' : color}
            icon={status === 'delivered' ? <CheckOutlined /> : undefined}
          >
            {NOTIFICATION_LABEL[status]}
          </Tag>
        );
      },
    },
    {
      title: '处置人',
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
      title: '操作',
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
            详情
          </Button>
          <Popconfirm
            title="确定关闭此告警？"
            description="关闭后会追加人工关闭事件，确认继续？"
            okText="确定"
            cancelText="取消"
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
              关闭
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="告警"
      description="Alert 聚合完整生命周期；Event 记录触发、升级、恢复与人工关闭。"
      dependency="control"
    >
      <ApmSurface>
        <div className="flex flex-col gap-4">
        <Tabs
          className={styles.alertsViewTabs}
          activeKey={activeTab}
          onChange={handleViewChange}
          items={[
            { key: 'active', label: '活跃告警' },
            { key: 'history', label: '历史告警' },
          ]}
        />

        <section className={`${styles.alertsContent} flex flex-col gap-4`} aria-label="告警工作区">
          <section className={styles.alertsToolbar} aria-label="告警筛选">
            <div className={styles.alertsToolbarActions}>
              <Input
                allowClear
                aria-label="搜索告警"
                placeholder="搜索告警标题 / 服务 / 规则"
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
                刷新
              </Button>
            </div>
          </section>

          <section className={styles.alertsDistribution} aria-label="告警分布">
            <Collapse
              title="分布图"
              isOpen={chartExpanded}
              onToggle={setChartExpanded}
              titleClassName={styles.alertsDistributionCollapseTitle}
              contentClassName={styles.alertsDistributionCollapseContent}
              icon={(
                <div
                  className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs"
                  aria-label="三级告警数量"
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
                          {SEVERITY_LABEL[level]}
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
              <div
                className={styles.alertsDistributionChart}
                role="img"
                aria-label={`${activeTab === 'active' ? '活跃' : '历史'}告警事件分布，按严重、错误、警告分组`}
              >
                <TimeSeriesComposedChart
                  data={distribution}
                  xDataKey="time"
                  getXLabel={(item) => dayjs(String(item.time)).format('YYYY-MM-DD HH:mm')}
                  series={[
                    {
                      name: '严重',
                      type: 'bar',
                      dataKey: 'critical',
                      color: ALERT_LEVEL_COLORS.critical,
                      stack: 'severity',
                      barGradient: false,
                      barMaxWidth: 32,
                      barBorderRadius: [0, 0, 0, 0],
                    },
                    {
                      name: '错误',
                      type: 'bar',
                      dataKey: 'error',
                      color: ALERT_LEVEL_COLORS.error,
                      stack: 'severity',
                      barGradient: false,
                      barMaxWidth: 32,
                      barBorderRadius: [0, 0, 0, 0],
                    },
                    {
                      name: '警告',
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
            </Collapse>
          </section>

          <section className={styles.alertsTableSection} aria-label="告警列表">
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
                    最多显示 {ALERT_LIST_LIMIT} 条，请缩小筛选范围
                  </Typography.Text>
                ) : null}
              </>
            ) : (
              <CatalogState kind={state === 'ready' ? 'empty' : state} onRetry={load} />
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
        chartRows={chartRows}
        snapshotTimeFormat={snapshotTimeFormat}
        onClose={resetDrawerState}
        onCloseAlert={handleCloseAlert}
        onRetrySnapshot={openDrawer}
        onSelectEvent={chooseEvent}
        onRetryDelivery={handleRetryDelivery}
      />
    </ApmRouteShell>
  );
}
