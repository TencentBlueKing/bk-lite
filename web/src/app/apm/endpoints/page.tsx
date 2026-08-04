'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Input, Radio, Select, Space, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmService } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';
type MetricRange = '15m' | '1h' | '4h' | '1d' | '7d';
type SortKey = 'request_rate' | 'error_rate' | 'p95_ms';

interface EndpointRow {
  key: string;
  method: string;
  route: string;
  serviceId: string;
  serviceName: string;
  namespace: string;
  environment: string;
  requestRate: number;
  errorRate: number | null;
  p95Ms: number | null;
  lastSeenAt: string;
}

const RANGE_MS: Record<MetricRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

const splitEndpoint = (value: string) => {
  const match = value.trim().match(/^([^\s]+)\s+(.+)$/);
  return match ? { method: match[1], route: match[2] } : { method: 'SPAN', route: value };
};

const recentLabel = (value: string) => {
  const minutes = Math.max(0, dayjs().diff(dayjs(value), 'minute'));
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
};

const errorRateColor = (value: number | null) => {
  if (value === null) return undefined;
  if (value >= 0.05) return 'error';
  if (value >= 0.01) return 'warning';
  return 'success';
};

export default function ApmEndpointsPage() {
  const { getServiceRed, getServices, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [rows, setRows] = useState<EndpointRow[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [environment, setEnvironment] = useState('');
  const [timeRange, setTimeRange] = useState<MetricRange>('1h');
  const [serviceId, setServiceId] = useState('all');
  const [sortKey, setSortKey] = useState<SortKey>('request_rate');
  const [keyword, setKeyword] = useState('');

  const load = useCallback(async () => {
    if (authLoading) return;
    setState('loading');
    try {
      const serviceItems = await getServices();
      setServices(serviceItems);
      const availableEnvironments = Array.from(new Set(
        serviceItems.flatMap((service) => service.environment_views.map((view) => view.environment)),
      )).filter(Boolean);
      const selectedEnvironment = environment || availableEnvironments[0] || 'production';
      if (!environment) setEnvironment(selectedEnvironment);

      const visibleServices = serviceItems.filter((service) => (
        service.environment_views.some((view) => view.environment === selectedEnvironment)
      ));
      const endedAt = new Date();
      const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
      const results = await Promise.allSettled(visibleServices.map(async (service) => ({
        service,
        red: await getServiceRed(service.id, selectedEnvironment, startedAt.toISOString(), endedAt.toISOString()),
      })));
      const successfulResults = results.filter((result) => result.status === 'fulfilled');
      if (results.length && !successfulResults.length) {
        const firstFailure = results.find((result) => result.status === 'rejected');
        throw firstFailure?.reason;
      }
      const endpointRows = results.flatMap((result) => {
        if (result.status !== 'fulfilled') return [];
        const { service, red } = result.value;
        return red.top_endpoints.map((endpoint) => {
          const identity = splitEndpoint(endpoint.endpoint);
          return {
            key: `${service.id}:${selectedEnvironment}:${endpoint.endpoint}`,
            method: identity.method,
            route: identity.route,
            serviceId: service.id,
            serviceName: service.name,
            namespace: service.namespace,
            environment: selectedEnvironment,
            requestRate: endpoint.request_rate,
            errorRate: endpoint.error_rate,
            p95Ms: endpoint.p95_ms,
            lastSeenAt: service.last_seen_at,
          };
        });
      });
      setRows(endpointRows);
      setState(endpointRows.length ? 'ready' : 'empty');
    } catch (error) {
      setRows([]);
      setState(catalogErrorKind(error));
    }
  }, [authLoading, environment, getServiceRed, getServices, timeRange]);

  useEffect(() => {
    load();
  }, [load]);

  const environmentOptions = useMemo(() => Array.from(new Set(
    services.flatMap((service) => service.environment_views.map((view) => view.environment)),
  )).filter(Boolean).map((value) => ({ value, label: value })), [services]);

  const serviceOptions = useMemo(() => services
    .filter((service) => service.environment_views.some((view) => view.environment === environment))
    .map((service) => ({ value: service.id, label: service.name })), [environment, services]);

  const visibleRows = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase();
    return rows
      .filter((row) => serviceId === 'all' || row.serviceId === serviceId)
      .filter((row) => !normalized
        || row.route.toLocaleLowerCase().includes(normalized)
        || row.serviceName.toLocaleLowerCase().includes(normalized))
      .sort((left, right) => {
        if (sortKey === 'request_rate') return right.requestRate - left.requestRate;
        if (sortKey === 'error_rate') return (right.errorRate ?? -1) - (left.errorRate ?? -1);
        return (right.p95Ms ?? -1) - (left.p95Ms ?? -1);
      });
  }, [keyword, rows, serviceId, sortKey]);

  const columns: TableColumnsType<EndpointRow> = [
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (value) => <Tag bordered={false} color={value === 'POST' ? 'blue' : undefined}>{value}</Tag>,
    },
    {
      title: '端点',
      render: (_, row) => (
        <Space size={7}>
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" aria-hidden="true" />
          <Typography.Text className="font-mono text-xs">{row.method} {row.route}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '所属服务',
      width: 180,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{row.serviceName}</Typography.Text>
          <Typography.Text type="secondary" className="text-xs">{row.namespace || '未归类应用'} · {row.environment}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '吞吐量',
      dataIndex: 'requestRate',
      align: 'right',
      width: 130,
      render: (value) => <span className="tabular-nums"><strong>{value.toFixed(2)}</strong> <Typography.Text type="secondary" className="text-xs">次/秒</Typography.Text></span>,
    },
    {
      title: '错误率',
      dataIndex: 'errorRate',
      align: 'right',
      width: 100,
      render: (value: number | null) => value === null
        ? '—'
        : <Tag bordered={false} color={errorRateColor(value)}>{(value * 100).toFixed(2)}%</Tag>,
    },
    {
      title: 'P95',
      dataIndex: 'p95Ms',
      align: 'right',
      width: 100,
      render: (value: number | null) => <span className="tabular-nums">{value === null ? '—' : `${value.toFixed(2)} ms`}</span>,
    },
    {
      title: '最近活跃',
      dataIndex: 'lastSeenAt',
      align: 'right',
      width: 110,
      render: (value) => <Typography.Text type="secondary" className="text-xs">{recentLabel(value)}</Typography.Text>,
    },
  ];

  return (
    <ApmRouteShell
      title="端点"
      description="按服务端点查看真实吞吐量、错误率与 P95 时延，定位高影响接口。"
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-3">
            <Input
              allowClear
              aria-label="搜索路径模板或服务"
              className="w-72"
              placeholder="搜索路径模板 / 服务"
              prefix={<SearchOutlined aria-hidden="true" />}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              aria-label="环境"
              className="w-36"
              value={environment || undefined}
              placeholder="选择环境"
              options={environmentOptions}
              onChange={(value) => {
                setEnvironment(value);
                setServiceId('all');
              }}
            />
            <div className="flex-1" />
            <Select
              aria-label="服务"
              className="w-40"
              value={serviceId}
              options={[{ value: 'all', label: '全部服务' }, ...serviceOptions]}
              onChange={setServiceId}
            />
            <Select<SortKey>
              aria-label="排序"
              className="w-32"
              value={sortKey}
              options={[
                { value: 'request_rate', label: '吞吐量' },
                { value: 'error_rate', label: '错误率' },
                { value: 'p95_ms', label: 'P95 耗时' },
              ]}
              onChange={setSortKey}
            />
            <Radio.Group
              aria-label="时间范围"
              buttonStyle="solid"
              size="small"
              value={timeRange}
              onChange={(event) => setTimeRange(event.target.value)}
            >
              {(Object.keys(RANGE_MS) as MetricRange[]).map((value) => (
                <Radio.Button key={value} value={value}>{value}</Radio.Button>
              ))}
            </Radio.Group>
            <Button aria-label="刷新端点" icon={<ReloadOutlined aria-hidden="true" />} onClick={load} />
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <Table rowKey="key" columns={columns} dataSource={visibleRows} pagination={false} />
          ) : (
            <CatalogState kind={state} description={state === 'empty' ? '当前环境和时间范围内没有端点指标。' : undefined} />
          )}
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
