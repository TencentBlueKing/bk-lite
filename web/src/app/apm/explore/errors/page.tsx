'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Alert, Button, Select } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import ApmIssueList from '@/app/apm/components/issue-list';
import type { ApmIssue, ApmService } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';
const RANGE_MS: Record<TimeRange, number> = { '15m': 900000, '1h': 3600000, '4h': 14400000, '1d': 86400000, '7d': 604800000 };
const TIME_RANGES = Object.keys(RANGE_MS) as TimeRange[];

function isTimeRange(value: string | null): value is TimeRange {
  return TIME_RANGES.includes(value as TimeRange);
}

export default function ApmErrorsPage() {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getIssues, getServices, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [serviceId, setServiceId] = useState<string>();
  const [environment, setEnvironment] = useState<string | undefined>(searchParams.get('environment') || undefined);
  const [timeRange, setTimeRange] = useState<TimeRange>(() => {
    const value = searchParams.get('window');
    return isTimeRange(value) ? value : '1h';
  });
  const [items, setItems] = useState<ApmIssue[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [state, setState] = useState<PageState>('loading');
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (!authLoading) void getServices().then(setServices).catch(() => setServices([]));
  }, [authLoading, getServices]);
  useEffect(() => {
    const namespace = searchParams.get('service_namespace');
    const name = searchParams.get('service_name');
    if (!namespace || !name) return;
    const found = services.find((service) => service.namespace === namespace && service.name === name);
    if (found) setServiceId(found.id);
  }, [searchParams, services]);
  const environments = useMemo(() => Array.from(new Set(services.flatMap((service) => service.environment_views.map((view) => view.environment)))).sort(), [services]);
  const selectedService = useMemo(() => services.find((service) => service.id === serviceId), [serviceId, services]);
  const load = useCallback((cursor?: string) => {
    if (authLoading) return;
    if (cursor) setLoadingMore(true); else setState('loading');
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
    void getIssues({ service_namespace: selectedService?.namespace, service_name: selectedService?.name, environment, started_at: startedAt.toISOString(), ended_at: endedAt.toISOString(), cursor, limit: 50 })
      .then((page) => {
        setItems((current) => cursor ? [...current, ...page.items] : page.items);
        setNextCursor(page.next_cursor); setTruncated(page.truncated);
        setState(page.items.length || cursor || page.next_cursor ? 'ready' : 'empty');
      }).catch((error) => setState(catalogErrorKind(error))).finally(() => setLoadingMore(false));
  }, [authLoading, environment, getIssues, selectedService, timeRange]);
  useEffect(() => { load(); }, [load]);

  return (
    <ApmRouteShell title={t('apm.errors.title', '错误分析')} description={t('apm.errors.description', '按真实异常语义聚类 Error Span，并下钻版本、端点和样本 Trace。')}>
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Select className="w-52" allowClear showSearch optionFilterProp="label" placeholder={t('apm.errors.allServices', '全部服务')} value={serviceId} options={services.map((service) => ({ value: service.id, label: `${service.namespace} / ${service.name}` }))} onChange={setServiceId} />
            <Select className="w-44" allowClear showSearch placeholder={t('apm.errors.allEnvironments', '全部环境')} value={environment} options={environments.map((value) => ({ value, label: value || t('apm.common.unset', '未设置') }))} onChange={setEnvironment} />
            <Select<TimeRange> className="w-28" value={timeRange} options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))} onChange={setTimeRange} />
          </FilterToolbar>
          {truncated ? <Alert showIcon type="info" message={t('apm.errors.boundedHint', '结果按时间窗和游标有界展示，可继续加载更早样本。')} /> : null}
          {state === 'ready' ? (
            <div className="flex flex-col gap-4">
              {!items.length ? <CatalogState kind="empty" description={t('apm.errors.emptyPage', '当前游标页没有可见 Issue，可继续加载更早样本。')} /> : null}
              <ApmIssueList items={items} />
              {nextCursor ? <Button loading={loadingMore} onClick={() => load(nextCursor)}>{t('apm.common.loadMore', '加载更多')}</Button> : null}
            </div>
          ) : state === 'empty' ? (
            <CatalogState kind="empty" description={t('apm.errors.empty', '当前权限和时间窗内没有错误 Issue。')} />
          ) : (
            <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => load()} />
          )}
        </div>
      </ApmSurface>
    </ApmRouteShell>
  );
}
