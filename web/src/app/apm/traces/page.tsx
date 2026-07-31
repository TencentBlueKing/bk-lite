'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button, Input, Select, Space, Table, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmTraceSearchParams, ApmTraceSummary } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready' | 'idle';
type TimeRange = '15m' | '1h' | '4h' | '24h' | '7d';

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

export default function ApmTracesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getTraces, isLoading: authLoading } = useApmApi();
  const [namespace, setNamespace] = useState(searchParams.get('service_namespace') ?? '');
  const [serviceName, setServiceName] = useState(searchParams.get('service_name') ?? '');
  const [environment, setEnvironment] = useState(searchParams.get('environment') ?? 'production');
  const [instanceId, setInstanceId] = useState(searchParams.get('instance_id') ?? '');
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [items, setItems] = useState<ApmTraceSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [state, setState] = useState<PageState>(serviceName ? 'loading' : 'idle');
  const autoSearched = useRef(false);

  const buildQuery = useCallback((cursor?: string): ApmTraceSearchParams => {
    const linkedStart = searchParams.get('started_at');
    const linkedEnd = searchParams.get('ended_at');
    const endedAt = linkedEnd ?? new Date().toISOString();
    const startedAt = linkedStart ?? new Date(new Date(endedAt).getTime() - RANGE_MS[timeRange]).toISOString();
    return {
      service_namespace: namespace,
      service_name: serviceName,
      environment,
      instance_id: instanceId || undefined,
      started_at: startedAt,
      ended_at: endedAt,
      cursor,
      limit: 20,
    };
  }, [environment, instanceId, namespace, searchParams, serviceName, timeRange]);

  const search = useCallback((cursor?: string) => {
    if (!serviceName.trim() || authLoading) {
      setState('idle');
      return;
    }
    setState('loading');
    getTraces(buildQuery(cursor))
      .then((page) => {
        setItems((current) => (cursor ? [...current, ...page.items] : page.items));
        setNextCursor(page.next_cursor);
        setState(page.items.length === 0 && !cursor ? 'empty' : 'ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, buildQuery, getTraces, serviceName]);

  useEffect(() => {
    if (!authLoading && serviceName && !autoSearched.current) {
      autoSearched.current = true;
      search();
    }
  }, [authLoading, search, serviceName]);

  const columns = useMemo<TableProps<ApmTraceSummary>['columns']>(() => [
    {
      title: '入口操作',
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{item.root_span_name || item.service_name}</Typography.Text>
          <Typography.Text type="secondary" className="font-mono text-xs">
            {item.trace_id.slice(0, 16)}
          </Typography.Text>
        </Space>
      ),
    },
    { title: '实例', dataIndex: 'instance_id', render: (value) => value || '身份缺失' },
    { title: 'Span', dataIndex: 'span_count', width: 80 },
    { title: '耗时', dataIndex: 'duration_ms', width: 120, render: (value) => `${value.toFixed(2)} ms` },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value) => <Tag color={value === 'error' ? 'error' : 'success'}>{value === 'error' ? '错误' : '正常'}</Tag>,
    },
    { title: '开始时间', dataIndex: 'started_at', width: 200, render: (value) => new Date(value).toLocaleString() },
  ], []);

  return (
    <ApmRouteShell
      title="Trace 搜索"
      description="使用受控的服务、环境、实例与时间窗搜索，不接受任意 TraceQL。"
      dependency="telemetry"
    >
      <Space wrap className="mb-4">
        <Input value={namespace} onChange={(event) => setNamespace(event.target.value)} placeholder="应用 namespace（可空）" />
        <Input value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="服务名（必填）" />
        <Input value={environment} onChange={(event) => setEnvironment(event.target.value)} placeholder="环境（可为空字符串）" />
        <Input value={instanceId} onChange={(event) => setInstanceId(event.target.value)} placeholder="实例 ID（可选）" />
        <Select<TimeRange>
          value={timeRange}
          onChange={(value) => {
            setTimeRange(value);
            router.replace('/apm/traces');
          }}
          options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))}
          className="w-24"
        />
        <Button type="primary" onClick={() => search()} disabled={!serviceName.trim()}>搜索</Button>
      </Space>
      {state === 'idle' ? (
        <CatalogState kind="empty" description="请输入服务名和环境后搜索 Trace。" />
      ) : state === 'ready' ? (
        <>
          <Table
            rowKey="trace_id"
            columns={columns}
            dataSource={items}
            pagination={false}
            onRow={(item) => ({ onClick: () => router.push(`/apm/traces/${item.trace_id}`), className: 'cursor-pointer' })}
          />
          {nextCursor ? <Button className="mt-4" onClick={() => search(nextCursor)}>加载更多</Button> : null}
        </>
      ) : (
        <CatalogState kind={state} description={state === 'empty' ? '当前条件下没有可见 Trace。' : undefined} />
      )}
    </ApmRouteShell>
  );
}
