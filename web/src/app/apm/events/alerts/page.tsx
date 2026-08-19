'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Alert as AntAlert,
  Avatar,
  Button,
  Descriptions,
  Drawer,
  Input,
  message,
  Popconfirm,
  Space,
  Tabs,
  Tag,
  Timeline,
  Typography,
  theme,
  type TableColumnsType,
} from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import Collapse from '@/components/collapse';
import TimeSelector from '@/components/time-selector';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { ALERT_LEVEL_COLORS, OBSERVABILITY_SERIES_COLORS } from '@/constants/observabilityChart';
import type {
  ApmAlert,
  ApmAlertMetricSnapshot,
  ApmAlertEvent,
  ApmAlertQuery,
  ApmEventSnapshot,
  ApmNotificationDelivery,
  ApmPolicySeverity,
} from '@/app/apm/types';
import styles from '@/app/apm/events/event-workspace.module.scss';

type PageState = CatalogStateKind | 'ready';
type AlertView = 'active' | 'history';
const HISTORY_RANGE_MS = 604_800_000;
const HISTORY_TIME_DEFAULT = { selectValue: 10080, rangePickerVaule: null };
const ACTION_LABEL = { triggered: '触发', escalated: '级别升级', recovered: '恢复', closed: '人工关闭' } as const;
const STATUS_LABEL = { active: '告警中', recovered: '已恢复', closed: '已关闭' } as const;
const STATUS_COLOR = { active: 'error', recovered: 'success', closed: 'default' } as const;
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
  const { token } = theme.useToken();
  const {
    closeAlert,
    getAlertDistribution,
    getAlerts,
    getAlertSnapshots,
    getEventEvidence,
    getNotificationDeliveries,
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
      limit: 100,
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
  const metricSnapshotRows = useMemo(
    () => (metricSnapshot?.snapshots ?? []).map((item) => ({
      timestamp: item.snapshot_time,
      value: item.value == null ? null : Number(item.value),
      threshold: item.threshold == null || item.threshold.value === '' ? null : Number(item.threshold.value),
      event: item.type === 'event' ? Number(item.value ?? item.threshold?.value ?? 0) : null,
    })),
    [metricSnapshot],
  );
  const metricSnapshotTimeFormat = useMemo(() => {
    const days = new Set(metricSnapshotRows.map((row) => dayjs(row.timestamp).format('YYYY-MM-DD')));
    return days.size > 1 ? 'MM-DD HH:mm' : 'HH:mm';
  }, [metricSnapshotRows]);

  const columns: TableColumnsType<ApmAlert> = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value) => {
        const severity = value as ApmPolicySeverity;
        return <Tag color={SEVERITY_COLOR[severity]}>{SEVERITY_LABEL[severity]}</Tag>;
      },
    },
    {
      title: '触发时间',
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (value) => (
        <span className={styles.alertTimeCell}>
          <ClockCircleOutlined aria-hidden="true" />
          {dayjs(value).format('YYYY-MM-DD HH:mm')}
        </span>
      ),
    },
    {
      title: '告警标题',
      dataIndex: 'title',
      render: (_, item) => (
        <Button
          type="link"
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
        <Tag color={SEVERITY_COLOR[item.severity]}>{METRIC_LABEL[value as ApmAlert['metric_type']]}</Tag>
      ),
    },
    {
      title: '服务 / 端点',
      width: 208,
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
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      render: (value) => {
        const status = (value || 'none') as NonNullable<ApmAlert['notification_status']>;
        if (status === 'none') return <Typography.Text type="secondary">{NOTIFICATION_LABEL.none}</Typography.Text>;
        const color = status === 'delivered' ? 'success' : status === 'pending' ? 'processing' : 'warning';
        return (
          <Tag color={status === 'failed' ? 'error' : color} icon={status === 'delivered' ? <CheckOutlined /> : undefined}>
            {NOTIFICATION_LABEL[status]}
          </Tag>
        );
      },
    },
    {
      title: '处置人',
      dataIndex: 'operator',
      width: APM_TABLE_COLUMN_WIDTHS.organization,
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
      spacing="flush"
    >
      <div className={`${styles.workspace} ${styles.alertsWorkspace}`}>
        <Tabs
          className={styles.alertsViewTabs}
          activeKey={activeTab}
          onChange={handleViewChange}
          items={[
            { key: 'active', label: '活跃告警' },
            { key: 'history', label: '历史告警' },
          ]}
        />

        <section className={styles.alertsContent} aria-label="告警工作区">
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
                <div className={styles.alertsSeveritySummary} aria-label="三级告警数量">
                  <Typography.Text type="secondary">级别：</Typography.Text>
                  <Tag color={ALERT_LEVEL_COLORS.critical}>严重 {distributionTotals.critical}</Tag>
                  <Tag color={ALERT_LEVEL_COLORS.error}>错误 {distributionTotals.error}</Tag>
                  <Tag color={ALERT_LEVEL_COLORS.warning}>警告 {distributionTotals.warning}</Tag>
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
              <ApmDataTable
                rowKey="id"
                columns={columns}
                dataSource={alerts}
                pagination={{ pageSize: 20 }}
                scroll={{ x: 1248 }}
              />
            ) : (
              <CatalogState kind={state === 'ready' ? 'empty' : state} onRetry={load} />
            )}
          </section>
        </section>
      </div>
      <Drawer
        width={880}
        open={Boolean(selected)}
        onClose={resetDrawerState}
        title={selected?.title}
        extra={
          selected?.status === 'active' ? (
            <Popconfirm
              title="人工关闭会追加 closed 事件和不可变快照，确认继续？"
              onConfirm={() => selected ? handleCloseAlert(selected) : undefined}
            >
              <Button danger icon={<CloseCircleOutlined />}>
                人工关闭
              </Button>
            </Popconfirm>
          ) : null
        }
      >
        {selected ? (
          <Tabs
            items={[
              {
                key: 'alert',
                label: '告警',
                children: (
                  <Space direction="vertical" size="large" className="w-full">
                    <Descriptions
                      bordered
                      size="small"
                      column={2}
                      items={[
                        {
                          key: 'status',
                          label: '生命周期状态',
                          children: <Tag color={STATUS_COLOR[selected.status]}>{STATUS_LABEL[selected.status]}</Tag>,
                        },
                        { key: 'severity', label: '当前级别', children: selected.severity },
                        {
                          key: 'service',
                          label: 'Service',
                          children: `${selected.service_namespace}/${selected.service_name}`,
                        },
                        { key: 'endpoint', label: 'Endpoint', children: selected.endpoint || '全部端点' },
                        { key: 'environment', label: '环境', children: selected.environment },
                        { key: 'version', label: '版本', children: selected.version || '全部版本' },
                        {
                          key: 'started',
                          label: '开始时间',
                          children: dayjs(selected.started_at).format('YYYY-MM-DD HH:mm:ss'),
                        },
                        {
                          key: 'ended',
                          label: '结束时间',
                          children: selected.ended_at ? dayjs(selected.ended_at).format('YYYY-MM-DD HH:mm:ss') : '—',
                        },
                      ]}
                    />
                    <Typography.Title level={5}>告警指标快照</Typography.Title>
                    {metricSnapshotLoading ? (
                      <CatalogState kind="loading" />
                    ) : metricSnapshotError ? (
                      <CatalogState
                        kind={metricSnapshotError}
                        onRetry={() => openDrawer(selected)}
                      />
                    ) : metricSnapshotRows.length && metricSnapshot ? (
                      <Space direction="vertical" size="small" className="w-full">
                        <Typography.Text type="secondary">
                          检测频率 {metricSnapshot.evaluation_interval} 分钟 · 指标窗口{' '}
                          {metricSnapshot.metric_window} 分钟 · 聚合方式 {metricSnapshot.aggregation}
                        </Typography.Text>
                        <div
                          className="h-72"
                          role="img"
                          aria-label="告警生命周期内每次策略评估值与当时阈值"
                        >
                          <TimeSeriesComposedChart
                            data={metricSnapshotRows}
                            xDataKey="timestamp"
                            getXLabel={(item) => dayjs(String(item.timestamp)).format(metricSnapshotTimeFormat)}
                            xAxisBoundaryGap={false}
                            series={[
                              {
                                name: '评估值',
                                type: 'line',
                                dataKey: 'value',
                                color: OBSERVABILITY_SERIES_COLORS[0],
                                showArea: true,
                                areaOpacity: 0.24,
                                smooth: false,
                                lineWidth: 1,
                              },
                              {
                                name: '当时阈值',
                                type: 'line',
                                dataKey: 'threshold',
                                color: ALERT_LEVEL_COLORS[selected.severity],
                                lineWidth: 1,
                              },
                              {
                                name: '生命周期事件',
                                type: 'line',
                                dataKey: 'event',
                                color: token.colorWarning,
                                showSymbol: true,
                                lineWidth: 0,
                              },
                            ]}
                          />
                        </div>
                      </Space>
                    ) : (
                      <CatalogState kind="empty" description="暂无告警指标快照" />
                    )}
                    <Typography.Title level={5}>生命周期事件</Typography.Title>
                    <Timeline
                      items={selected.events.map((event) => ({
                        color: event.id === selectedEvent?.id ? token.colorPrimary : 'gray',
                        children: (
                          <Button
                            type="text"
                            className="h-auto !px-0 text-left"
                            onClick={() => chooseEvent(selected, event)}
                          >
                            <Space direction="vertical" size={0}>
                              <span>
                                {ACTION_LABEL[event.action]} · {event.severity}
                              </span>
                              <Typography.Text type="secondary" className="!text-xs">
                                {dayjs(event.occurred_at).format('YYYY-MM-DD HH:mm:ss')} · {event.value ?? '无数据'}
                              </Typography.Text>
                            </Space>
                          </Button>
                        ),
                      }))}
                    />
                  </Space>
                ),
              },
              {
                key: 'snapshot',
                label: '事件原始数据',
                children: eventEvidenceLoading ? (
                  <CatalogState kind="loading" />
                ) : eventEvidence ? (
                  <Space direction="vertical" size="middle" className="w-full">
                    <AntAlert
                      showIcon
                      type={
                        eventEvidence.payload_status === 'available'
                          ? 'success'
                          : eventEvidence.payload_status === 'expired'
                            ? 'warning'
                            : 'info'
                      }
                      message={
                        eventEvidence.payload_status === 'expired'
                          ? '遥测保留期已过；以下语义快照仍永久可读，指标序列已按保留策略清理。'
                          : eventEvidence.payload_status === 'unavailable'
                            ? '指标序列对象暂不可用；APM Event 与语义证据已持久化，后台将有界重试。'
                            : eventEvidence.payload_status === 'pending'
                              ? '语义快照已持久化，指标序列正在异步写入对象存储。'
                              : '正在展示所选事件发生时的原始指标证据，不会重新查询当前策略。'
                      }
                    />
                    <Typography.Title level={5}>
                      {selectedEvent
                        ? `${ACTION_LABEL[selectedEvent.action]} · ${dayjs(selectedEvent.occurred_at).format('YYYY-MM-DD HH:mm:ss')}`
                        : '事件趋势'}
                    </Typography.Title>
                    <div
                      className="h-72"
                      role="img"
                      aria-label={`事件 ${eventEvidence.event_id} 趋势，评估值 ${eventEvidence.evaluation_snapshot.value ?? '无数据'}，当时阈值 ${eventEvidence.evaluation_snapshot.threshold ?? '无'}`}
                    >
                      <TimeSeriesComposedChart
                        data={chartRows}
                        xDataKey="timestamp"
                        getXLabel={(item) => dayjs(String(item.timestamp)).format(snapshotTimeFormat)}
                        xAxisBoundaryGap={false}
                        series={[
                          {
                            name: '原始指标',
                            type: 'line',
                            dataKey: 'value',
                            color: OBSERVABILITY_SERIES_COLORS[0],
                            showArea: true,
                            areaOpacity: 0.36,
                            smooth: false,
                            lineWidth: 1,
                          },
                          {
                            name: '当时阈值',
                            type: 'line',
                            dataKey: 'threshold',
                            color: ALERT_LEVEL_COLORS[eventEvidence.evaluation_snapshot.severity ?? 'critical'],
                            lineWidth: 1,
                          },
                          {
                            name: '事件发生点',
                            type: 'line',
                            dataKey: 'event',
                            color: token.colorWarning,
                            showSymbol: true,
                            lineWidth: 0,
                          },
                        ]}
                      />
                    </div>
                    <Descriptions
                      bordered
                      size="small"
                      column={2}
                      items={[
                        { key: 'schema', label: 'Schema', children: `v${eventEvidence.schema_version}` },
                        { key: 'event', label: 'event_id', children: eventEvidence.event_id },
                        { key: 'value', label: '评估值', children: eventEvidence.evaluation_snapshot.value ?? '无数据' },
                        {
                          key: 'condition',
                          label: '当时条件',
                          children: `${eventEvidence.evaluation_snapshot.comparator ?? '—'} ${eventEvidence.evaluation_snapshot.threshold ?? '—'} ${eventEvidence.evaluation_snapshot.unit ?? ''}`,
                        },
                        {
                          key: 'policy',
                          label: '策略快照',
                          span: 2,
                          children: (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(eventEvidence.policy_snapshot, null, 2)}
                            </pre>
                          ),
                        },
                        {
                          key: 'object',
                          label: '对象快照',
                          span: 2,
                          children: (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(eventEvidence.object_snapshot, null, 2)}
                            </pre>
                          ),
                        },
                        {
                          key: 'trace',
                          label: 'Trace 检索上下文',
                          span: 2,
                          children: (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(eventEvidence.trace_context, null, 2)}
                            </pre>
                          ),
                        },
                      ]}
                    />
                    <Typography.Title level={5}>通知投递（独立记录）</Typography.Title>
                    {deliveries.length ? (
                      <Descriptions
                        bordered
                        size="small"
                        column={1}
                        items={deliveries.map((item) => ({
                          key: item.id,
                          label: item.channel_name || item.channel_type,
                          children: `${item.status} · 尝试 ${item.attempts} 次`,
                        }))}
                      />
                    ) : (
                      <Typography.Text type="secondary">该事件未配置通知或尚未生成投递记录。</Typography.Text>
                    )}
                  </Space>
                ) : (
                  <CatalogState kind="empty" description="所选事件没有可读原始数据" />
                ),
              },
            ]}
          />
        ) : null}
      </Drawer>
    </ApmRouteShell>
  );
}
