'use client';

import { useCallback, useEffect, useState } from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Badge, Button, message, Select, Space, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmEvent, ApmEventQuery, ApmNotificationDelivery, ApmPolicySeverity } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';

const SEVERITY = {
  critical: { label: '严重', color: 'red' },
  error: { label: '错误', color: 'orange' },
  warning: { label: '警告', color: 'gold' },
  info: { label: '提醒', color: 'blue' },
} as const;

const ACTION = {
  created: { label: '触发', color: 'error' },
  recovery: { label: '恢复', color: 'success' },
} as const;

const DELIVERY_STATUS: Record<ApmNotificationDelivery['status'], { label: string; color: string }> = {
  pending: { label: '待投递', color: 'processing' },
  delivered: { label: '已送达', color: 'success' },
  failed: { label: '终止失败', color: 'error' },
};

export default function ApmEventsPage() {
  const { getEvents, isLoading: authLoading, retryNotificationDelivery } = useApmApi();
  const [events, setEvents] = useState<ApmEvent[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [query, setQuery] = useState<ApmEventQuery>({ limit: 50 });
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (authLoading) return;
    setState('loading');
    getEvents(query)
      .then((items) => {
        setEvents(items);
        setState(items.length ? 'ready' : 'empty');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, getEvents, query]);

  useEffect(() => load(), [load]);

  const columns: TableColumnsType<ApmEvent> = [
    {
      title: '事件',
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
      title: '生命周期',
      dataIndex: 'action',
      width: 100,
      responsive: ['sm'],
      render: (action: ApmEvent['action']) => <Tag bordered={false} color={ACTION[action].color}>{ACTION[action].label}</Tag>,
    },
    { title: '指标', dataIndex: 'item', width: 130, responsive: ['lg'] },
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
  ];

  return (
    <ApmRouteShell
      title="APM 事件"
      description="查看由 APM 自己持久化和管理的告警生命周期事件。"
      dependency="control"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Space wrap>
              <Select
                allowClear
                aria-label="按生命周期筛选"
                className="w-36"
                placeholder="全部生命周期"
                value={query.action}
                options={Object.entries(ACTION).map(([value, config]) => ({ value, label: config.label }))}
                onChange={(action) => setQuery((current) => ({ ...current, action }))}
              />
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
                count={events.length}
                showZero
                color="var(--color-primary)"
                className="text-xs text-[var(--color-text-3)]"
              />
              <Typography.Text type="secondary" className="text-xs">最近 7 天事件</Typography.Text>
            </Space>
            <Button icon={<ReloadOutlined aria-hidden="true" />} onClick={load}>刷新</Button>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <Table
              rowKey="event_id"
              columns={columns}
              dataSource={events}
              pagination={false}
              expandable={{
                rowExpandable: (event) => Boolean(event.notification_deliveries?.length),
                expandedRowRender: (event) => (
                  <div className="flex flex-col gap-2 py-1">
                    {event.notification_deliveries.map((delivery) => (
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
                            onClick={async () => {
                              setRetryingId(delivery.id);
                              try {
                                const retried = await retryNotificationDelivery(delivery.id);
                                setEvents((items) => items.map((item) => item.id === event.id ? {
                                  ...item,
                                  notification_deliveries: item.notification_deliveries.map((current) => (
                                    current.id === retried.id ? retried : current
                                  )),
                                } : item));
                                message.success('通知已进入重投队列');
                              } finally {
                                setRetryingId(null);
                              }
                            }}
                          >
                            人工重投
                          </Button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ),
              }}
            />
          ) : (
            <CatalogState
              kind={state}
              description={state === 'empty' ? '最近 7 天当前组织没有 APM 告警事件。' : undefined}
            />
          )}
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
