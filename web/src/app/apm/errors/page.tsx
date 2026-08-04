'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { BugOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Collapse, Empty, Input, Radio, Select, Space, Tag, Typography } from 'antd';
import { useRouter } from 'next/navigation';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmService, ApmTraceSummary } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready' | 'idle';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

export default function ApmErrorsPage() {
  const router = useRouter();
  const { getServices, getTraces, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [serviceId, setServiceId] = useState('');
  const [environment, setEnvironment] = useState('');
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<ApmTraceSummary[]>([]);
  const [state, setState] = useState<PageState>('loading');

  const selectedService = useMemo(
    () => services.find((service) => service.id === serviceId),
    [serviceId, services],
  );

  const loadServices = useCallback(async () => {
    if (authLoading) return;
    setState('loading');
    try {
      const serviceItems = await getServices();
      setServices(serviceItems);
      setState('idle');
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [authLoading, getServices]);

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

  const visibleItems = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase();
    if (!normalized) return items;
    return items.filter((item) => (
      item.root_span_name.toLocaleLowerCase().includes(normalized)
      || item.trace_id.toLocaleLowerCase().includes(normalized)
    ));
  }, [items, keyword]);

  const affectedServices = new Set(items.map((item) => `${item.service_namespace}:${item.service_name}`)).size;
  const averageDuration = items.length
    ? items.reduce((total, item) => total + item.duration_ms, 0) / items.length
    : 0;

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
              value={serviceId || undefined}
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
                { label: '错误调用链', value: items.length, danger: true },
                { label: '受影响 Trace', value: items.length },
                { label: '受影响服务', value: affectedServices },
                { label: '平均耗时', value: `${averageDuration.toFixed(2)} ms` },
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
              <div className="flex flex-col gap-3 bg-[var(--color-bg-1)] p-3">
                {visibleItems.map((item) => (
                  <article key={item.trace_id} className="overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)]">
                    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border-2)] bg-[var(--color-primary-bg)] px-3 py-2">
                      <Tag bordered={false}>{item.service_name}</Tag>
                      <Tag bordered={false}>{item.environment || '未设置环境'}</Tag>
                      <Button
                        type="link"
                        size="small"
                        className="px-0"
                        onClick={() => router.push(`/apm/traces/${item.trace_id}`)}
                      >
                        查看样本 Trace →
                      </Button>
                    </div>
                    <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <Space size={8}>
                          <BugOutlined className="text-[var(--color-fail)]" aria-hidden="true" />
                          <Typography.Text strong className="font-mono text-sm">
                            {item.root_span_name || '未命名错误操作'}
                          </Typography.Text>
                          <Tag bordered={false} color="error">错误 Trace</Tag>
                        </Space>
                        <Typography.Text type="secondary" className="mt-1 block truncate font-mono text-xs">
                          Trace {item.trace_id}
                        </Typography.Text>
                      </div>
                      <div className="grid shrink-0 grid-cols-3 gap-8 text-right">
                        <div>
                          <div className="font-semibold tabular-nums text-[var(--color-fail)]">{item.span_count}</div>
                          <Typography.Text type="secondary" className="text-xs">跨度数</Typography.Text>
                        </div>
                        <div>
                          <div className="font-semibold tabular-nums">{item.duration_ms.toFixed(2)} ms</div>
                          <Typography.Text type="secondary" className="text-xs">总耗时</Typography.Text>
                        </div>
                        <div>
                          <div className="text-xs tabular-nums">{new Date(item.started_at).toLocaleString()}</div>
                          <Typography.Text type="secondary" className="text-xs">最近出现</Typography.Text>
                        </div>
                      </div>
                    </div>
                    <Collapse
                      ghost
                      size="small"
                      items={[{
                        key: 'context',
                        label: '调用上下文',
                        children: (
                          <div className="grid gap-2 rounded-md bg-[var(--color-fill-1)] p-3 text-xs md:grid-cols-2">
                            <span><Typography.Text type="secondary">应用：</Typography.Text>{item.service_namespace || '未归类应用'}</span>
                            <span><Typography.Text type="secondary">服务：</Typography.Text>{item.service_name}</span>
                            <span><Typography.Text type="secondary">环境：</Typography.Text>{item.environment || '未设置环境'}</span>
                            <span className="font-mono"><Typography.Text type="secondary">Trace ID：</Typography.Text>{item.trace_id}</span>
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
