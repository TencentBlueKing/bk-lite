'use client';

import type { ReactNode } from 'react';
import { Skeleton, Table } from 'antd';

import { useTranslation } from '@/utils/i18n';

/** Layout-isomorphic RUM loading chrome. See web/DESIGN.md → Loading / Skeleton. */

export function RumBone({ className = '' }: { className?: string }) {
  return <Skeleton.Input active size="small" className={`!min-w-0 ${className}`} />;
}

export interface RumSkeletonColumn {
  title?: ReactNode;
  width?: string | number;
  fixed?: 'left' | 'right';
}

export function rumSkeletonColumns(
  columns: ReadonlyArray<{
    title?: unknown;
    width?: string | number;
    fixed?: 'left' | 'right' | boolean;
  }>,
): RumSkeletonColumn[] {
  return columns.map((col) => ({
    title: typeof col.title === 'function' ? undefined : (col.title as ReactNode),
    width: col.width,
    fixed: col.fixed === 'left' || col.fixed === 'right' ? col.fixed : undefined,
  }));
}

export function RumKpiSkeleton({
  count = 6,
  className,
  cellClassName,
}: {
  count?: number;
  className?: string;
  cellClassName?: string;
  /** @deprecated 指标卡统一少框，不再使用 bordered */
  bordered?: boolean;
}) {
  const grid =
    count <= 3
      ? 'grid-cols-3'
      : count === 4
        ? 'grid-cols-2 sm:grid-cols-4'
        : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6';
  return (
    <div
      className={['grid min-w-0 gap-3', grid, className].filter(Boolean).join(' ')}
      aria-busy="true"
      aria-label="loading"
    >
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className={[
            'min-w-0 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] px-3.5 py-2.5',
            cellClassName,
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <RumBone className="!h-6 !w-16" />
          <div className="mt-1.5">
            <RumBone className="!h-3 !w-12" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RumTableSkeleton({
  columns,
  rows = 8,
  size = 'middle',
}: {
  columns: RumSkeletonColumn[];
  rows?: number;
  size?: 'small' | 'middle';
}) {
  const data = Array.from({ length: rows }, (_, index) => ({ key: `rum-sk-${index}` }));
  return (
    <div className="min-w-0 overflow-hidden" aria-busy="true" aria-label="loading">
      <Table
        rowKey="key"
        size={size}
        pagination={false}
        tableLayout="fixed"
        dataSource={data}
        columns={columns.map((col, index) => ({
          title: col.title,
          key: `rum-sk-col-${index}`,
          width: col.width,
          fixed: col.fixed,
          render: (_: unknown, __: { key: string }, rowIndex: number) => (
            <RumBone
              className={`!h-3.5 ${rowIndex % 3 === 0 ? '!w-4/5' : rowIndex % 3 === 1 ? '!w-3/5' : '!w-2/3'}`}
            />
          ),
        }))}
      />
    </div>
  );
}

const TREND_HEIGHTS = [42, 68, 51, 84, 60, 76, 48];

export function RumTrendSkeleton() {
  return (
    <section className="min-w-0 overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)]" aria-busy="true" aria-label="loading">
      <div className="flex min-h-8 items-center justify-between border-b border-[var(--color-border-2)] px-3.5 py-2.5">
        <RumBone className="!h-4 !w-20" />
        <RumBone className="!h-3 !w-28" />
      </div>
      <div className="flex h-32 items-end gap-1.5 p-3.5">
        {TREND_HEIGHTS.map((height, index) => (
          <div
            key={index}
            className="min-w-0 flex-1 rounded-t bg-[var(--color-fill-2)]"
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
    </section>
  );
}

function DistRows() {
  return (
    <div className="space-y-2.5">
      {[72, 54, 38, 22].map((width, index) => (
        <div key={index} className="space-y-1">
          <div className="flex items-center justify-between gap-2">
            <RumBone className="!h-3.5 !w-16" />
            <RumBone className="!h-3 !w-10" />
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-[var(--color-fill-2)]">
            <div className="h-full rounded-full bg-[var(--color-fill-3)]" style={{ width: `${width}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RumDistributionGridSkeleton() {
  return (
    <div className="grid min-w-0 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="loading">
      {Array.from({ length: 4 }).map((_, index) => (
        <section key={index} className="min-w-0 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
          <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
            <div className="flex items-center gap-2">
              <RumBone className="!h-4 !w-4 !rounded" />
              <RumBone className="!h-4 !w-20" />
              <RumBone className="!h-5 !w-7 !rounded-full" />
            </div>
          </div>
          <div className="p-3.5">
            <DistRows />
          </div>
        </section>
      ))}
    </div>
  );
}

export function RumOverviewSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy="true" aria-label="loading">
      <RumKpiSkeleton />
      <RumTrendSkeleton />
      <RumDistributionGridSkeleton />
      <section className="min-w-0 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
        <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <RumBone className="!h-4 !w-4 !rounded" />
            <RumBone className="!h-4 !w-20" />
            <RumBone className="!h-5 !w-7 !rounded-full" />
          </div>
          <RumBone className="!h-3.5 !w-14" />
        </div>
        <RumTableSkeleton
          size="middle"
          rows={6}
          columns={[
            { title: t('rum.sessions.session', '会话'), width: '22%' },
            { title: t('rum.sessions.started', '开始时间'), width: '18%' },
            { title: t('rum.overview.countryViews', '浏览'), width: '12%' },
            { title: t('rum.sessions.errored', '出错'), width: '12%' },
            { title: t('rum.overview.country', '国家/地区'), width: '14%' },
            { title: t('rum.sessions.landing', '落地页') },
          ]}
        />
      </section>
    </div>
  );
}

export function RumSetupSkeleton() {
  const { t } = useTranslation();
  const steps = [
    t('rum.detail.stepApp', '应用与 Origin'),
    t('rum.detail.stepKey', '浏览器密钥'),
    t('rum.detail.stepInstall', '安装与初始化'),
    t('rum.detail.stepVerify', '验证接入'),
  ];
  return (
    <ol className="w-full list-none space-y-0 p-0" aria-busy="true" aria-label="loading">
      {steps.map((title, index) => (
        <li key={title} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3.5">
          <div className="flex flex-col items-center">
            <span className="inline-flex size-[26px] shrink-0 rounded-full bg-[var(--color-fill-2)]" />
            {index < steps.length - 1 ? (
              <span className="my-1.5 w-px min-h-[18px] flex-1 bg-[var(--color-border-2)]" aria-hidden />
            ) : null}
          </div>
          <section className={index < steps.length - 1 ? 'min-w-0 pb-6' : 'min-w-0'}>
            <h2 className="text-sm font-medium text-[var(--color-text-3)]">{title}</h2>
            <div className="mt-3 space-y-2">
              <RumBone className="!h-3.5 !w-full" />
              <RumBone className="!h-3.5 !w-4/5" />
              {index === 2 ? <RumCodeSkeleton /> : null}
            </div>
          </section>
        </li>
      ))}
    </ol>
  );
}

export function RumCodeSkeleton() {
  return (
    <div
      className="space-y-2 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)] p-3"
      aria-busy="true"
      aria-label="loading"
    >
      <RumBone className="!h-3 !w-full" />
      <RumBone className="!h-3 !w-5/6" />
      <RumBone className="!h-3 !w-2/3" />
      <RumBone className="!h-3 !w-3/4" />
    </div>
  );
}

export function RumSessionDetailSkeleton() {
  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy="true" aria-label="loading">
      <RumKpiSkeleton count={4} />
      <section>
        <div className="mb-2">
          <RumBone className="!h-4 !w-20" />
        </div>
        <div className="overflow-hidden rounded-lg border border-[var(--color-border-2)] divide-y divide-[var(--color-border-2)]">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="flex items-center gap-3 px-3.5 py-2.5">
              <RumBone className="!h-3 !w-6" />
              <RumBone className="!h-3.5 !w-28" />
            </div>
          ))}
        </div>
      </section>
      <section>
        <div className="mb-3 flex items-center justify-between gap-2">
          <RumBone className="!h-4 !w-24" />
          <RumBone className="!h-7 !w-48 !rounded-md" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="flex gap-3">
              <span className="mt-1 size-2 shrink-0 rounded-full bg-[var(--color-fill-3)]" />
              <div className="min-w-0 flex-1 space-y-1">
                <RumBone className="!h-3 !w-28" />
                <RumBone className="!h-3.5 !w-3/5" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function RumErrorDetailSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy="true" aria-label="loading">
      <RumKpiSkeleton count={4} />

      <div className="flex min-w-0 flex-col items-start gap-4 lg:flex-row">
        {/* 左侧主要区域 */}
        <div className="flex min-w-0 flex-1 flex-col gap-4 w-full">
          {/* 堆栈卡片骨架 */}
          <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
            <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <RumBone className="!h-4 !w-24" />
              </div>
              <RumBone className="!h-4 !w-16" />
            </div>
            <div className="divide-y divide-[var(--color-border-1)]">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="flex items-center gap-3 px-3.5 py-2.5">
                  <RumBone className="!h-3 !w-6" />
                  <RumBone className="!h-3.5 !w-3/4" />
                </div>
              ))}
            </div>
          </section>

          {/* 出现记录卡片骨架 */}
          <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
            <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <RumBone className="!h-4 !w-28" />
              </div>
              <RumBone className="!h-3.5 !w-20" />
            </div>
            <RumTableSkeleton
              rows={4}
              columns={[
                { title: t('rum.sessions.session', '会话') },
                { title: t('rum.sessions.user', '用户') },
                { title: t('rum.errors.lastSeen', '最近出现') },
                { title: t('rum.common.actions', '操作'), width: 72, fixed: 'right' },
              ]}
            />
          </section>
        </div>

        {/* 右侧辅助与诊断面板 */}
        <div className="flex w-full shrink-0 flex-col gap-4 lg:w-[320px] xl:w-[340px]">
          {/* 出现趋势卡片骨架 */}
          <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
            <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <RumBone className="!h-4 !w-20" />
              </div>
              <RumBone className="!h-3 !w-14" />
            </div>
            <div className="p-3.5 space-y-2">
              <div className="h-[88px] overflow-hidden rounded bg-[var(--color-fill-2)]" />
              <RumBone className="!h-3 !w-3/4" />
            </div>
          </section>

          {/* 错误属性卡片骨架 */}
          <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
            <div className="flex items-center gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
              <RumBone className="!h-4 !w-20" />
            </div>
            <div className="space-y-2 p-3 text-xs">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2">
                  <RumBone className="!h-3.5 !w-16" />
                  <RumBone className="!h-3.5 !w-24" />
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export function RumReplayPlayerSkeleton() {
  return (
    <div
      className="flex min-h-96 flex-col justify-end rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)] p-4"
      aria-busy="true"
      aria-label="loading"
    >
      <div className="flex items-center gap-3">
        <span className="size-8 rounded-full bg-[var(--color-fill-3)]" />
        <div className="h-1.5 flex-1 rounded-full bg-[var(--color-fill-3)]" />
        <RumBone className="!h-3 !w-10" />
      </div>
    </div>
  );
}

export function RumReplayPageSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]" aria-busy="true" aria-label="loading">
      <RumReplayPlayerSkeleton />
      <aside className="space-y-3">
        <RumBone className="!h-4 !w-20" />
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="space-y-1.5 rounded-md border border-[var(--color-border-2)] p-2">
            <RumBone className="!h-3.5 !w-24" />
            <RumBone className="!h-3 !w-32" />
          </div>
        ))}
      </aside>
    </div>
  );
}

export function RumFunnelsSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden" aria-busy="true" aria-label="loading">
      <aside className="hidden h-full w-[260px] shrink-0 flex-col overflow-y-auto rounded-l-lg bg-[var(--color-fill-1)] px-3 py-3 lg:flex">
        <div className="mb-2 flex items-center justify-between px-2 pt-1 pb-1">
          <RumBone className="!h-3.5 !w-20" />
          <RumBone className="!h-4 !w-6 !rounded-full" />
        </div>
        <div className="flex flex-col gap-1">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="rounded-md px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <RumBone className="!h-3.5 !w-24" />
                <RumBone className="!h-3 !w-6" />
              </div>
              <div className="mt-1.5">
                <RumBone className="!h-2.5 !w-16" />
              </div>
            </div>
          ))}
        </div>
      </aside>
      <section className="flex h-full min-w-0 flex-1 flex-col overflow-y-auto rounded-r-lg bg-[var(--color-bg)] px-5 py-4">
        <div className="flex items-center justify-between gap-3 pb-4">
          <div className="space-y-2">
            <RumBone className="!h-5 !w-36" />
            <RumBone className="!h-4 !w-52" />
          </div>
          <div className="flex gap-2">
            <RumBone className="!h-8 !w-16 !rounded-md" />
            <RumBone className="!h-8 !w-16 !rounded-md" />
            <RumBone className="!h-8 !w-16 !rounded-md" />
          </div>
        </div>
        <RumFunnelsReachSkeleton
          columns={[
            { title: t('rum.funnels.step', '步骤'), width: '10%' },
            { title: t('rum.views.route', '路由'), width: '24%' },
            { title: t('rum.funnels.retention', '流转留存'), width: '32%' },
            { title: t('rum.funnels.convFromPrev', '相对上步转化'), width: '12%' },
            { title: t('rum.funnels.convFromStart', '相对首步转化'), width: '12%' },
            { title: t('rum.funnels.stepDropoff', '本步流失'), width: '10%' },
          ]}
        />
      </section>
    </div>
  );
}

export function RumFunnelsReachSkeleton({ columns }: { columns: RumSkeletonColumn[] }) {
  return (
    <div className="flex min-w-0 flex-col gap-5" aria-busy="true" aria-label="loading">
      <RumKpiSkeleton count={3} />
      <div className="flex flex-col gap-3 pt-1">
        <div className="flex items-center gap-2">
          <span className="h-3.5 w-1 rounded-sm bg-[var(--color-primary)]" aria-hidden />
          <RumBone className="!h-4 !w-24" />
        </div>
        <RumTableSkeleton columns={columns} rows={4} />
      </div>
    </div>
  );
}

export function RumAlertDetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="loading">
      <div className="flex gap-2 border-b border-[var(--color-border-2)] pb-3">
        <RumBone className="!h-5 !w-14 !rounded-md" />
        <RumBone className="!h-5 !w-14 !rounded-md" />
        <RumBone className="ml-auto !h-4 !w-20" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={index}
            className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)]/40 px-3 py-2"
          >
            <RumBone className="!h-3 !w-12" />
            <div className="mt-1.5">
              <RumBone className="!h-4 !w-20" />
            </div>
          </div>
        ))}
      </div>
      <div className="h-24 rounded-md bg-[var(--color-fill-2)]" />
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="flex gap-3">
            <span className="mt-1 size-2 shrink-0 rounded-full bg-[var(--color-fill-3)]" />
            <div className="min-w-0 flex-1 space-y-1">
              <RumBone className="!h-3.5 !w-28" />
              <RumBone className="!h-3 !w-40" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
