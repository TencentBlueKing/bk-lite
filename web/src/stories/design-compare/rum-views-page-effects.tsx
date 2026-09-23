'use client';

/**
 * RUM 视图与性能页布局选型示意 — Story only，不改生产。
 * 视觉契约对齐 OpsPilot：Look B 卡、Studio Workbench、语义 token。
 */

import type { ReactNode } from 'react';
import {
  DesktopOutlined,
  ExportOutlined,
  FilterOutlined,
  MobileOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { Button, Input, Segmented, Select, Tag } from 'antd';
import { afterPanel, afterSys } from './opspilot-after-system';

const ROUTES = [
  {
    route: '/home',
    badge: null as null | { label: string; tone: 'danger' | 'mute' },
    good: 62,
    ni: 28,
    poor: 10,
    views: 40,
    sessions: 28,
    lcp: '1800ms',
    lcpTone: 'ok' as const,
    inp: '90ms',
    inpTone: 'ok' as const,
    cls: '0.180',
    clsTone: 'warn' as const,
    mobile: 35,
    desktop: 65,
  },
  {
    route: '/cart',
    badge: { label: '体验偏差，需排查', tone: 'danger' as const },
    good: 18,
    ni: 22,
    poor: 60,
    views: 24,
    sessions: 18,
    lcp: '4200ms',
    lcpTone: 'bad' as const,
    inp: '280ms',
    inpTone: 'warn' as const,
    cls: '0.220',
    clsTone: 'warn' as const,
    mobile: 48,
    desktop: 52,
  },
  {
    route: '/checkout',
    badge: { label: '体验偏差，需排查', tone: 'danger' as const },
    good: 12,
    ni: 30,
    poor: 58,
    views: 18,
    sessions: 14,
    lcp: '3900ms',
    lcpTone: 'bad' as const,
    inp: '210ms',
    inpTone: 'warn' as const,
    cls: '0.090',
    clsTone: 'ok' as const,
    mobile: 40,
    desktop: 60,
  },
  {
    route: '/pay',
    badge: { label: '样本不足', tone: 'mute' as const },
    good: 40,
    ni: 40,
    poor: 20,
    views: 8,
    sessions: 6,
    lcp: '2100ms',
    lcpTone: 'warn' as const,
    inp: '120ms',
    inpTone: 'ok' as const,
    cls: '0.050',
    clsTone: 'ok' as const,
    mobile: 22,
    desktop: 78,
  },
  {
    route: '/account',
    badge: null,
    good: 70,
    ni: 22,
    poor: 8,
    views: 22,
    sessions: 16,
    lcp: '1600ms',
    lcpTone: 'ok' as const,
    inp: '80ms',
    inpTone: 'ok' as const,
    cls: '0.040',
    clsTone: 'ok' as const,
    mobile: 30,
    desktop: 70,
  },
] as const;

function toneClass(tone: 'ok' | 'warn' | 'bad') {
  if (tone === 'bad') return 'text-[var(--color-fail)]';
  if (tone === 'warn') return 'text-[var(--color-warning)]';
  return 'text-[var(--color-success)]';
}

function PageCanvas({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="min-h-[640px] p-4" style={{ background: afterSys.page }}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-[var(--color-text-1)]">{label}</div>
          <div className="mt-0.5 text-xs text-[var(--color-text-3)]">
            Story 示意 · 对齐 OpsPilot token / 面板 / 工具条 · 非生产页面
          </div>
        </div>
        <Tag className="m-0">{'视图与性能 · /rum/views'}</Tag>
      </div>
      {children}
    </div>
  );
}

function FakeTabs() {
  return (
    <div className="mb-3 flex gap-5 border-b border-[var(--color-fill-2)] text-[13px]">
      {['应用', '会话', '视图与性能', '转化漏斗'].map((tab) => (
        <span
          key={tab}
          className={`-mb-px border-b-2 pb-2 ${
            tab === '视图与性能'
              ? 'border-[var(--color-primary)] font-medium text-[var(--color-text-1)]'
              : 'border-transparent text-[var(--color-text-3)]'
          }`}
        >
          {tab}
        </span>
      ))}
    </div>
  );
}

function MetricTile({
  value,
  label,
  tone,
  flush,
}: {
  value: string;
  label: string;
  tone?: 'ok' | 'warn' | 'bad';
  flush?: boolean;
}) {
  return (
    <div
      className={
        flush
          ? 'min-w-0 px-1 py-0.5'
          : 'min-w-0 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3.5 py-2.5 shadow-2xs'
      }
    >
      <div
        className={`font-mono text-lg font-semibold tabular-nums ${
          tone ? toneClass(tone) : 'text-[var(--color-text-1)]'
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-xs text-[var(--color-text-3)]">{label}</div>
    </div>
  );
}

function DistBar({ good, ni, poor }: { good: number; ni: number; poor: number }) {
  return (
    <div className="flex min-w-[120px] items-center gap-2">
      <div className="flex h-2 flex-1 overflow-hidden rounded-sm bg-[var(--color-fill-2)]">
        <div className="h-full bg-[var(--color-success)]" style={{ width: `${good}%` }} />
        <div className="h-full bg-[var(--color-warning)]" style={{ width: `${ni}%` }} />
        <div className="h-full bg-[var(--color-fail)]" style={{ width: `${poor}%` }} />
      </div>
      <span className="w-8 shrink-0 text-right text-[11px] tabular-nums text-[var(--color-text-3)]">
        {good + ni + poor}%
      </span>
    </div>
  );
}

function Spark() {
  const pts = [40, 48, 42, 55, 50, 62, 58, 70];
  const max = Math.max(...pts);
  const min = Math.min(...pts);
  const d = pts
    .map((v, i) => {
      const x = (i / (pts.length - 1)) * 48;
      const y = 16 - ((v - min) / (max - min || 1)) * 14;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width="52" height="18" viewBox="0 0 52 18" aria-hidden>
      <path d={d} fill="none" stroke="var(--color-text-4)" strokeWidth="1.5" />
    </svg>
  );
}

function CrowdedToolbar() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <Segmented size="small" options={['按路由', '按版本']} value="按路由" />
      <div className="flex flex-wrap items-center gap-2">
        <Segmented size="small" options={['1h', '24h', '7d']} value="24h" />
        <Select size="small" className="w-36" value="all" options={[{ value: 'all', label: '全部应用' }]} />
        <Select size="small" className="w-28" value="visitor" options={[{ value: 'visitor', label: '访客' }]} />
        <Button size="small">已保存视图</Button>
        <Button size="small" icon={<ExportOutlined />}>
          导出
        </Button>
      </div>
    </div>
  );
}

function ClusteredToolbar({ leading }: { leading?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {leading ?? <Segmented size="small" options={['按路由', '按版本']} value="按路由" />}
        <Segmented size="small" options={['1h', '24h', '7d']} value="24h" />
        <Select size="small" className="w-36" value="all" options={[{ value: 'all', label: '全部应用' }]} />
        <Button size="small" icon={<FilterOutlined />}>
          筛选
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          size="small"
          className="w-52"
          prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
          placeholder="搜索路由"
        />
        <Button size="small">视图</Button>
        <Button size="small" icon={<ExportOutlined />}>
          导出
        </Button>
      </div>
    </div>
  );
}

function ViewsTable({ dense }: { dense?: boolean }) {
  const cell = dense ? 'px-2.5 py-2' : 'px-3 py-2.5';
  return (
    <div className="min-w-0 overflow-x-auto rounded-md border border-[var(--color-fill-2)]">
      <table className="w-full min-w-[920px] border-collapse text-left text-[13px]">
        <thead>
          <tr className="bg-[var(--color-fill-1)] text-[12px] text-[var(--color-text-3)]">
            {['路由', 'CWV 分布', '浏览', '会话', 'LCP P75', 'INP P75', 'CLS P75', '走势', '终端占比'].map(
              (h) => (
                <th key={h} className={`font-medium ${cell}`}>
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {ROUTES.map((r) => (
            <tr
              key={r.route}
              className="border-t border-[var(--color-fill-2)] hover:bg-[var(--color-fill-1)]"
            >
              <td className={cell}>
                <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                  <code className="font-medium text-[var(--color-text-1)]">{r.route}</code>
                  {r.badge ? (
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        r.badge.tone === 'danger'
                          ? 'bg-[color-mix(in_srgb,var(--color-fail)_12%,var(--color-bg))] text-[var(--color-fail)]'
                          : 'bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
                      }`}
                    >
                      {r.badge.label}
                    </span>
                  ) : null}
                </div>
              </td>
              <td className={cell}>
                <DistBar good={r.good} ni={r.ni} poor={r.poor} />
              </td>
              <td className={`tabular-nums ${cell}`}>{r.views}</td>
              <td className={`tabular-nums ${cell}`}>{r.sessions}</td>
              <td className={`font-mono text-sm tabular-nums ${cell} ${toneClass(r.lcpTone)}`}>
                {r.lcp}
              </td>
              <td className={`font-mono text-sm tabular-nums ${cell} ${toneClass(r.inpTone)}`}>
                {r.inp}
              </td>
              <td className={`font-mono text-sm tabular-nums ${cell} ${toneClass(r.clsTone)}`}>
                {r.cls}
              </td>
              <td className={cell}>
                <Spark />
              </td>
              <td className={`text-[12px] text-[var(--color-text-3)] ${cell}`}>
                <span className="inline-flex items-center gap-2">
                  <span className="inline-flex items-center gap-0.5">
                    <MobileOutlined />
                    {r.mobile}%
                  </span>
                  <span className="inline-flex items-center gap-0.5">
                    <DesktopOutlined />
                    {r.desktop}%
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A · 当前态：顶部 KPI 漂浮 + 下方工具条/表面板 */
export function RumViewsOptionACurrent() {
  return (
    <PageCanvas label="A · 当前态（对照）">
      <FakeTabs />
      <div className="flex flex-col gap-3.5">
        <div className="grid grid-cols-3 gap-3">
          <MetricTile value="1800ms" label="LCP P75" tone="ok" />
          <MetricTile value="90ms" label="INP P75" tone="ok" />
          <MetricTile value="0.180" label="CLS P75" tone="warn" />
        </div>
        <div className={`${afterPanel.card} flex flex-col gap-3.5 p-4`}>
          <CrowdedToolbar />
          <ViewsTable />
        </div>
      </div>
    </PageCanvas>
  );
}

/** B · 单面板工作台：CWV 摘要嵌在面板头下 */
export function RumViewsOptionBSingleWorkbench() {
  return (
    <PageCanvas label="B · 单面板工作台（推荐基线）">
      <FakeTabs />
      <div className={`${afterPanel.card} flex flex-col`}>
        <div className={`${afterPanel.head} justify-between gap-3`}>
          <span>视图与性能</span>
          <span className="text-[12px] font-normal text-[var(--color-text-3)]">
            近 24 小时 · 按路由
          </span>
        </div>

        <div className="grid grid-cols-3 gap-6 border-b border-[var(--color-fill-2)] px-3.5 py-3">
          <MetricTile value="1800ms" label="LCP P75" tone="ok" flush />
          <MetricTile value="90ms" label="INP P75" tone="ok" flush />
          <MetricTile value="0.180" label="CLS P75" tone="warn" flush />
        </div>

        <div className="flex flex-col gap-3 p-3.5">
          <ClusteredToolbar />
          <ViewsTable dense />
        </div>
      </div>
    </PageCanvas>
  );
}

/** C · 双栏工作台：左模式/筛选，右明细 */
export function RumViewsOptionCDualWorkbench() {
  return (
    <PageCanvas label="C · 双栏工作台（对齐 Studio 设置）">
      <FakeTabs />
      <div className={`${afterPanel.card} flex min-h-[560px]`}>
        <aside className="flex w-[200px] shrink-0 flex-col border-r border-[var(--color-fill-2)]">
          <div className={afterPanel.head}>视图维度</div>
          <div className="flex flex-col gap-4 p-3.5">
            <div>
              <div className="mb-1.5 text-[12px] font-medium text-[var(--color-text-2)]">聚合</div>
              <Segmented block size="small" options={['按路由', '按版本']} value="按路由" />
            </div>
            <div>
              <div className="mb-1.5 text-[12px] font-medium text-[var(--color-text-2)]">时间</div>
              <Segmented block size="small" options={['1h', '24h', '7d']} value="24h" />
            </div>
            <div>
              <div className="mb-1.5 text-[12px] font-medium text-[var(--color-text-2)]">应用</div>
              <Select
                className="w-full"
                size="small"
                value="all"
                options={[{ value: 'all', label: '全部应用' }]}
              />
            </div>
            <div>
              <div className="mb-1.5 text-[12px] font-medium text-[var(--color-text-2)]">流量</div>
              <Select
                className="w-full"
                size="small"
                value="visitor"
                options={[{ value: 'visitor', label: '访客' }]}
              />
            </div>
            <div className="border-t border-[var(--color-fill-2)] pt-3">
              <div className="mb-2 text-[12px] font-medium text-[var(--color-text-2)]">整体 CWV</div>
              <div className="space-y-2">
                <MetricTile value="1800ms" label="LCP P75" tone="ok" flush />
                <MetricTile value="90ms" label="INP P75" tone="ok" flush />
                <MetricTile value="0.180" label="CLS P75" tone="warn" flush />
              </div>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className={`${afterPanel.head} justify-between`}>
            <span>路由明细</span>
            <span className="text-[12px] font-normal text-[var(--color-text-3)]">5 条路由</span>
          </div>
          <div className="flex flex-col gap-3 p-3.5">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Input
                size="small"
                className="w-60"
                prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                placeholder="搜索路由"
              />
              <Button size="small">视图</Button>
              <Button size="small" icon={<ExportOutlined />}>
                导出
              </Button>
            </div>
            <ViewsTable dense />
          </div>
        </div>
      </div>
    </PageCanvas>
  );
}

/** D · Look B 路由卡网格 */
export function RumViewsOptionDCardGrid() {
  return (
    <PageCanvas label="D · Look B 路由卡网格">
      <FakeTabs />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="text-[14px] font-semibold text-[var(--color-text-1)]">
          视图与性能
          <span className="ml-2 text-[12px] font-normal text-[var(--color-text-3)]">
            LCP 1800ms · INP 90ms · CLS 0.180
          </span>
        </div>
        <ClusteredToolbar />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {ROUTES.map((r) => (
          <button
            key={r.route}
            type="button"
            className="flex min-h-[180px] flex-col rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-3 text-left shadow-2xs transition-colors hover:bg-[var(--color-fill-1)]"
          >
            <div className="flex items-start gap-2.5">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-[var(--color-fill-1)] font-mono text-[12px] text-[var(--color-text-2)]">
                /
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-[15px] font-semibold leading-snug text-[var(--color-text-1)]">
                  {r.route}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-3)]">
                  {r.badge ? (
                    <>
                      <span
                        className={`size-1.5 rounded-full ${
                          r.badge.tone === 'danger'
                            ? 'bg-[var(--color-fail)]'
                            : 'bg-[var(--color-text-4)]'
                        }`}
                      />
                      <span
                        className={
                          r.badge.tone === 'danger' ? 'text-[var(--color-fail)]' : undefined
                        }
                      >
                        {r.badge.label}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
                      <span>体验良好</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-2.5">
              <DistBar good={r.good} ni={r.ni} poor={r.poor} />
            </div>

            <div className="mt-2 grid grid-cols-3 gap-2 text-[12px]">
              <div>
                <div className={`font-mono font-semibold tabular-nums ${toneClass(r.lcpTone)}`}>
                  {r.lcp}
                </div>
                <div className="text-[11px] text-[var(--color-text-3)]">LCP</div>
              </div>
              <div>
                <div className={`font-mono font-semibold tabular-nums ${toneClass(r.inpTone)}`}>
                  {r.inp}
                </div>
                <div className="text-[11px] text-[var(--color-text-3)]">INP</div>
              </div>
              <div>
                <div className={`font-mono font-semibold tabular-nums ${toneClass(r.clsTone)}`}>
                  {r.cls}
                </div>
                <div className="text-[11px] text-[var(--color-text-3)]">CLS</div>
              </div>
            </div>

            <div className="mt-auto flex items-center justify-between border-t border-[var(--color-fill-2)] pt-2 text-[12px] text-[var(--color-text-3)]">
              <span>
                {r.views} 浏览 · {r.sessions} 会话
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="inline-flex items-center gap-0.5">
                  <MobileOutlined />
                  {r.mobile}%
                </span>
                <span className="inline-flex items-center gap-0.5">
                  <DesktopOutlined />
                  {r.desktop}%
                </span>
              </span>
            </div>
          </button>
        ))}
      </div>
    </PageCanvas>
  );
}

export const RUM_VIEWS_OPTIONS = [
  {
    id: 'A',
    name: 'A · 当前态（对照）',
    summary: '顶部三块 CWV KPI 漂浮，下方工具条+表。对照现状断层。',
    render: () => <RumViewsOptionACurrent />,
  },
  {
    id: 'B',
    name: 'B · 单面板工作台',
    summary: '一块工作台：栏头 + 内嵌 CWV 摘要 + 成组工具条 + 表。推荐基线。',
    render: () => <RumViewsOptionBSingleWorkbench />,
  },
  {
    id: 'C',
    name: 'C · 双栏工作台',
    summary: '左维度/筛选/整体 CWV，右路由明细。对齐 Studio 设置双栏。',
    render: () => <RumViewsOptionCDualWorkbench />,
  },
  {
    id: 'D',
    name: 'D · Look B 路由卡',
    summary: '路由做成实体卡网格，扫异常友好；多路由对比弱于表。',
    render: () => <RumViewsOptionDCardGrid />,
  },
] as const;
