'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchOutlined } from '@ant-design/icons';
import { Button, Input, Select, Table, Typography } from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import ServiceIdentity from '@/app/apm/components/service-identity';
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
        setState(page.items.length === 0 && !cursor && !page.next_cursor ? 'empty' : 'ready');
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
      title: '服务与入口操作',
      render: (_, item) => (
        <ServiceIdentity
          namespace={item.service_namespace}
          name={item.root_span_name || item.service_name}
          secondary={item.trace_id.slice(0, 16)}
        />
      ),
    },
    {
      title: '实例',
      dataIndex: 'instance_id',
      responsive: ['lg'],
      render: (value) => (
        <Typography.Text ellipsis className="block max-w-48 font-mono text-xs">
          {value || '身份缺失'}
        </Typography.Text>
      ),
    },
    { title: 'Span', dataIndex: 'span_count', width: 80, responsive: ['md'], className: 'tabular-nums' },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 120,
      render: (value) => <span className="font-medium tabular-nums">{value.toFixed(2)} ms</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value) => (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${value === 'error'
            ? 'bg-[color-mix(in_srgb,var(--color-fail)_10%,var(--color-bg))] text-[var(--color-fail)]'
            : 'bg-[color-mix(in_srgb,var(--color-success)_10%,var(--color-bg))] text-[var(--color-success)]'
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${value === 'error' ? 'bg-[var(--color-fail)]' : 'bg-[var(--color-success)]'}`}
            aria-hidden="true"
          />
          {value === 'error' ? '错误' : '正常'}
        </span>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      width: 200,
      responsive: ['lg'],
      render: (value) => <span className="tabular-nums">{new Date(value).toLocaleString()}</span>,
    },
  ], []);

  return (
    <ApmRouteShell
      title="Trace 搜索"
      description="使用受控的服务、环境、实例与时间窗搜索，不接受任意 TraceQL。"
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1.3fr_auto_auto] xl:items-end">
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">应用 namespace</span>
              <Input value={namespace} onChange={(event) => setNamespace(event.target.value)} placeholder="可留空" />
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">服务名</span>
              <Input value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="必填" />
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">环境</span>
              <Input value={environment} onChange={(event) => setEnvironment(event.target.value)} placeholder="可留空" />
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">实例 ID</span>
              <Input value={instanceId} onChange={(event) => setInstanceId(event.target.value)} placeholder="可选" />
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">时间窗</span>
              <Select<TimeRange>
                aria-label="时间窗"
                value={timeRange}
                onChange={(value) => {
                  setTimeRange(value);
                  router.replace('/apm/traces');
                }}
                options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))}
                className="w-full xl:w-24"
              />
            </label>
            <Button
              type="primary"
              icon={<SearchOutlined aria-hidden="true" />}
              onClick={() => search()}
              disabled={!serviceName.trim()}
            >
              搜索
            </Button>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'idle' ? (
            <CatalogState kind="empty" description="输入服务名和环境后搜索 Trace。" />
          ) : state === 'ready' ? (
            <>
              <Table
                rowKey="trace_id"
                columns={columns}
                dataSource={items}
                pagination={false}
                onRow={(item) => ({
                  onClick: () => router.push(`/apm/traces/${item.trace_id}`),
                  onKeyDown: (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      router.push(`/apm/traces/${item.trace_id}`);
                    }
                  },
                  role: 'link',
                  'aria-label': `查看 Trace ${item.trace_id}`,
                  tabIndex: 0,
                  className: 'cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] focus-visible:outline-offset-[-2px]',
                })}
              />
              {nextCursor ? (
                <div className="flex justify-center border-t border-[var(--color-border-1)] p-3">
                  <Button onClick={() => search(nextCursor)}>加载更多</Button>
                </div>
              ) : null}
            </>
          ) : (
            <CatalogState kind={state} description={state === 'empty' ? '当前条件下没有可见 Trace。' : undefined} />
          )}
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
