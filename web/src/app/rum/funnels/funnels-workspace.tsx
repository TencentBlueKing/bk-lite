'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import {
  Button,
  Empty,
  Popconfirm,
  Select,
  type TableColumnsType,
} from 'antd';

import { useRumQueries, type RumFunnelItem } from '@/app/rum/api';
import {
  RumDualWorkbench,
  RumFilterBlock,
} from '@/app/rum/components/rum-dual-workbench';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import RumPermission from '@/app/rum/components/rum-permission';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import { RumFunnelsReachSkeleton, RumFunnelsSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import TrafficScopeControl from '@/app/rum/components/traffic-scope';
import { degradationReason } from '@/app/rum/lib/degradation';
import { displayRoute } from '@/app/rum/lib/format';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import FunnelFormDrawer from '@/app/rum/funnels/ui/funnel-form-drawer';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';

export default function FunnelsWorkspace() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams<{ id?: string }>();
  const routeId = params.id ? decodeURIComponent(params.id) : '';
  const { range, setRange, traffic, searchParams, setParams } = useRumSearchParams();
  const { listFunnels, deleteFunnel, funnelReach, authReady } = useRumQueries();

  const [items, setItems] = useState<RumFunnelItem[]>([]);
  const [pending, setPending] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<RumFunnelItem | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [reached, setReached] = useState<number[]>([]);
  const [reachPending, setReachPending] = useState(false);
  const [reachDegrade, setReachDegrade] = useState<ReturnType<typeof degradationReason>>(null);

  const selectedId = routeId || searchParams.get('funnel') || items[0]?.id || '';
  const activeFunnel = useMemo(
    () => items.find((f) => f.id === selectedId) || items[0] || null,
    [items, selectedId],
  );

  const load = useCallback(async () => {
    setPending(true);
    try {
      setItems(await listFunnels());
    } catch {
      setItems([]);
    } finally {
      setPending(false);
    }
  }, [listFunnels]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listFunnels()
        .then((next) => {
          if (!isCancelled()) setItems(next);
        })
        .catch(() => {
          if (!isCancelled()) setItems([]);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [listFunnels],
  );

  const runReach = useCallback(
    async (funnel: RumFunnelItem) => {
      setReachPending(true);
      try {
        const query: Record<string, string> = { range, traffic };
        if (funnel.application) query.application = funnel.application;
        const result = await funnelReach(funnel.id, query);
        setReached(result.reached);
        setReachDegrade(degradationReason(result));
      } catch {
        setReached([]);
        setReachDegrade(null);
      } finally {
        setReachPending(false);
      }
    },
    [funnelReach, range, traffic],
  );

  useEffect(() => {
    if (!authReady) return;
    if (activeFunnel) void runReach(activeFunnel);
    else setReached([]);
  }, [authReady, activeFunnel, runReach]);

  function selectFunnel(id: string) {
    if (routeId) {
      router.push(`/rum/funnels/${encodeURIComponent(id)}`);
    } else {
      setParams({ funnel: id });
    }
  }

  async function remove(funnel: RumFunnelItem) {
    setDeleting(funnel.id);
    try {
      await deleteFunnel(funnel.id);
      const remaining = items.filter((item) => item.id !== funnel.id);
      setItems(remaining);
      if (activeFunnel?.id === funnel.id && remaining[0]) {
        selectFunnel(remaining[0].id);
      }
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setDeleting(null);
    }
  }

  const steps = activeFunnel?.steps || [];
  const max = reached[0] || 0;
  const overall =
    reached.length > 1 && max > 0
      ? Math.round(((reached[reached.length - 1] || 0) / max) * 100)
      : null;

  const topDropoff = useMemo(() => {
    let worst = -1;
    let worstIdx = -1;
    for (let i = 1; i < reached.length; i++) {
      const prev = reached[i - 1] || 0;
      const cur = reached[i] || 0;
      if (prev <= 0) continue;
      const drop = Math.round(((prev - cur) / prev) * 100);
      if (drop > worst) {
        worst = drop;
        worstIdx = i;
      }
    }
    return worstIdx >= 0 ? { index: worstIdx, pct: worst } : null;
  }, [reached]);

  const stepColumns: TableColumnsType<{ step: string; index: number }> = [
    {
      title: t('rum.funnels.step', '步骤'),
      key: 'index',
      width: '8%',
      render: (_, row) => (
        <span className="font-mono tabular-nums">
          {String(row.index + 1).padStart(2, '0')}
        </span>
      ),
    },
    {
      title: t('rum.views.route', '路由'),
      key: 'step',
      width: '24%',
      render: (_, row) => (
        <span className="font-mono">
          {row.step}
        </span>
      ),
    },
    {
      title: t('rum.funnels.retention', '流转留存'),
      key: 'retention',
      width: '32%',
      render: (_, row) => {
        const count = reached[row.index] || 0;
        const pct = max > 0 ? Math.round((count / max) * 100) : 0;
        return (
          <div className="flex items-center gap-3">
            <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-[var(--color-fill-2)]">
              <div
                className="h-full rounded-full bg-[var(--color-primary)] transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-24 shrink-0 font-mono tabular-nums">
              <span>{count}</span>
              <span className="ml-1 text-xs text-[var(--color-text-3)]">({pct}%)</span>
            </span>
          </div>
        );
      },
    },
    {
      title: t('rum.funnels.convFromPrev', '相对上步转化'),
      key: 'fromPrev',
      width: '12%',
      render: (_, row) => {
        if (row.index === 0) return <span className="text-[var(--color-text-4)]">—</span>;
        const prev = reached[row.index - 1] || 0;
        const cur = reached[row.index] || 0;
        if (prev <= 0) return <span className="text-[var(--color-text-4)]">—</span>;
        return (
          <span className="font-mono tabular-nums">
            {Math.round((cur / prev) * 100)}%
          </span>
        );
      },
    },
    {
      title: t('rum.funnels.convFromFirst', '相对首步转化'),
      key: 'fromFirst',
      width: '12%',
      render: (_, row) => {
        const cur = reached[row.index] || 0;
        if (max <= 0) return <span className="text-[var(--color-text-4)]">—</span>;
        return (
          <span className="font-mono tabular-nums">
            {Math.round((cur / max) * 100)}%
          </span>
        );
      },
    },
    {
      title: t('rum.funnels.dropoff', '本步流失'),
      key: 'dropoff',
      width: '12%',
      render: (_, row) => {
        if (row.index === steps.length - 1) {
          return <span className="text-[var(--color-text-4)]">{t('rum.funnels.endpoint', '终点')}</span>;
        }
        const cur = reached[row.index] || 0;
        const next = reached[row.index + 1] || 0;
        if (cur <= 0) return <span className="text-[var(--color-text-4)]">—</span>;
        const dropCount = cur - next;
        const dropPct = Math.round((dropCount / cur) * 100);
        if (dropCount <= 0) return <span className="font-mono">0</span>;
        return (
          <span className="font-mono tabular-nums text-[var(--color-fail)]">
            ↘ {dropPct}% <span className="text-xs font-normal opacity-70">({dropCount})</span>
          </span>
        );
      },
    },
  ];

  const newButton = (
    <RumPermission resource="funnels" action="Operate">
      <Button
        type="primary"
        size="small"
        icon={<PlusOutlined />}
        onClick={() => {
          setEditing(null);
          setDrawerOpen(true);
        }}
      >
        {t('common.new', '新建')}
      </Button>
    </RumPermission>
  );

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.funnels.title', '转化漏斗')}</h1>

      <FunnelFormDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        initial={editing}
        onSaved={() => void load()}
      />

      {pending && items.length === 0 ? (
        <RumFunnelsSkeleton />
      ) : items.length === 0 ? (
        <RumDualWorkbench
          asideTitle={t('rum.funnels.title', '转化漏斗')}
          aside={
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('rum.funnels.empty', '还没有漏斗')}
            />
          }
          mainTitle={t('rum.funnels.title', '转化漏斗')}
          mainExtra={newButton}
          main={
            <div className="flex min-h-0 flex-1 items-center justify-center">
              <Empty
                description={
                  <div>
                    <p className="m-0 text-sm font-semibold">{t('rum.funnels.empty', '还没有漏斗')}</p>
                    <p className="mt-1 text-xs text-[var(--color-text-3)]">
                      {t('rum.funnels.emptyHint', '创建一条路径，用现有浏览数据测算转化。')}
                    </p>
                  </div>
                }
              />
            </div>
          }
        />
      ) : (
        <RumDualWorkbench
          asideTitle={t('rum.funnels.title', '转化漏斗')}
          aside={
            <>
              <RumFilterBlock title={t('rum.common.timeWindow', '时间')}>
                <RumRangeSegmented block size="small" value={range} onChange={setRange} />
              </RumFilterBlock>
              <RumFilterBlock title={t('rum.traffic.label', '流量')}>
                <TrafficScopeControl block size="small" />
              </RumFilterBlock>
              <div className="border-t border-[var(--color-fill-2)] pt-3">
                <div className="mb-2 flex items-center justify-between text-[12px] font-medium text-[var(--color-text-2)]">
                  <span>{t('rum.funnels.list', '漏斗列表')}</span>
                  <span className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 font-mono text-[11px] font-medium tabular-nums text-[var(--color-text-3)]">
                    {items.length}
                  </span>
                </div>
                <div className="-mx-3.5 divide-y divide-[var(--color-border-2)] border-y border-[var(--color-border-2)] bg-[var(--color-bg)]">
                  {items.map((f) => {
                    const selected = f.id === activeFunnel?.id;
                    const stepCount = f.steps?.length || 0;
                    const firstStep = f.steps?.[0] ? displayRoute(f.steps[0]) : '';
                    const lastStep = f.steps?.[f.steps.length - 1] ? displayRoute(f.steps[f.steps.length - 1]) : '';
                    const pathPreview =
                      firstStep && lastStep && firstStep !== lastStep
                        ? `${firstStep} → ${lastStep}`
                        : firstStep || '—';

                    return (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => selectFunnel(f.id)}
                        className={[
                          'group relative block w-full p-3 text-left transition-colors',
                          selected
                            ? 'border-l-[3px] border-l-[var(--color-primary)] bg-[var(--color-fill-2)] pl-[9px]'
                            : 'border-l-[3px] border-l-transparent hover:bg-[var(--color-fill-1)] pl-[9px]',
                        ].join(' ')}
                      >
                        <div className="mb-1.5 flex items-start justify-between gap-2">
                          <span
                            className={[
                              'truncate text-[13px] leading-tight',
                              selected
                                ? 'font-medium text-[var(--color-primary)]'
                                : 'font-medium text-[var(--color-text-1)] group-hover:text-[var(--color-primary)]',
                            ].join(' ')}
                            title={f.name}
                          >
                            {f.name}
                          </span>
                          <div className="flex shrink-0 items-center gap-1.5 pl-1">
                            <span
                              className={[
                                'inline-flex items-center justify-center rounded-full px-1.5 py-[1px] font-mono text-[10px] font-medium leading-none tabular-nums',
                                selected
                                  ? 'bg-[var(--color-primary)] text-white'
                                  : 'bg-[var(--color-fill-3)] text-[var(--color-text-2)]',
                              ].join(' ')}
                            >
                              {stepCount} {t('rum.funnels.stepUnit', '步')}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-[12px] text-[var(--color-text-3)]">
                          <div className="flex min-w-0 items-center gap-1 truncate">
                            <span
                              className="truncate font-medium text-[var(--color-text-2)]"
                              title={f.application || t('rum.filter.allApps', '全部应用')}
                            >
                              {f.application || t('rum.filter.allApps', '全部应用')}
                            </span>
                            <span>·</span>
                            <span className="truncate font-mono text-[11px] text-[var(--color-text-4)]" title={pathPreview}>
                              {pathPreview}
                            </span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
          }
          mainTitle={activeFunnel?.name || t('rum.funnels.title', '转化漏斗')}
          mainExtra={newButton}
          main={
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
              <div className="lg:hidden">
                <Select
                  className="w-full"
                  value={activeFunnel?.id}
                  onChange={selectFunnel}
                  options={items.map((f) => ({
                    value: f.id,
                    label: `${f.name} (${f.application || t('rum.filter.allApps', '全部应用')} · ${f.steps?.length || 0})`,
                  }))}
                />
                <div className="mt-2">
                  <RumListToolbar
                    spacing="flush"
                    trailing={
                      <>
                        <RumRangeSegmented value={range} onChange={setRange} />
                        <TrafficScopeControl />
                      </>
                    }
                  />
                </div>
              </div>
              {!activeFunnel ? (
                <div className="flex flex-1 items-center justify-center text-sm text-[var(--color-text-3)]">
                  {t('rum.funnels.empty', '还没有漏斗')}
                </div>
              ) : (
                <div className="flex min-w-0 flex-col gap-5">
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-1">
                    <div className="min-w-0">
                      <h2 className="text-lg font-semibold tracking-tight text-[var(--color-text-1)]">
                        {activeFunnel.name}
                      </h2>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-[var(--color-text-3)]">
                        <span className="font-medium text-[var(--color-text-2)]">
                          {activeFunnel.application || t('rum.filter.allApps', '全部应用')}
                        </span>
                        <span className="text-[var(--color-text-4)]">·</span>
                        <div className="inline-flex flex-wrap items-center gap-1">
                          {activeFunnel.steps.map((step, i) => (
                            <span key={`${step}-${i}`} className="inline-flex items-center gap-1">
                              {i > 0 ? <span className="text-[11px] text-[var(--color-text-4)]">→</span> : null}
                              <span className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--color-text-2)]">
                                {step}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <RumPermission
                      resource="funnels"
                      action="Operate"
                      className="inline-flex shrink-0 items-center gap-2"
                    >
                      <Button
                        icon={<EditOutlined aria-hidden="true" />}
                        onClick={() => {
                          setEditing(activeFunnel);
                          setDrawerOpen(true);
                        }}
                      >
                        {t('rum.funnels.edit', '编辑')}
                      </Button>
                      <Button
                        icon={<CopyOutlined aria-hidden="true" />}
                        onClick={() => {
                          setEditing({
                            ...activeFunnel,
                            id: '',
                            name: `${activeFunnel.name} (copy)`,
                          });
                          setDrawerOpen(true);
                        }}
                      >
                        {t('rum.funnels.duplicate', '复制')}
                      </Button>
                      <Popconfirm
                        title={t('rum.funnels.deleteConfirm', '确认删除漏斗「{name}」？', {
                          name: activeFunnel.name,
                        })}
                        onConfirm={() => void remove(activeFunnel)}
                        okText={t('rum.funnels.delete', '删除')}
                        cancelText={t('rum.common.cancel', '取消')}
                        okButtonProps={{ danger: true }}
                      >
                        <Button
                          icon={<DeleteOutlined aria-hidden="true" />}
                          loading={deleting === activeFunnel.id}
                        >
                          {t('rum.funnels.delete', '删除')}
                        </Button>
                      </Popconfirm>
                    </RumPermission>
                  </div>

                  {reachDegrade ? <PipelineDegradedBanner reason={reachDegrade} /> : null}

                  {reachPending ? (
                    <RumFunnelsReachSkeleton columns={rumSkeletonColumns(stepColumns)} />
                  ) : (
                    <>
                      <RumMetricGrid
                        cells={[
                          {
                            label: t('rum.funnels.conversionRate', '整体转化率'),
                            value: max > 0 && overall != null ? `${overall}%` : '—',
                            tone:
                              overall == null
                                ? undefined
                                : overall < 20
                                  ? 'danger'
                                  : overall < 50
                                    ? 'warning'
                                    : 'success',
                          },
                          {
                            label: t('rum.funnels.overall', '首步→末步'),
                            value: max > 0 ? `${reached[0] || 0} → ${reached[reached.length - 1] || 0}` : '0 → 0',
                          },
                          {
                            label: t('rum.funnels.topDropoff', '流失最多步骤'),
                            value:
                              max > 0 && topDropoff && steps[topDropoff.index]
                                ? `${steps[topDropoff.index]} · ${topDropoff.pct}%`
                                : '—',
                            tone: topDropoff && topDropoff.pct >= 50 ? 'danger' : undefined,
                          },
                        ]}
                      />

                      <div className="flex flex-col gap-3 pt-1">
                        <div className="flex items-center gap-2">
                          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
                            {t('rum.funnels.steps', '步骤转化明细')}
                          </h3>
                        </div>
                        <CustomTable
                          rowKey={(row) => `${row.step}-${row.index}`}
                          size="middle"
                          pagination={false}
                          dataSource={steps.map((step, index) => ({ step, index }))}
                          columns={stepColumns}
                        />
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          }
        />
      )}
    </div>
  );
}
