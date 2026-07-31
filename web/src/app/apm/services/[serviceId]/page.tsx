'use client';

import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeftOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Col, Row, Segmented, Select, Space, Tag, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmService, ApmServiceRed } from '@/app/apm/types';
import SummaryMetricCard from '@/components/summary-metric-card';

type PageState = CatalogStateKind | 'ready';
type TimeRange = '15m' | '1h' | '4h' | '24h';

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
};

export default function ApmServiceDetailPage() {
  const params = useParams<{ serviceId: string }>();
  const searchParams = useSearchParams();
  const { getService, getServiceRed, isLoading: authLoading } = useApmApi();
  const [service, setService] = useState<ApmService>();
  const [environment, setEnvironment] = useState<string | undefined>(
    searchParams.get('environment') ?? undefined
  );
  const [red, setRed] = useState<ApmServiceRed>();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [catalogState, setCatalogState] = useState<PageState>('loading');
  const [metricState, setMetricState] = useState<PageState>('loading');

  useEffect(() => {
    if (authLoading || !params.serviceId) return;
    let active = true;
    getService(params.serviceId)
      .then((item) => {
        if (!active) return;
        setService(item);
        const available = item.environment_views.map((view) => view.environment);
        setEnvironment((current) =>
          current !== undefined && available.includes(current) ? current : available[0]
        );
        setCatalogState('ready');
      })
      .catch((error) => {
        if (active) setCatalogState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, getService, params.serviceId]);

  useEffect(() => {
    if (!service || environment === undefined) {
      setMetricState('empty');
      return;
    }
    let active = true;
    setMetricState('loading');
    const endedAt = new Date().toISOString();
    const startedAt = new Date(new Date(endedAt).getTime() - RANGE_MS[timeRange]).toISOString();
    getServiceRed(service.id, environment, startedAt, endedAt)
      .then((value) => {
        if (!active) return;
        setRed(value);
        setMetricState('ready');
      })
      .catch((error) => {
        if (active) setMetricState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [environment, getServiceRed, service, timeRange]);

  const traceHref = service && red
    ? `/apm/traces?${new URLSearchParams({
      service_namespace: service.namespace,
      service_name: service.name,
      environment: red.environment,
      started_at: red.started_at,
      ended_at: red.ended_at,
    }).toString()}`
    : '/apm/traces';

  return (
    <ApmRouteShell
      title="服务详情"
      description="在固定服务身份下切换环境与时间窗，查看 RED 指标并下钻 Trace。"
      dependency="telemetry"
    >
      {catalogState !== 'ready' ? (
        <ApmSurface padding="none"><CatalogState kind={catalogState} /></ApmSurface>
      ) : service ? (
        <div className="flex flex-col gap-4">
          <ApmSurface padding="compact">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <Link href="/apm/services">
                  <Button aria-label="返回服务目录" icon={<ArrowLeftOutlined aria-hidden="true" />} />
                </Link>
                <div className="min-w-0">
                  <Space size={8} wrap>
                    <Typography.Title level={2} className="!mb-0 !text-lg !font-semibold">
                      {service.name}
                    </Typography.Title>
                    <Tag bordered={false}>{environment || '未设置'}</Tag>
                    <ApmStatusTag status={service.status} />
                  </Space>
                  <Typography.Text type="secondary" className="block truncate text-xs">
                    所属应用 {service.namespace || '未归类应用'}
                  </Typography.Text>
                </div>
              </div>
              <Space wrap>
                <Select
                  aria-label="选择环境"
                  className="min-w-40"
                  value={environment}
                  onChange={setEnvironment}
                  options={service.environment_views.map((item) => ({
                    value: item.environment,
                    label: item.environment || '未设置',
                  }))}
                />
                <Segmented<TimeRange>
                  aria-label="选择时间窗"
                  value={timeRange}
                  onChange={setTimeRange}
                  options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))}
                />
                {metricState === 'ready' ? (
                  <Link href={traceHref}>
                    <Button icon={<SearchOutlined aria-hidden="true" />}>查看 Trace</Button>
                  </Link>
                ) : null}
              </Space>
            </div>
          </ApmSurface>
          {metricState === 'ready' && red ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12} xl={6}>
                <SummaryMetricCard
                  layout="vertical"
                  label="请求速率"
                  value={red.request_rate.toFixed(2)}
                  unit="req/s"
                  className="h-full bg-[var(--color-bg)] p-4"
                />
              </Col>
              <Col xs={24} md={12} xl={6}>
                <SummaryMetricCard
                  layout="vertical"
                  label="错误率"
                  value={(red.error_rate * 100).toFixed(2)}
                  unit="%"
                  valueColor={red.error_rate > 0.05 ? 'var(--color-fail)' : 'var(--color-text-1)'}
                  className="h-full bg-[var(--color-bg)] p-4"
                />
              </Col>
              <Col xs={24} md={12} xl={6}>
                <SummaryMetricCard
                  layout="vertical"
                  label="P95 延迟"
                  value={red.p95_ms.toFixed(1)}
                  unit="ms"
                  className="h-full bg-[var(--color-bg)] p-4"
                />
              </Col>
              <Col xs={24} md={12} xl={6}>
                <SummaryMetricCard
                  layout="vertical"
                  label="P99 延迟"
                  value={red.p99_ms.toFixed(1)}
                  unit="ms"
                  className="h-full bg-[var(--color-bg)] p-4"
                />
              </Col>
            </Row>
          ) : (
            <ApmSurface padding="none">
              <CatalogState
                kind={metricState === 'ready' ? 'error' : metricState}
                description={metricState === 'empty' ? '当前服务尚无可查询的环境视图。' : undefined}
              />
            </ApmSurface>
          )}
        </div>
      ) : null}
    </ApmRouteShell>
  );
}
