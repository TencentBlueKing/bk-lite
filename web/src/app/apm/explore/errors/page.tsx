'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { BugOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Collapse, Empty, Input, Radio, Select, Space, Tag, Typography } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { formatLatency, formatRelativeTime } from '@/app/apm/components/metric-format';
import type { ApmService, ApmTraceSummary } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready' | 'idle';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';

interface ErrorCluster {
  key: string;
  name: string;
  samples: ApmTraceSummary[];
  lastSeenAt: string;
  totalSpans: number;
  affectedVersions: string[];
}

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

function clusterErrors(items: ApmTraceSummary[]): ErrorCluster[] {
  const groups = new Map<string, ApmTraceSummary[]>();
  items.forEach((item) => {
    const key = item.root_span_name || '未命名错误操作';
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  });
  return Array.from(groups.entries())
    .map(([name, samples]) => {
      const sorted = [...samples].sort((left, right) => right.started_at.localeCompare(left.started_at));
      return {
        key: name,
        name,
        samples: sorted,
        lastSeenAt: sorted[0]?.started_at ?? '',
        totalSpans: samples.reduce((total, item) => total + item.span_count, 0),
        affectedVersions: [],
      };
    })
    .sort((left, right) => right.samples.length - left.samples.length);
}

export default function ApmErrorsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getServices, getTraces, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [serviceId, setServiceId] = useState(searchParams.get('service_id') ?? '');
  const [environment, setEnvironment] = useState(searchParams.get('environment') ?? '');
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<ApmTraceSummary[]>([]);
  const [state, setState] = useState<PageState>('loading');

  const selectedService = useMemo(
    () => services.find((service) => service.id === serviceId)
      || services.find((service) => service.name === searchParams.get('service_name')),
    [searchParams, serviceId, services],
  );

  const loadServices = useCallback(async () => {
    if (authLoading) return;
    setState('loading');
    try {
      const serviceItems = await getServices();
      setServices(serviceItems);
      const preferred = serviceItems.find((service) => service.id === serviceId)
        || serviceItems.find((service) => service.name === searchParams.get('service_name'));
      if (preferred) {
        setServiceId(preferred.id);
        if (!environment) setEnvironment(preferred.environment_views[0]?.environment ?? '');
      }
      setState('idle');
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [authLoading, environment, getServices, searchParams, serviceId]);

  useEffect(() => {
    loadServices();
  }, [loadServices]);

  const search = useCallback(async () => {
    if (!selectedService || !environment || authLoading) {
      setItems([]);
      setState('idle');
      return;
    }
    setState('loading');
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
    try {
      const page = await getTraces({
        service_namespace: selectedService.namespace,
        service_name: selectedService.name,
        environment,
        started_at: startedAt.toISOString(),
        ended_at: endedAt.toISOString(),
        limit: 100,
      });
      const errors = page.items.filter((item) => item.status === 'error');
      setItems(errors);
      setState(errors.length ? 'ready' : 'empty');
    } catch (error) {
      setItems([]);
      setState(catalogErrorKind(error));
    }
  }, [authLoading, environment, getTraces, selectedService, timeRange]);

  useEffect(() => {
    search();
  }, [search]);

  const clusters = useMemo(() => {
    const grouped = clusterErrors(items);
    const normalized = keyword.trim().toLocaleLowerCase();
    if (!normalized) return grouped;
    return grouped.filter((cluster) => (
      cluster.name.toLocaleLowerCase().includes(normalized)
      || cluster.samples.some((item) => item.trace_id.toLocaleLowerCase().includes(normalized))
    ));
  }, [items, keyword]);

  const affectedServices = new Set(items.map((item) => `${item.service_namespace}:${item.service_name}`)).size;
  const affectedTraces = items.length;

  const serviceOptions = services.map((service) => ({
    value: service.id,
    label: `${service.namespace || '未归类应用'} / ${service.name}`,
  }));
  const environmentOptions = selectedService?.environment_views.map((view) => ({
    value: view.environment,
    label: view.environment || '未设置环境',
  })) ?? [];

  return (
    <ApmRouteShell
      title="错误"
      description="从真实错误调用链下钻故障上下文；Issue 自动聚类将在数据能力就绪后接入。"
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        <Alert
          showIcon
          type="info"
          message="当前版本按错误调用链展示；Issue 聚类与异常栈聚合将在数据能力接入后开放。"
          description="以下卡片按入口操作做了客户端归并，便于浏览，不代表正式 Issue 模型。"
        />
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-3">
            <Radio.Group
              aria-label="时间范围"
              buttonStyle="solid"
              size="small"
              value={timeRange}
              onChange={(event) => setTimeRange(event.target.value)}
            >
              {(Object.keys(RANGE_MS) as TimeRange[]).map((value) => (
                <Radio.Button key={value} value={value}>{value}</Radio.Button>
              ))}
            </Radio.Group>
            <div className="flex-1" />
            <Select
              showSearch
              aria-label="服务"
              className="w-64"
              placeholder="选择服务"
              optionFilterProp="label"
              value={selectedService?.id || undefined}
              options={serviceOptions}
              onChange={(value) => {
                const service = services.find((item) => item.id === value);
                setServiceId(value);
                setEnvironment(service?.environment_views[0]?.environment ?? '');
              }}
            />
            <Select
              aria-label="环境"
              className="w-36"
              disabled={!selectedService}
              placeholder="选择环境"
              value={environment || undefined}
              options={environmentOptions}
              onChange={setEnvironment}
            />
            <Button aria-label="刷新错误调用链" icon={<ReloadOutlined aria-hidden="true" />} disabled={!selectedService || !environment} onClick={search} />
          </div>
        </ApmSurface>

        {selectedService ? (
          <ApmSurface padding="compact">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                { label: '错误分组', value: clusters.length, danger: true },
                { label: '受影响 Trace', value: affectedTraces },
                { label: '受影响服务', value: affectedServices },
                { label: '出现次数', value: items.length },
              ].map((metric) => (
                <div key={metric.label} className="border-r border-[var(--color-border-2)] px-3 last:border-r-0">
                  <Typography.Text type="secondary" className="text-xs">{metric.label}</Typography.Text>
                  <div className={`mt-1 text-xl font-semibold tabular-nums ${metric.danger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'}`}>
                    {metric.value}
                  </div>
                </div>
              ))}
            </div>
          </ApmSurface>
        ) : null}

        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'idle' ? (
            <Empty className="my-10" description="选择服务与环境后查看错误调用链。" />
          ) : state === 'ready' ? (
            <>
              <div className="border-b border-[var(--color-border-2)] p-3">
                <Input
                  allowClear
                  aria-label="搜索错误调用链"
                  className="w-80"
                  placeholder="搜索入口操作或 Trace ID"
                  prefix={<SearchOutlined aria-hidden="true" />}
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-3 bg-[var(--color-fill-1)] p-3">
                {clusters.map((cluster) => (
                  <article key={cluster.key} className="overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]">
                    <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <Space size={8} wrap>
                          <BugOutlined className="text-[var(--color-fail)]" aria-hidden="true" />
                          <Typography.Text strong className="font-mono text-sm">
                            {cluster.name}
                          </Typography.Text>
                          <Tag bordered={false} color="blue">入口归并</Tag>
                          <Typography.Text type="secondary" className="!text-xs">
                            {selectedService?.name} · {environment || '未设置'}
                          </Typography.Text>
                        </Space>
                        <Typography.Text type="secondary" className="mt-2 block !text-xs">
                          最近样本 Trace {cluster.samples[0]?.trace_id}
                        </Typography.Text>
                        <div className="mt-2 flex flex-wrap gap-3">
                          <Button
                            type="link"
                            size="small"
                            className="!px-0"
                            onClick={() => router.push(`/apm/explore/traces/${cluster.samples[0].trace_id}`)}
                          >
                            查看样本 Trace →
                          </Button>
                          <Button
                            type="link"
                            size="small"
                            className="!px-0"
                            onClick={() => router.push(`/apm/explore/traces?${new URLSearchParams({
                              service_namespace: selectedService?.namespace ?? '',
                              service_name: selectedService?.name ?? '',
                              environment,
                            }).toString()}`)}
                          >
                            查看相关调用链 →
                          </Button>
                        </div>
                      </div>
                      <div className="grid shrink-0 grid-cols-3 gap-8 text-right">
                        <div>
                          <div className="font-semibold tabular-nums text-[var(--color-fail)]">{cluster.samples.length}</div>
                          <Typography.Text type="secondary" className="text-xs">受影响 Trace</Typography.Text>
                        </div>
                        <div>
                          <div className="font-semibold tabular-nums text-[var(--color-fail)]">{cluster.samples.length}</div>
                          <Typography.Text type="secondary" className="text-xs">出现次数</Typography.Text>
                        </div>
                        <div>
                          <div className="text-[13px] tabular-nums">{formatRelativeTime(cluster.lastSeenAt)}</div>
                          <Typography.Text type="secondary" className="text-xs">最近出现</Typography.Text>
                        </div>
                      </div>
                    </div>
                    <Collapse
                      ghost
                      size="small"
                      items={[{
                        key: 'samples',
                        label: `样本列表（${cluster.samples.length}）`,
                        children: (
                          <div className="flex flex-col gap-2">
                            {cluster.samples.slice(0, 8).map((item) => (
                              <button
                                key={item.trace_id}
                                type="button"
                                className="flex items-center justify-between gap-3 rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-left hover:bg-[var(--color-primary-bg-active)]"
                                onClick={() => router.push(`/apm/explore/traces/${item.trace_id}`)}
                              >
                                <span className="min-w-0 truncate font-mono text-xs">{item.trace_id}</span>
                                <span className="shrink-0 text-xs tabular-nums text-[var(--color-text-3)]">
                                  {formatLatency(item.duration_ms)} · {formatRelativeTime(item.started_at)}
                                </span>
                              </button>
                            ))}
                          </div>
                        ),
                      }]}
                    />
                  </article>
                ))}
              </div>
            </>
          ) : (
            <CatalogState kind={state} description={state === 'empty' ? '当前条件下没有错误调用链。' : undefined} />
          )}
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
