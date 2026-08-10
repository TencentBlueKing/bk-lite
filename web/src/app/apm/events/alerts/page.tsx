'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ReloadOutlined } from '@ant-design/icons';
import {
  Badge,
  Button,
  Descriptions,
  Drawer,
  Input,
  message,
  Radio,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
  type TableColumnsType,
} from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import FilterToolbar from '@/components/filter-toolbar';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmEvent, ApmEventQuery, ApmNotificationDelivery, ApmPolicyMetric, ApmPolicySeverity } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';
type AlertTab = 'active' | 'history';
type DrawerTab = 'alert' | 'event';
type TimeRange = '1h' | '24h' | '7d';

const RANGE_MS: Record<TimeRange, number> = {
  '1h': 60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

const SEVERITY = {
  critical: { label: '严重', color: 'red' },
  error: { label: '错误', color: 'orange' },
  warning: { label: '警告', color: 'gold' },
  info: { label: '提醒', color: 'blue' },
} as const;

const SEVERITY_CHART: Record<'critical' | 'error' | 'warning', string> = {
  critical: 'var(--color-fail)',
  error: 'var(--theme-color-status-warning)',
  warning: 'var(--color-warning, var(--theme-color-status-warning))',
};

const ALERT_STATUS = {
  firing: { label: '告警中', color: 'error' },
  recovered: { label: '已恢复', color: 'success' },
} as const;

const METRIC_LABELS: Record<ApmPolicyMetric, string> = {
  error_rate: '错误率',
  p95: 'P95 延迟',
  p99: 'P99 延迟',
  throughput: '吞吐',
  no_traffic: '无流量',
};

const ACTION_LABELS: Record<ApmEvent['action'], string> = {
  created: '触发',
  recovery: '恢复',
};

const DELIVERY_STATUS: Record<ApmNotificationDelivery['status'], { label: string; color: string }> = {
  pending: { label: '待投递', color: 'processing' },
  delivered: { label: '已送达', color: 'success' },
  failed: { label: '终止失败', color: 'error' },
};

export default function ApmEventsPage() {
  const searchParams = useSearchParams();
  const { getEvents, isLoading: authLoading, retryNotificationDelivery } = useApmApi();
  const [events, setEvents] = useState<ApmEvent[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [query, setQuery] = useState<ApmEventQuery>({ limit: 50 });
  const [activeTab, setActiveTab] = useState<AlertTab>('active');
  const [timeRange, setTimeRange] = useState<TimeRange>('24h');
  const [keyword, setKeyword] = useState(
    () => searchParams.get('service') ?? searchParams.get('q') ?? ''
  );
  const [environmentFilter, setEnvironmentFilter] = useState(
    () => searchParams.get('environment') ?? ''
  );
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('alert');
  const [selectedAlert, setSelectedAlert] = useState<ApmEvent | null>(null);

  const load = useCallback(() => {
    if (authLoading) return;
    setState('loading');
    const endedAt = new Date();
    getEvents({
      ...query,
      started_at: new Date(endedAt.getTime() - RANGE_MS[timeRange]).toISOString(),
      ended_at: endedAt.toISOString(),
    })
      .then((items) => {
        setEvents(items);
        setState(items.length ? 'ready' : 'empty');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, getEvents, query, timeRange]);

  useEffect(() => load(), [load]);

  useEffect(() => {
    if (!drawerOpen || !selectedAlert) return;
    const refreshed = events.find((event) => event.id === selectedAlert.id)
      ?? events.find((event) => event.external_id === selectedAlert.external_id);
    if (!refreshed || refreshed === selectedAlert) return;
    setSelectedAlert(refreshed);
  }, [drawerOpen, events]);

  const alerts = useMemo(() => {
    const seen = new Set<string>();
    return events.filter((event) => {
      if (seen.has(event.external_id)) return false;
      seen.add(event.external_id);
      return true;
    });
  }, [events]);

  const activeAlerts = useMemo(
    () => alerts.filter((event) => event.status === 'firing'),
    [alerts],
  );
  const historicalAlerts = useMemo(
    () => alerts.filter((event) => event.status === 'recovered'),
    [alerts],
  );
  const visibleAlerts = useMemo(() => {
    const source = activeTab === 'active' ? activeAlerts : historicalAlerts;
    const normalized = keyword.trim().toLocaleLowerCase();
    const env = environmentFilter.trim().toLocaleLowerCase();
    return source.filter((event) => {
      if (env && (event.environment || '').toLocaleLowerCase() !== env) return false;
      if (!normalized) return true;
      return (
        event.title.toLocaleLowerCase().includes(normalized)
        || event.service.toLocaleLowerCase().includes(normalized)
        || event.resource_name.toLocaleLowerCase().includes(normalized)
        || event.item.toLocaleLowerCase().includes(normalized)
      );
    });
  }, [activeAlerts, activeTab, environmentFilter, historicalAlerts, keyword]);
  const visibleState: PageState = state === 'ready' && !visibleAlerts.length ? 'empty' : state;

  const distribution = useMemo(() => {
    const bucketCount = timeRange === '1h' ? 12 : timeRange === '24h' ? 24 : 28;
    const rangeMs = RANGE_MS[timeRange];
    const bucketMs = rangeMs / bucketCount;
    const rangeStart = Date.now() - rangeMs;
    const buckets = Array.from({ length: bucketCount }, () => ({ critical: 0, error: 0, warning: 0 }));
    events.forEach((event) => {
      if (event.severity === 'info') return;
      const index = Math.min(bucketCount - 1, Math.max(0, Math.floor((new Date(event.start_time).getTime() - rangeStart) / bucketMs)));
      buckets[index][event.severity] += 1;
    });
    return buckets;
  }, [events, timeRange]);
  const maxDistribution = Math.max(1, ...distribution.map((bucket) => bucket.critical + bucket.error + bucket.warning));

  const relatedEvents = useMemo(() => {
    if (!selectedAlert) return [];
    return events
      .filter((event) => event.external_id === selectedAlert.external_id)
      .sort((left, right) => new Date(right.start_time).getTime() - new Date(left.start_time).getTime());
  }, [events, selectedAlert]);

  const openDrawer = useCallback((alert: ApmEvent, tab: DrawerTab = 'alert') => {
    setSelectedAlert(alert);
    setDrawerTab(tab);
    setDrawerOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelectedAlert(null);
    setDrawerTab('alert');
  }, []);

  const handleRetry = useCallback(async (event: ApmEvent, delivery: ApmNotificationDelivery) => {
    setRetryingId(delivery.id);
    try {
      const retried = await retryNotificationDelivery(delivery.id);
      setEvents((items) => items.map((item) => item.id === event.id ? {
        ...item,
        notification_deliveries: item.notification_deliveries.map((current) => (
          current.id === retried.id ? retried : current
        )),
      } : item));
      setSelectedAlert((current) => {
        if (!current || current.id !== event.id) return current;
        return {
          ...current,
          notification_deliveries: current.notification_deliveries.map((item) => (
            item.id === retried.id ? retried : item
          )),
        };
      });
      message.success('通知已进入重投队列');
    } finally {
      setRetryingId(null);
    }
  }, [retryNotificationDelivery]);

  const renderDeliveries = (event: ApmEvent) => {
    const deliveries = event.notification_deliveries ?? [];
    if (!deliveries.length) {
      return <Typography.Text type="secondary">未配置通知渠道</Typography.Text>;
    }
    return (
      <div className="flex flex-col gap-2">
        {deliveries.map((delivery) => (
          <div
            key={delivery.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-3 py-2"
          >
            <Space direction="vertical" size={0}>
              <Space wrap>
                <Typography.Text strong>{delivery.channel_name || `渠道 ${delivery.channel_id ?? '未知'}`}</Typography.Text>
                <Tag bordered={false}>{delivery.channel_type || '未知类型'}</Tag>
                <Tag bordered={false} color={delivery.delivery_mode === 'alert_event_copy' ? 'purple' : 'blue'}>
                  {delivery.delivery_mode === 'alert_event_copy' ? '告警中心事件副本' : '普通通知'}
                </Tag>
                <Tag bordered={false} color={DELIVERY_STATUS[delivery.status].color}>
                  {DELIVERY_STATUS[delivery.status].label}
                </Tag>
              </Space>
              <Typography.Text type="secondary" className="text-xs">
                尝试 {delivery.attempts} 次
                {delivery.recipients.length ? ` · 接收人 ${delivery.recipients.join('、')}` : ''}
                {delivery.last_error_message ? ` · ${delivery.last_error_code || 'delivery_failed'}：${delivery.last_error_message}` : ''}
              </Typography.Text>
            </Space>
            {delivery.status === 'failed' ? (
              <Button
                size="small"
                loading={retryingId === delivery.id}
                onClick={() => handleRetry(event, delivery)}
              >
                人工重投
              </Button>
            ) : null}
          </div>
        ))}
      </div>
    );
  };

  const columns: TableColumnsType<ApmEvent> = [
    {
      title: '告警',
      dataIndex: 'title',
      fixed: 'left',
      render: (title, event) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{title}</Typography.Text>
          <Typography.Text type="secondary">
            {event.resource_name || event.service} · {event.environment || '未设置环境'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 90,
      render: (severity: ApmEvent['severity']) => (
        <Tag bordered={false} color={SEVERITY[severity].color}>{SEVERITY[severity].label}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      responsive: ['sm'],
      render: (status: ApmEvent['status']) => (
        <Tag bordered={false} color={ALERT_STATUS[status].color}>{ALERT_STATUS[status].label}</Tag>
      ),
    },
    {
      title: '指标',
      dataIndex: 'item',
      width: 130,
      responsive: ['lg'],
      render: (item: ApmPolicyMetric) => METRIC_LABELS[item] ?? item,
    },
    {
      title: '值',
      dataIndex: 'value',
      width: 100,
      responsive: ['md'],
      render: (value) => value ?? '—',
      className: 'tabular-nums',
    },
    {
      title: '通知',
      width: 130,
      render: (_, event) => {
        const deliveries = event.notification_deliveries ?? [];
        if (!deliveries.length) return <Typography.Text type="secondary">未配置</Typography.Text>;
        const failed = deliveries.filter((delivery) => delivery.status === 'failed').length;
        const pending = deliveries.filter((delivery) => delivery.status === 'pending').length;
        return failed
          ? <Tag bordered={false} color="error">{failed} 个失败</Tag>
          : pending
            ? <Tag bordered={false} color="processing">{pending} 个处理中</Tag>
            : <Tag bordered={false} color="success">全部送达</Tag>;
      },
    },
    {
      title: '发生时间',
      dataIndex: 'start_time',
      width: 180,
      responsive: ['md'],
      render: (value) => <span className="tabular-nums">{dayjs(value).format('YYYY-MM-DD HH:mm:ss')}</span>,
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, event) => (
        <Button
          type="link"
          className="!px-0"
          onClick={(clickEvent) => {
            clickEvent.stopPropagation();
            openDrawer(event);
          }}
        >
          详情
        </Button>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="告警"
      description="集中查看当前告警与已恢复的历史告警，并追踪每次通知投递结果。"
      dependency="control"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <FilterToolbar align="start" spacing="flush" className="mb-3 w-full" contentClassName="w-full">
            <Input.Search
              allowClear
              aria-label="搜索告警标题、服务或规则"
              className="w-80"
              placeholder="搜索告警标题 / 服务 / 规则"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              allowClear
              aria-label="按环境筛选告警"
              className="w-40"
              placeholder="全部环境"
              value={environmentFilter || undefined}
              options={Array.from(new Set(events.map((event) => event.environment).filter(Boolean)))
                .sort()
                .map((value) => ({ value, label: value }))}
              onChange={(value) => setEnvironmentFilter(value ?? '')}
            />
            <div className="flex-1" />
            <Typography.Text type="secondary" className="text-xs">时间范围</Typography.Text>
            <Radio.Group
              aria-label="告警时间范围"
              buttonStyle="solid"
              size="small"
              value={timeRange}
              onChange={(event) => setTimeRange(event.target.value)}
            >
              {(Object.keys(RANGE_MS) as TimeRange[]).map((value) => (
                <Radio.Button key={value} value={value}>{value}</Radio.Button>
              ))}
            </Radio.Group>
            <Button icon={<ReloadOutlined aria-hidden="true" />} onClick={load}>刷新</Button>
          </FilterToolbar>
          <div className="mb-3 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <Typography.Text strong>告警分布（近 {timeRange}）</Typography.Text>
              <Space size="middle">
                <Typography.Text type="secondary" className="text-xs">严重 {events.filter((event) => event.severity === 'critical').length}</Typography.Text>
                <Typography.Text type="secondary" className="text-xs">错误 {events.filter((event) => event.severity === 'error').length}</Typography.Text>
                <Typography.Text type="secondary" className="text-xs">警告 {events.filter((event) => event.severity === 'warning').length}</Typography.Text>
              </Space>
            </div>
            <div className="flex h-16 items-end gap-1" role="img" aria-label={`近 ${timeRange} 告警分布`}>
              {distribution.map((bucket, index) => (
                <div key={index} className="flex h-full min-w-1 flex-1 flex-col justify-end overflow-hidden rounded-t-sm" title={`第 ${index + 1} 时间段：${bucket.critical + bucket.error + bucket.warning} 条`}>
                  <span className="block" style={{ height: `${(bucket.critical / maxDistribution) * 100}%`, background: SEVERITY_CHART.critical }} />
                  <span className="block" style={{ height: `${(bucket.error / maxDistribution) * 100}%`, background: SEVERITY_CHART.error }} />
                  <span className="block" style={{ height: `${(bucket.warning / maxDistribution) * 100}%`, background: SEVERITY_CHART.warning }} />
                </div>
              ))}
            </div>
          </div>
          <Tabs
            activeKey={activeTab}
            className="mb-3"
            items={[
              {
                key: 'active',
                label: <Space size={6}>活跃告警<Badge count={activeAlerts.length} showZero color="var(--color-fail)" /></Space>,
              },
              {
                key: 'history',
                label: <Space size={6}>历史告警<Badge count={historicalAlerts.length} showZero /></Space>,
              },
            ]}
            onChange={(key) => setActiveTab(key as AlertTab)}
          />
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border-2)] pt-3">
            <Space wrap size="middle">
              <Select
                allowClear
                aria-label="按告警级别筛选"
                className="w-36"
                placeholder="全部级别"
                value={query.severity}
                options={(Object.entries(SEVERITY) as [ApmEvent['severity'], typeof SEVERITY[keyof typeof SEVERITY]][])
                  .filter(([value]) => value !== 'info')
                  .map(([value, config]) => ({ value: value as ApmPolicySeverity, label: config.label }))}
                onChange={(severity) => setQuery((current) => ({ ...current, severity }))}
              />
              <Badge
                count={visibleAlerts.length}
                showZero
                color="var(--color-primary)"
                className="text-xs text-[var(--color-text-3)]"
              />
              <Typography.Text type="secondary" className="text-xs">
                {activeTab === 'active' ? '当前未恢复' : '最近 7 天已恢复'}
              </Typography.Text>
            </Space>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {visibleState === 'ready' ? (
            <Table
              rowKey="event_id"
              columns={columns}
              dataSource={visibleAlerts}
              pagination={false}
              onRow={(event) => ({
                onClick: () => openDrawer(event),
                className: 'cursor-pointer',
              })}
            />
          ) : (
            <CatalogState
              kind={visibleState}
              description={visibleState === 'empty'
                ? activeTab === 'active'
                  ? '当前组织没有活跃 APM 告警。'
                  : '最近 7 天当前组织没有历史 APM 告警。'
                : undefined}
            />
          )}
        </ApmSurface>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={closeDrawer}
        width={880}
        title={selectedAlert ? (
          <Space size={8} wrap align="center">
            <Tag bordered={false} color={ALERT_STATUS[selectedAlert.status].color}>
              {ALERT_STATUS[selectedAlert.status].label}
            </Tag>
            <Tag bordered={false} color={SEVERITY[selectedAlert.severity].color}>
              {SEVERITY[selectedAlert.severity].label}
            </Tag>
            <Tag bordered={false}>{METRIC_LABELS[selectedAlert.item] ?? selectedAlert.item}</Tag>
            <span className="text-base font-semibold">{selectedAlert.title}</span>
          </Space>
        ) : '告警详情'}
        footer={(
          <div className="flex justify-end">
            <Button onClick={closeDrawer}>关闭</Button>
          </div>
        )}
        styles={{
          body: { paddingTop: 0 },
        }}
      >
        {selectedAlert ? (
          <div className="flex h-full flex-col">
            <div className="flex flex-wrap gap-x-4 gap-y-2 border-b border-[var(--color-border)] py-3 text-xs text-[var(--color-text-3)]">
              <span>
                所属服务{' '}
                <Typography.Text className="!text-xs !text-[var(--color-primary)]">{selectedAlert.service}</Typography.Text>
              </span>
              {selectedAlert.resource_name ? (
                <span>
                  资源{' '}
                  <Typography.Text className="!text-xs">{selectedAlert.resource_name}</Typography.Text>
                </span>
              ) : null}
              <span>
                环境{' '}
                <Typography.Text className="!text-xs">{selectedAlert.environment || '未设置环境'}</Typography.Text>
              </span>
              <span>
                触发时间{' '}
                <Typography.Text className="!text-xs tabular-nums">
                  {dayjs(selectedAlert.start_time).format('YYYY-MM-DD HH:mm:ss')}
                </Typography.Text>
              </span>
            </div>

            <Tabs
              activeKey={drawerTab}
              className="mt-2"
              onChange={(key) => setDrawerTab(key as DrawerTab)}
              items={[
                { key: 'alert', label: '告警' },
                { key: 'event', label: `事件 (${relatedEvents.length})` },
              ]}
            />

            <div className="min-h-0 flex-1 overflow-y-auto pb-2">
              {drawerTab === 'alert' ? (
                <div className="flex flex-col gap-4">
                  <Descriptions
                    title="告警信息"
                    bordered
                    size="small"
                    column={2}
                    labelStyle={{ width: 110, color: 'var(--color-text-3)' }}
                  >
                    <Descriptions.Item label="时间">
                      {dayjs(selectedAlert.start_time).format('YYYY-MM-DD HH:mm:ss')}
                    </Descriptions.Item>
                    <Descriptions.Item label="级别">
                      <span
                        className="border-l-4 pl-2 font-semibold"
                        style={{
                          borderColor: selectedAlert.severity === 'critical'
                            ? SEVERITY_CHART.critical
                            : selectedAlert.severity === 'error'
                              ? SEVERITY_CHART.error
                              : SEVERITY_CHART.warning,
                          color: selectedAlert.severity === 'critical'
                            ? SEVERITY_CHART.critical
                            : selectedAlert.severity === 'error'
                              ? SEVERITY_CHART.error
                              : SEVERITY_CHART.warning,
                        }}
                      >
                        {SEVERITY[selectedAlert.severity].label}
                      </span>
                    </Descriptions.Item>
                    <Descriptions.Item label="状态">
                      <Tag bordered={false} color={ALERT_STATUS[selectedAlert.status].color}>
                        {ALERT_STATUS[selectedAlert.status].label}
                      </Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="度量">
                      {METRIC_LABELS[selectedAlert.item] ?? selectedAlert.item}
                    </Descriptions.Item>
                    <Descriptions.Item label="所属对象" span={2}>
                      <Space direction="vertical" size={0}>
                        <Typography.Text>{selectedAlert.service}</Typography.Text>
                        {selectedAlert.resource_name ? (
                          <Typography.Text type="secondary" className="text-xs">
                            {selectedAlert.resource_name}
                          </Typography.Text>
                        ) : null}
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="环境">
                      {selectedAlert.environment || '未设置环境'}
                    </Descriptions.Item>
                    <Descriptions.Item label="当前值">
                      <span className="tabular-nums">{selectedAlert.value ?? '—'}</span>
                    </Descriptions.Item>
                    <Descriptions.Item label="描述" span={2}>
                      {selectedAlert.description || '—'}
                    </Descriptions.Item>
                    {selectedAlert.end_time ? (
                      <Descriptions.Item label="结束时间" span={2}>
                        {dayjs(selectedAlert.end_time).format('YYYY-MM-DD HH:mm:ss')}
                      </Descriptions.Item>
                    ) : null}
                    <Descriptions.Item label="策略 ID" span={2}>
                      {selectedAlert.policy_id || '—'}
                    </Descriptions.Item>
                  </Descriptions>

                  <div>
                    <Typography.Text strong className="mb-2 block">通知投递</Typography.Text>
                    {renderDeliveries(selectedAlert)}
                  </div>
                </div>
              ) : (
                <div>
                  <Typography.Text type="secondary" className="mb-3 block text-xs">
                    同一 external_id 关联的事件时间线
                  </Typography.Text>
                  {relatedEvents.length ? (
                    <Timeline
                      items={relatedEvents.map((event) => ({
                        color: event.action === 'recovery'
                          ? 'green'
                          : event.severity === 'critical'
                            ? 'red'
                            : 'blue',
                        children: (
                          <div className="flex flex-wrap items-start justify-between gap-3 pb-1">
                            <Space direction="vertical" size={2}>
                              <Space wrap size={6}>
                                <Typography.Text strong className="tabular-nums">
                                  {dayjs(event.start_time).format('YYYY-MM-DD HH:mm:ss')}
                                </Typography.Text>
                                <Tag bordered={false}>{ACTION_LABELS[event.action]}</Tag>
                                <Tag bordered={false} color={SEVERITY[event.severity].color}>
                                  {SEVERITY[event.severity].label}
                                </Tag>
                                <Tag bordered={false} color={ALERT_STATUS[event.status].color}>
                                  {ALERT_STATUS[event.status].label}
                                </Tag>
                              </Space>
                              <Typography.Text>{event.title}</Typography.Text>
                              <Typography.Text type="secondary" className="text-xs">
                                {METRIC_LABELS[event.item] ?? event.item}
                                {event.value !== null ? ` · ${event.value}` : ''}
                                {event.description ? ` · ${event.description}` : ''}
                              </Typography.Text>
                            </Space>
                          </div>
                        ),
                      }))}
                    />
                  ) : (
                    <Typography.Text type="secondary">暂无关联事件</Typography.Text>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : null}
      </Drawer>
    </ApmRouteShell>
  );
}
