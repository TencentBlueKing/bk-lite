'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Empty, Input, Popconfirm, Select, Switch, type TableColumnsType } from 'antd';

import { useRumQueries, type RumMonitorItem } from '@/app/rum/api';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import { RumSingleWorkbench } from '@/app/rum/components/rum-dual-workbench';
import RumPermission from '@/app/rum/components/rum-permission';
import { RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import MonitorFormDrawer from '@/app/rum/monitors/ui/monitor-form-drawer';
import CustomTable from '@/components/custom-table';
import SemanticBadge from '@/components/semantic-badge';
import { toneSemanticPalette } from '@/app/rum/lib/cwv';
import { useTranslation } from '@/utils/i18n';

function metricLabel(t: (key: string, fallback?: string) => string, metric: string): string {
  return t(`rum.monitors.metric.${metric}`, metric);
}

function formatThreshold(metric: string, value: number): string {
  if (metric === 'error_rate') return `${(value * 100).toFixed(1)}%`;
  if (metric === 'cls_p75') return value.toFixed(3);
  return `${Math.round(value)}ms`;
}

const severityTone: Record<string, 'info' | 'warning' | 'danger' | 'neutral'> = {
  info: 'info',
  warning: 'warning',
  critical: 'danger',
};

export default function RumMonitorsPage() {
  const { t } = useTranslation();
  const { application: appFromUrl, searchParams } = useRumSearchParams();
  const focusRule = searchParams.get('rule')?.trim() || undefined;
  const { listMonitors, updateMonitor, deleteMonitor, listApplications, authReady } = useRumQueries();

  const [items, setItems] = useState<RumMonitorItem[]>([]);
  const [apps, setApps] = useState<string[]>([]);
  const [selectedApp, setSelectedApp] = useState(appFromUrl);
  const [query, setQuery] = useState('');
  const [pending, setPending] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<RumMonitorItem | null>(null);

  const load = useCallback(async () => {
    setPending(true);
    try {
      setItems(await listMonitors());
    } catch {
      setItems([]);
    } finally {
      setPending(false);
    }
  }, [listMonitors]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listMonitors()
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
    [listMonitors],
  );

  useEffect(() => {
    setSelectedApp(appFromUrl);
  }, [appFromUrl]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      void listApplications()
        .then((list) => {
          if (!isCancelled()) setApps(list.map((a) => a.application).filter(Boolean));
        })
        .catch(() => {
          if (!isCancelled()) setApps([]);
        });
    },
    [listApplications],
  );

  async function toggleEnabled(item: RumMonitorItem) {
    setActing(item.id);
    try {
      await updateMonitor(item.id, { ...item, enabled: !item.enabled });
      await load();
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(null);
    }
  }

  async function remove(item: RumMonitorItem) {
    setActing(item.id);
    try {
      await deleteMonitor(item.id);
      await load();
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(null);
    }
  }

  const appOptions = useMemo(() => {
    const set = new Set(apps);
    items.forEach((m) => {
      if (m.application) set.add(m.application);
    });
    return Array.from(set).map((app) => ({ value: app, label: app }));
  }, [apps, items]);

  const filteredItems = useMemo(() => {
    return items.filter((m) => {
      if (selectedApp && m.application !== selectedApp) return false;
      if (query.trim()) {
        const q = query.trim().toLowerCase();
        const matchName = m.name.toLowerCase().includes(q);
        const matchApp = m.application.toLowerCase().includes(q);
        const matchMetric = metricLabel(t, m.metric).toLowerCase().includes(q);
        if (!matchName && !matchApp && !matchMetric) return false;
      }
      return true;
    });
  }, [items, selectedApp, query, t]);
  const table = useRumClientPager(filteredItems, `${selectedApp}|${query}`);

  const columns = useMemo<TableColumnsType<RumMonitorItem>>(
    () => [
      {
        title: t('rum.monitors.name', '名称'),
        key: 'name',
        ellipsis: true,
        render: (_: unknown, m: RumMonitorItem) => <span className="truncate">{m.name}</span>,
      },
      {
        title: t('rum.applications.application', '应用'),
        key: 'application',
        width: 140,
        render: (_: unknown, m: RumMonitorItem) => (
          <span className="font-mono">{m.application}</span>
        ),
      },
      {
        title: t('rum.monitors.condition', '条件'),
        key: 'condition',
        width: 220,
        render: (_: unknown, m: RumMonitorItem) => (
          <div className="inline-flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 text-xs font-medium">
              {metricLabel(t, m.metric)}
            </span>
            <span className="font-mono tabular-nums">
              &gt; {formatThreshold(m.metric, m.criticalThreshold)}
            </span>
            <span className="text-xs text-[var(--color-text-3)]">
              ·{' '}
              {t('rum.monitors.forMinutes', '持续 {n} 分钟', {
                n: Math.max(1, Math.round(m.forDurationSec / 60)),
              })}
            </span>
          </div>
        ),
      },
      {
        title: t('rum.monitors.severityLabel', '严重级别'),
        key: 'severity',
        width: 96,
        render: (_: unknown, m: RumMonitorItem) => (
          <SemanticBadge
            label={t(`rum.monitors.severity.${m.severity || 'warning'}`, m.severity || 'warning')}
            {...toneSemanticPalette(severityTone[m.severity] ?? 'neutral')}
          />
        ),
      },
      {
        title: t('rum.monitors.enable', '启用'),
        key: 'enabled',
        width: 72,
        render: (_: unknown, m: RumMonitorItem) => (
          <div onClick={(e) => e.stopPropagation()}>
            <RumPermission
              resource="monitors"
              action="Operate"
              fallback={
                <Switch
                  size="small"
                  checked={m.enabled}
                  disabled
                  aria-label={m.enabled ? t('rum.monitors.disable', '禁用') : t('rum.monitors.enable', '启用')}
                />
              }
            >
              <Switch
                size="small"
                checked={m.enabled}
                loading={acting === m.id}
                onChange={() => void toggleEnabled(m)}
                aria-label={m.enabled ? t('rum.monitors.disable', '禁用') : t('rum.monitors.enable', '启用')}
              />
            </RumPermission>
          </div>
        ),
      },
      {
        title: t('rum.alertEvents.status', '状态'),
        key: 'status',
        width: 96,
        render: (_: unknown, m: RumMonitorItem) => {
          if (!m.enabled) {
            return (
              <SemanticBadge
                label={
                  <span className="inline-flex items-center gap-1">
                    <span className="size-1.5 rounded-full bg-[var(--color-text-4)]" />
                    {t('rum.common.disabled', '已禁用')}
                  </span>
                }
                {...toneSemanticPalette('neutral')}
              />
            );
          }
          if (m.firing) {
            return (
              <SemanticBadge
                label={
                  <span className="inline-flex items-center gap-1">
                    <span className="size-1.5 animate-pulse rounded-full bg-[var(--color-fail)]" />
                    {t('rum.monitors.statusFiring', '告警中')}
                  </span>
                }
                {...toneSemanticPalette('danger')}
              />
            );
          }
          return (
            <SemanticBadge
              label={
                <span className="inline-flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
                  {t('rum.monitors.statusOk', '正常')}
                </span>
              }
              {...toneSemanticPalette('success')}
            />
          );
        },
      },
      {
        title: t('rum.common.actions', '操作'),
        key: 'actions',
        width: 120,
        fixed: 'right',
        render: (_: unknown, m: RumMonitorItem) => (
          <div
            className="flex flex-nowrap items-center gap-3 whitespace-nowrap"
            onClick={(e) => e.stopPropagation()}
          >
            <RumPermission
              resource="monitors"
              action="Operate"
              className="inline-flex items-center gap-3"
            >
              <RumIconAction
                title={t('rum.common.edit', '编辑')}
                onClick={() => {
                  setEditing(m);
                  setDrawerOpen(true);
                }}
              />
              <Popconfirm
                title={t('rum.monitors.deleteConfirm', '确认删除该策略？')}
                onConfirm={() => void remove(m)}
                okText={t('rum.common.delete', '删除')}
                cancelText={t('rum.common.cancel', '取消')}
                okButtonProps={{ danger: true }}
              >
                <span className="inline-flex">
                  <RumIconAction
                    title={t('rum.monitors.delete', '删除')}
                    danger
                    disabled={acting === m.id}
                  />
                </span>
              </Popconfirm>
            </RumPermission>
          </div>
        ),
      },
    ],
    [t, acting],
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.monitors.title', '告警策略')}</h1>

      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            trailing={
              <>
                <Select
                  allowClear
                  placeholder={t('rum.filter.allApps', '全部应用')}
                  value={selectedApp || undefined}
                  onChange={(val) => setSelectedApp(val || '')}
                  className="min-w-40 w-44"
                  options={appOptions}
                />
                <Input
                  allowClear
                  prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                  placeholder={t('rum.monitors.searchPlaceholder', '搜索策略…')}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="!h-8 w-60 !items-center !py-0"
                />
                <RumPermission resource="monitors" action="Operate">
                  <Button
                    type="primary"
                    icon={<PlusOutlined aria-hidden="true" />}
                    onClick={() => {
                      setEditing(null);
                      setDrawerOpen(true);
                    }}
                  >
                    {t('common.new', '新建')}
                  </Button>
                </RumPermission>
              </>
            }
          />
        }
      >
        <MonitorFormDrawer
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          initial={editing}
          onSaved={() => void load()}
        />

        {!pending && filteredItems.length === 0 ? (
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <Empty
              description={
                <div className="flex flex-col gap-1">
                  <span>{t('rum.monitors.empty', '还没有告警策略')}</span>
                  <span className="text-xs text-[var(--color-text-3)]">
                    {t('rum.monitors.emptyHint', '创建一条策略，监控错误率或 Core Web Vitals。')}
                  </span>
                </div>
              }
            />
          </div>
        ) : pending && items.length === 0 ? (
          <RumTableSkeleton columns={rumSkeletonColumns(columns)} />
        ) : filteredItems.length > 0 ? (
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable<RumMonitorItem>
              rowKey="id"
              size="middle"
              tableLayout="fixed"
              autoScrollX={false}
              dataSource={table.rows}
              columns={columns}
              pagination={{
                current: table.pagination.current,
                pageSize: table.pagination.pageSize,
                total: table.pagination.total,
                showSizeChanger: table.pagination.showSizeChanger,
                onChange: table.pagination.onChange,
              }}
              rowClassName={(row) => (focusRule && row.id === focusRule ? 'bg-[var(--color-primary-bg)]' : '')}
              onRow={(record) => ({
                className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                onClick: () => {
                  setEditing(record);
                  setDrawerOpen(true);
                },
              })}
            />
          </div>
        ) : null}
      </RumSingleWorkbench>
    </div>
  );
}
