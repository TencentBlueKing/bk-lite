'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  Alert as AntAlert,
  Button,
  Descriptions,
  Drawer,
  Input,
  message,
  Popconfirm,
  Radio,
  Select,
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
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import type {
  ApmAlert,
  ApmAlertEvent,
  ApmAlertQuery,
  ApmEventSnapshot,
  ApmNotificationDelivery,
  ApmPolicySeverity,
} from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';
type Range = '1h' | '24h' | '7d';
const RANGE_MS: Record<Range, number> = { '1h': 3_600_000, '24h': 86_400_000, '7d': 604_800_000 };
const ACTION_LABEL = { triggered: '触发', escalated: '级别升级', recovered: '恢复', closed: '人工关闭' } as const;
const STATUS_LABEL = { active: '告警中', recovered: '已恢复', closed: '已关闭' } as const;
const STATUS_COLOR = { active: 'error', recovered: 'success', closed: 'default' } as const;
const SEVERITY_COLOR: Record<ApmPolicySeverity, string> = { critical: 'red', error: 'orange', warning: 'gold' };

export default function ApmAlertsPage() {
  const { token } = theme.useToken();
  const {
    closeAlert,
    getAlertDistribution,
    getAlerts,
    getAlertSnapshots,
    getNotificationDeliveries,
    isLoading: authLoading,
  } = useApmApi();
  const [alerts, setAlerts] = useState<ApmAlert[]>([]);
  const [distribution, setDistribution] = useState<
    Array<{ time: string; critical: number; error: number; warning: number }>
  >([]);
  const [state, setState] = useState<PageState>('loading');
  const [activeTab, setActiveTab] = useState<'active' | 'history'>('active');
  const [range, setRange] = useState<Range>('24h');
  const [severity, setSeverity] = useState<ApmPolicySeverity | undefined>();
  const [metric, setMetric] = useState<ApmAlertQuery['metric_type']>();
  const [keyword, setKeyword] = useState('');
  const [submittedKeyword, setSubmittedKeyword] = useState('');
  const [selected, setSelected] = useState<ApmAlert | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<ApmAlertEvent | null>(null);
  const [snapshot, setSnapshot] = useState<ApmEventSnapshot | null>(null);
  const [deliveries, setDeliveries] = useState<ApmNotificationDelivery[]>([]);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

  const timeParams = useMemo(() => {
    const endedAt = new Date();
    return { started_at: new Date(endedAt.getTime() - RANGE_MS[range]).toISOString(), ended_at: endedAt.toISOString() };
  }, [range]);

  const load = useCallback(() => {
    if (authLoading) return;
    setState('loading');
    const query: ApmAlertQuery = {
      ...timeParams,
      limit: 100,
      severity,
      metric_type: metric,
      keyword: submittedKeyword,
      status: activeTab === 'active' ? 'active' : undefined,
    };
    Promise.all([getAlerts(query), getAlertDistribution(timeParams)])
      .then(([items, buckets]) => {
        const visible = activeTab === 'history' ? items.filter((item) => item.status !== 'active') : items;
        setAlerts(visible);
        setDistribution(buckets);
        setState(visible.length ? 'ready' : 'empty');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [activeTab, authLoading, getAlertDistribution, getAlerts, metric, severity, submittedKeyword, timeParams]);

  useEffect(() => load(), [load]);

  const chooseEvent = useCallback(
    (alert: ApmAlert, event: ApmAlertEvent) => {
      setSelectedEvent(event);
      setSnapshot(null);
      setDeliveries([]);
      setSnapshotLoading(true);
      Promise.all([
        getAlertSnapshots(alert.id, event.event_id),
        getNotificationDeliveries({ event_id: event.event_id }),
      ])
        .then(([snapshots, deliveryItems]) => {
          setSnapshot(snapshots[0] ?? null);
          setDeliveries(deliveryItems);
        })
        .finally(() => setSnapshotLoading(false));
    },
    [getAlertSnapshots, getNotificationDeliveries],
  );

  const openDrawer = (alert: ApmAlert) => {
    setSelected(alert);
    const event = alert.events.at(-1) ?? null;
    if (event) chooseEvent(alert, event);
  };

  const chartRows = useMemo(() => {
    const series = snapshot?.payload?.series ?? [];
    const threshold = snapshot?.evaluation_snapshot.threshold;
    const eventAt = new Date(snapshot?.occurred_at ?? 0).getTime();
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
      event: index === closest ? point.value : null,
    }));
  }, [snapshot]);

  const columns: TableColumnsType<ApmAlert> = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: 90,
      render: (value) => <Tag color={SEVERITY_COLOR[value as ApmPolicySeverity]}>{value}</Tag>,
    },
    {
      title: '告警',
      dataIndex: 'title',
      render: (_, item) => (
        <Button type="link" className="!px-0" onClick={() => openDrawer(item)}>
          {item.title}
        </Button>
      ),
    },
    {
      title: 'Service / Endpoint',
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <span>
            {item.service_namespace ? `${item.service_namespace} / ` : ''}
            {item.service_name}
          </span>
          <Typography.Text type="secondary" className="!text-xs">
            {item.endpoint || '全部端点'} · {item.environment}
            {item.version ? ` · ${item.version}` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    { title: '指标', dataIndex: 'metric_type', width: 130 },
    { title: '当前值', dataIndex: 'current_value', width: 110, render: (value) => value ?? '无数据' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value) => (
        <Tag color={STATUS_COLOR[value as ApmAlert['status']]}>{STATUS_LABEL[value as ApmAlert['status']]}</Tag>
      ),
    },
    { title: '事件', dataIndex: 'event_count', width: 80 },
    {
      title: '最近变化',
      dataIndex: 'last_event_at',
      width: 180,
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
  ];

  return (
    <ApmRouteShell
      title="告警"
      description="Alert 聚合完整生命周期；Event 记录触发、升级、恢复与人工关闭。"
      dependency="control"
    >
      <Space direction="vertical" size="middle" className="w-full">
        <ApmSurface>
          <div className="h-40" role="img" aria-label={`最近 ${range} 告警事件分布，按严重、错误、警告分组`}>
            <TimeSeriesComposedChart
              data={distribution}
              xDataKey="time"
              getXLabel={(item) => dayjs(String(item.time)).format(range === '7d' ? 'MM-DD' : 'HH:mm')}
              series={[
                { name: '严重', type: 'bar', dataKey: 'critical', color: token.colorError },
                { name: '错误', type: 'bar', dataKey: 'error', color: token.colorWarning },
                { name: '警告', type: 'bar', dataKey: 'warning', color: token.colorPrimary },
              ]}
            />
          </div>
        </ApmSurface>
        <ApmSurface padding="none">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] p-3">
            <Tabs
              className="mr-2"
              activeKey={activeTab}
              onChange={(key) => setActiveTab(key as 'active' | 'history')}
              items={[
                { key: 'active', label: '活跃告警' },
                { key: 'history', label: '历史告警' },
              ]}
            />
            <Input.Search
              className="w-72"
              allowClear
              placeholder="搜索标题、策略、服务或端点"
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value);
                if (!event.target.value) setSubmittedKeyword('');
              }}
              onSearch={(value) => setSubmittedKeyword(value.trim())}
            />
            <Select
              className="w-32"
              allowClear
              placeholder="全部级别"
              value={severity}
              onChange={setSeverity}
              options={Object.keys(SEVERITY_COLOR).map((value) => ({ value, label: value }))}
            />
            <Select
              className="w-36"
              allowClear
              placeholder="全部指标"
              value={metric}
              onChange={setMetric}
              options={['error_rate', 'p95', 'p99', 'throughput', 'no_traffic'].map((value) => ({
                value,
                label: value,
              }))}
            />
            <div className="flex-1" />
            <Radio.Group value={range} onChange={(event) => setRange(event.target.value)}>
              {Object.keys(RANGE_MS).map((value) => (
                <Radio.Button key={value} value={value}>
                  {value}
                </Radio.Button>
              ))}
            </Radio.Group>
            <Button icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
          </div>
          <div className="p-3">
            {state === 'ready' ? (
              <ApmDataTable
                rowKey="id"
                columns={columns}
                dataSource={alerts}
                pagination={{ pageSize: 20 }}
                onRow={(item) => ({
                  className: 'cursor-pointer',
                  tabIndex: 0,
                  onClick: () => openDrawer(item),
                  onKeyDown: (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      openDrawer(item);
                    }
                  },
                })}
                scroll={{ x: 1080 }}
              />
            ) : (
              <CatalogState kind={state} onRetry={load} />
            )}
          </div>
        </ApmSurface>
      </Space>
      <Drawer
        width={880}
        open={Boolean(selected)}
        onClose={() => {
          setSelected(null);
          setSelectedEvent(null);
          setSnapshot(null);
        }}
        title={selected?.title}
        extra={
          selected?.status === 'active' ? (
            <Popconfirm
              title="人工关闭会追加 closed 事件和不可变快照，确认继续？"
              onConfirm={async () => {
                if (!selected) return;
                await closeAlert(selected.id);
                message.success('告警已关闭');
                setSelected(null);
                load();
              }}
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
                label: '事件快照',
                children: snapshotLoading ? (
                  <CatalogState kind="loading" />
                ) : snapshot ? (
                  <Space direction="vertical" size="middle" className="w-full">
                    <AntAlert
                      showIcon
                      type={
                        snapshot.payload_status === 'available'
                          ? 'success'
                          : snapshot.payload_status === 'expired'
                            ? 'warning'
                            : 'info'
                      }
                      message={
                        snapshot.payload_status === 'expired'
                          ? '遥测保留期已过；以下语义快照仍永久可读，指标序列已按保留策略清理。'
                          : snapshot.payload_status === 'unavailable'
                            ? '指标序列对象暂不可用；APM Event 与语义证据已持久化，后台将有界重试。'
                            : snapshot.payload_status === 'pending'
                              ? '语义快照已持久化，指标序列正在异步写入对象存储。'
                              : '正在展示所选事件发生时的持久化快照，不会重新查询当前策略。'
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
                      aria-label={`事件 ${snapshot.event_id} 趋势，评估值 ${snapshot.evaluation_snapshot.value ?? '无数据'}，当时阈值 ${snapshot.evaluation_snapshot.threshold ?? '无'}`}
                    >
                      <TimeSeriesComposedChart
                        data={chartRows}
                        xDataKey="timestamp"
                        getXLabel={(item) => dayjs(String(item.timestamp)).format('HH:mm')}
                        xAxisBoundaryGap={false}
                        series={[
                          { name: '评估值', type: 'line', dataKey: 'value', color: token.colorPrimary, showArea: true },
                          {
                            name: '当时阈值',
                            type: 'line',
                            dataKey: 'threshold',
                            color: token.colorError,
                            lineType: 'dashed',
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
                        { key: 'schema', label: 'Schema', children: `v${snapshot.schema_version}` },
                        { key: 'event', label: 'event_id', children: snapshot.event_id },
                        { key: 'value', label: '评估值', children: snapshot.evaluation_snapshot.value ?? '无数据' },
                        {
                          key: 'condition',
                          label: '当时条件',
                          children: `${snapshot.evaluation_snapshot.comparator ?? '—'} ${snapshot.evaluation_snapshot.threshold ?? '—'} ${snapshot.evaluation_snapshot.unit ?? ''}`,
                        },
                        {
                          key: 'policy',
                          label: '策略快照',
                          span: 2,
                          children: (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(snapshot.policy_snapshot, null, 2)}
                            </pre>
                          ),
                        },
                        {
                          key: 'object',
                          label: '对象快照',
                          span: 2,
                          children: (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(snapshot.object_snapshot, null, 2)}
                            </pre>
                          ),
                        },
                        {
                          key: 'trace',
                          label: 'Trace 检索上下文',
                          span: 2,
                          children: (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(snapshot.trace_context, null, 2)}
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
                  <CatalogState kind="empty" description="所选事件没有可读快照" />
                ),
              },
            ]}
          />
        ) : null}
      </Drawer>
    </ApmRouteShell>
  );
}
