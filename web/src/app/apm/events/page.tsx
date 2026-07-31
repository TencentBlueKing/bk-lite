'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button, Select, Space, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmEvent, ApmEventQuery, ApmPolicySeverity } from '@/app/apm/types';

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
  closed: { label: '关闭', color: 'default' },
} as const;

export default function ApmEventsPage() {
  const { getEvents, isLoading: authLoading } = useApmApi();
  const [events, setEvents] = useState<ApmEvent[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [query, setQuery] = useState<ApmEventQuery>({ limit: 50 });

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
        <Tag color={SEVERITY[severity].color}>{SEVERITY[severity].label}</Tag>
      ),
    },
    {
      title: '生命周期',
      dataIndex: 'action',
      width: 100,
      render: (action: ApmEvent['action']) => <Tag color={ACTION[action].color}>{ACTION[action].label}</Tag>,
    },
    { title: '指标', dataIndex: 'item', width: 130 },
    {
      title: '值',
      dataIndex: 'value',
      width: 100,
      render: (value) => value ?? '—',
    },
    {
      title: '发生时间',
      dataIndex: 'start_time',
      width: 180,
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 120,
      render: (_, event) => (
        <Link href={`/alarm/alarms?resource_type=apm_service&resource_id=${encodeURIComponent(event.resource_id)}`}>
          <Button type="link">告警中心</Button>
        </Link>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="APM 事件"
      description="查看统一告警中心中来源为 APM 的事件，不复制告警生命周期数据。"
      dependency="alerts"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Space wrap>
          <Select
            allowClear
            aria-label="按生命周期筛选"
            className="w-32"
            placeholder="全部生命周期"
            value={query.action}
            options={Object.entries(ACTION).map(([value, config]) => ({ value, label: config.label }))}
            onChange={(action) => setQuery((current) => ({ ...current, action }))}
          />
          <Select
            allowClear
            aria-label="按告警级别筛选"
            className="w-32"
            placeholder="全部级别"
            value={query.severity}
            options={(Object.entries(SEVERITY) as [ApmEvent['severity'], typeof SEVERITY[keyof typeof SEVERITY]][])
              .filter(([value]) => value !== 'info')
              .map(([value, config]) => ({ value: value as ApmPolicySeverity, label: config.label }))}
            onChange={(severity) => setQuery((current) => ({ ...current, severity }))}
          />
        </Space>
        <Button onClick={load}>刷新</Button>
      </div>
      {state === 'ready' ? (
        <Table rowKey="event_id" columns={columns} dataSource={events} scroll={{ x: 980 }} pagination={false} />
      ) : (
        <CatalogState
          kind={state}
          description={state === 'empty' ? '最近 7 天当前组织没有 APM 告警事件。' : undefined}
        />
      )}
    </ApmRouteShell>
  );
}
