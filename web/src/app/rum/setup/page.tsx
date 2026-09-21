'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Empty, Input, Segmented, type TableColumnsType } from 'antd';

import { useRumQueries, type RumApplicationView } from '@/app/rum/api';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import { RumSingleWorkbench } from '@/app/rum/components/rum-dual-workbench';
import RumRefreshButton from '@/app/rum/components/rum-refresh-button';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import { RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import {
  compareRumIngestStatus,
  matchesRumIngestFilter,
  rumIngestStatus,
  rumIngestStatusTone,
  rumSetupPath,
  type RumIngestFilter,
  type RumIngestStatus,
} from '@/app/rum/lib/ingest';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import SemanticBadge from '@/components/semantic-badge';
import { toneSemanticPalette } from '@/app/rum/lib/cwv';
import CustomTable from '@/components/custom-table';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';

function relativeAccepted(seconds: number | undefined, nowMs: number, locale: string): string {
  if (!seconds) return '—';
  const diffSec = Math.round((seconds * 1000 - nowMs) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(diffSec, 'second');
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), 'hour');
  return rtf.format(Math.round(diffSec / 86400), 'day');
}

export default function RumSetupIndexPage() {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const router = useRouter();
  const { listApplications, authReady } = useRumQueries();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<RumIngestFilter>('all');
  const [apps, setApps] = useState<RumApplicationView[]>([]);
  const [pending, setPending] = useState(true);
  const [controlUnavailable, setControlUnavailable] = useState(false);
  const renderNow = Date.now();

  const load = useCallback(async () => {
    setPending(true);
    try {
      setApps(await listApplications());
      setControlUnavailable(false);
    } catch {
      setApps([]);
      setControlUnavailable(true);
    } finally {
      setPending(false);
    }
  }, [listApplications]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listApplications()
        .then((items) => {
          if (isCancelled()) return;
          setApps(items);
          setControlUnavailable(false);
        })
        .catch(() => {
          if (isCancelled()) return;
          setApps([]);
          setControlUnavailable(true);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [listApplications],
  );

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return apps
      .filter((app) => {
        const status = rumIngestStatus(app);
        if (!matchesRumIngestFilter(status, filter)) return false;
        if (!needle) return true;
        return app.application.toLowerCase().includes(needle);
      })
      .sort((a, b) => {
        const byStatus = compareRumIngestStatus(rumIngestStatus(a), rumIngestStatus(b));
        if (byStatus !== 0) return byStatus;
        return a.application.localeCompare(b.application);
      });
  }, [apps, filter, search]);

  const table = useRumClientPager(visible, `${filter}|${search}`);

  function statusLabel(status: RumIngestStatus): string {
    if (status === 'connected') return t('rum.setup.statusConnected', '已接入');
    if (status === 'waiting') return t('rum.setup.statusWaiting', '未接入');
    return t('rum.setup.statusDisabled', '已禁用');
  }

  const columns: TableColumnsType<RumApplicationView> = [
    {
      title: t('rum.applications.application', '应用'),
      dataIndex: 'application',
      key: 'application',
      width: 220,
      render: (name: string) => <span>{name}</span>,
    },
    {
      title: t('rum.setup.status', '接入状态'),
      key: 'status',
      width: 112,
      render: (_, app) => {
        const status = rumIngestStatus(app);
        return <SemanticBadge label={statusLabel(status)} {...toneSemanticPalette(rumIngestStatusTone(status))} />;
      },
    },
    {
      title: t('rum.detail.originsTitle', '允许的 Origin'),
      key: 'origins',
      width: 120,
      render: (_, app) =>
        t('rum.applications.originsCount', '{count} 个', { count: app.origins?.length || 0 }),
    },
    {
      title: t('rum.setup.lastAccepted', '最近接收'),
      key: 'lastAccepted',
      width: 140,
      render: (_, app) => (
        <span className="tabular-nums">
          {relativeAccepted(app.lastAcceptedAt, renderNow, locale)}
        </span>
      ),
    },
    {
      title: t('rum.common.actions', '操作'),
      key: 'actions',
      width: 80,
      fixed: 'right',
      onHeaderCell: () => ({ className: '!pr-6' }),
      onCell: () => ({ className: '!pr-6' }),
      render: (_, app) => (
        <div className="whitespace-nowrap" onClick={(event) => event.stopPropagation()}>
          <RumIconAction
            title={t('rum.setup.configure', '配置')}
            onClick={() => router.push(rumSetupPath(app.application))}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.setup.title', '接入')}</h1>

      {controlUnavailable ? <PipelineDegradedBanner reason="control" /> : null}

      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            leading={
              <Segmented
                value={filter}
                onChange={(key) => setFilter(key as RumIngestFilter)}
                options={[
                  { value: 'all', label: t('rum.setup.filterAll', '全部') },
                  { value: 'waiting', label: t('rum.setup.filterWaiting', '未接入') },
                  { value: 'connected', label: t('rum.setup.filterConnected', '已接入') },
                ]}
              />
            }
            trailing={
              <>
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t('rum.setup.searchPlaceholder', '搜索应用…')}
                  prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                  allowClear
                  className="!h-8 w-60 !items-center !py-0"
                />
                <RumRefreshButton loading={pending} onClick={() => void load()} />
              </>
            }
          />
        }
      >
        {pending && apps.length === 0 ? (
          <RumTableSkeleton columns={rumSkeletonColumns(columns)} />
        ) : !pending && apps.length === 0 ? (
          <Empty
            image={
              <span className="inline-flex size-11 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-text-3)]">
                <ApiOutlined />
              </span>
            }
            description={
              <div className="mx-auto max-w-md">
                <p className="m-0 text-sm font-semibold">
                  {controlUnavailable
                    ? t('rum.applications.controlUnavailableTitle', '控制面不可达')
                    : t('rum.setup.empty', '还没有需要接入的应用')}
                </p>
                <p className="mt-1 text-xs text-[var(--color-text-3)]">
                  {controlUnavailable
                    ? t(
                      'rum.applications.controlUnavailableHint',
                      '无法读取应用列表与接入配置，请检查 RUM controller 连接。',
                    )
                    : t('rum.setup.emptyHint', '先在应用里创建一个，再回到这里配置 Origin 与 SDK。')}
                </p>
                {!controlUnavailable ? (
                  <div className="mt-4 flex justify-center">
                    <Button onClick={() => router.push('/rum/applications')}>
                      {t('rum.setup.goApplications', '去应用')}
                    </Button>
                  </div>
                ) : null}
              </div>
            }
          />
        ) : visible.length === 0 ? (
          <Empty description={t('rum.setup.filterEmpty', '没有符合筛选的应用')} />
        ) : (
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable<RumApplicationView>
              rowKey="application"
              dataSource={table.rows}
              pagination={{
                current: table.pagination.current,
                pageSize: table.pagination.pageSize,
                total: table.pagination.total,
                showSizeChanger: table.pagination.showSizeChanger,
                onChange: table.pagination.onChange,
              }}
              tableLayout="fixed"
              size="middle"
              autoScrollX={false}
              columns={columns}
              onRow={(app) => ({
                onClick: () => router.push(rumSetupPath(app.application)),
                className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
              })}
            />
          </div>
        )}
      </RumSingleWorkbench>
    </div>
  );
}
