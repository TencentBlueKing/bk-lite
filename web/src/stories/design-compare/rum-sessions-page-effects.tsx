'use client';

/**
 * RUM 会话页布局选型示意 — Story only，不改生产。
 * 视觉契约对齐 OpsPilot：Look B 卡解剖、Studio Workbench 单/双面板、语义 token。
 */

import type { ReactNode } from 'react';
import {
  DesktopOutlined,
  ExportOutlined,
  FilterOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { Button, Input, Segmented, Select, Switch, Tag } from 'antd';
import { afterPanel, afterSys } from './opspilot-after-system';

const SESSIONS = [
  {
    route: '/cart',
    id: '01KJQ…W0',
    user: '匿名',
    views: 1,
    duration: '15s',
    errors: 1,
    env: 'Chrome',
    started: '9月11日 16:31',
    replay: true,
  },
  {
    route: '/pay',
    id: '01KJQ…M0',
    user: '匿名',
    views: 1,
    duration: '15s',
    errors: 1,
    env: 'Chrome',
    started: '9月11日 16:31',
    replay: false,
  },
  {
    route: '/cart',
    id: '01KJQ…R0',
    user: '匿名',
    views: 1,
    duration: '15s',
    errors: 1,
    env: 'Chrome',
    started: '9月11日 16:31',
    replay: true,
  },
  {
    route: '/checkout',
    id: '01KJQ…A2',
    user: 'u_8842',
    views: 4,
    duration: '2m 10s',
    errors: 0,
    env: 'Chrome',
    started: '9月11日 16:28',
    replay: true,
  },
  {
    route: '/home',
    id: '01KJQ…B7',
    user: '匿名',
    views: 2,
    duration: '48s',
    errors: 0,
    env: 'Safari',
    started: '9月11日 16:20',
    replay: false,
  },
] as const;

function PageCanvas({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div
      className="min-h-[640px] p-4"
      style={{ background: afterSys.page }}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-[var(--color-text-1)]">{label}</div>
          <div className="mt-0.5 text-xs text-[var(--color-text-3)]">
            Story 示意 · 对齐 OpsPilot token / 面板 / 工具条规则 · 非生产页面
          </div>
        </div>
        <Tag className="m-0">{'会话 · /rum/sessions'}</Tag>
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
            tab === '会话'
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
  danger,
  flush,
}: {
  value: string;
  label: string;
  danger?: boolean;
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
          danger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-xs text-[var(--color-text-3)]">{label}</div>
    </div>
  );
}

function MiniBars() {
  const bars = [2, 1, 0, 3, 1, 0, 2, 4, 1, 8, 18, 12];
  const max = Math.max(...bars);
  return (
    <div className="flex h-14 items-end gap-1">
      {bars.map((v, i) => (
        <div
          key={i}
          className="w-2.5 rounded-sm bg-[color-mix(in_srgb,var(--color-primary)_55%,var(--color-fill-2))]"
          style={{ height: `${Math.max(8, (v / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function CrowdedToolbar() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented size="small" options={['1h', '24h', '7d']} value="1h" />
      <Select size="small" className="w-36" value="all" options={[{ value: 'all', label: '全部应用' }]} />
      <Select size="small" className="w-28" value="visitor" options={[{ value: 'visitor', label: '访客' }]} />
      <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
        仅看错误 <Switch size="small" />
      </div>
      <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
        仅看回放 <Switch size="small" />
      </div>
      <Select size="small" className="w-28" value="impact" options={[{ value: 'impact', label: '影响力' }]} />
      <Input
        size="small"
        className="w-52"
        prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
        placeholder="搜索会话 ID"
      />
      <Button size="small">已保存视图</Button>
      <Button size="small" icon={<ExportOutlined />}>
        导出
      </Button>
    </div>
  );
}

function ClusteredToolbar({ leading }: { leading?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {leading}
        <Segmented size="small" options={['1h', '24h', '7d']} value="1h" />
        <Select size="small" className="w-36" value="all" options={[{ value: 'all', label: '全部应用' }]} />
        <Button size="small" icon={<FilterOutlined />}>
          筛选 · 2
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select size="small" className="w-28" value="impact" options={[{ value: 'impact', label: '影响力' }]} />
        <Input
          size="small"
          className="w-60"
          prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
          placeholder="搜索会话 ID"
        />
        <Button size="small">视图</Button>
        <Button size="small" icon={<ExportOutlined />}>
          导出
        </Button>
      </div>
    </div>
  );
}

function SessionTable({ dense }: { dense?: boolean }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-md border border-[var(--color-fill-2)]">
      <table className="w-full border-collapse text-left text-[13px]">
        <thead>
          <tr className="bg-[var(--color-fill-1)] text-[12px] text-[var(--color-text-3)]">
            {['落地页', '用户', '浏览', '时长', '错误', '环境', '开始时间', '操作'].map((h) => (
              <th key={h} className={`font-medium ${dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SESSIONS.map((s) => (
            <tr
              key={s.id}
              className="border-t border-[var(--color-fill-2)] hover:bg-[var(--color-fill-1)]"
            >
              <td className={dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}>
                <div className="font-medium text-[var(--color-text-1)]">{s.route}</div>
                <div className="font-mono text-[11px] text-[var(--color-text-3)]">{s.id}</div>
              </td>
              <td className={`text-[var(--color-text-2)] ${dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}`}>
                {s.user}
              </td>
              <td className={`tabular-nums ${dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}`}>{s.views}</td>
              <td className={`tabular-nums ${dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}`}>{s.duration}</td>
              <td
                className={`tabular-nums ${dense ? 'px-2.5 py-2' : 'px-3 py-2.5'} ${
                  s.errors > 0 ? 'font-semibold text-[var(--color-fail)]' : ''
                }`}
              >
                {s.errors}
              </td>
              <td className={`text-[var(--color-text-3)] ${dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}`}>
                <span className="inline-flex items-center gap-1">
                  <DesktopOutlined />
                  {s.env}
                </span>
              </td>
              <td
                className={`text-[12px] tabular-nums text-[var(--color-text-3)] ${
                  dense ? 'px-2.5 py-2' : 'px-3 py-2.5'
                }`}
              >
                {s.started}
              </td>
              <td className={dense ? 'px-2.5 py-2' : 'px-3 py-2.5'}>
                {s.replay ? (
                  <button type="button" className="text-[var(--color-primary)]">
                    回放
                  </button>
                ) : (
                  <span className="text-[var(--color-text-4)]">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A · 当前态：KPI / 趋势 / 工具栏+表 三段漂浮 */
export function RumSessionsOptionACurrent() {
  return (
    <PageCanvas label="A · 当前态（对照）">
      <FakeTabs />
      <div className="flex flex-col gap-3.5">
        <div className="grid grid-cols-3 gap-3">
          <MetricTile value="67" label="总会话" />
          <MetricTile value="7" label="错误会话" danger />
          <MetricTile value="15s" label="中位时长" />
        </div>
        <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-3 shadow-2xs">
          <div className="mb-2 text-[13px] font-medium text-[var(--color-text-1)]">会话趋势</div>
          <MiniBars />
        </div>
        <div className={`${afterPanel.card} flex flex-col gap-3.5 p-4`}>
          <CrowdedToolbar />
          <SessionTable />
        </div>
      </div>
    </PageCanvas>
  );
}

/** B · 单面板工作台：摘要条嵌在面板内，工具条成组靠右 */
export function RumSessionsOptionBSingleWorkbench() {
  return (
    <PageCanvas label="B · 单面板工作台（推荐基线）">
      <FakeTabs />
      <div className={`${afterPanel.card} flex flex-col`}>
        <div className={`${afterPanel.head} justify-between gap-3`}>
          <span>会话</span>
          <span className="text-[12px] font-normal text-[var(--color-text-3)]">
            近 1 小时 · 67 条
          </span>
        </div>

        <div className="grid grid-cols-[1fr_220px] gap-4 border-b border-[var(--color-fill-2)] px-3.5 py-3">
          <div className="grid grid-cols-3 gap-4">
            <MetricTile value="67" label="总会话" flush />
            <MetricTile value="7" label="错误会话" danger flush />
            <MetricTile value="15s" label="中位时长" flush />
          </div>
          <div className="min-w-0">
            <div className="mb-1 text-[11px] text-[var(--color-text-3)]">会话趋势</div>
            <MiniBars />
          </div>
        </div>

        <div className="flex flex-col gap-3 p-3.5">
          <ClusteredToolbar />
          <SessionTable dense />
        </div>
      </div>
    </PageCanvas>
  );
}

/** C · 双栏工作台：左筛选轨 + 右内容面（对齐 Studio 设置） */
export function RumSessionsOptionCDualWorkbench() {
  return (
    <PageCanvas label="C · 双栏工作台（对齐 Studio 设置）">
      <FakeTabs />
      <div className={`${afterPanel.card} flex min-h-[560px]`}>
        <aside className="flex w-[200px] shrink-0 flex-col border-r border-[var(--color-fill-2)]">
          <div className={`${afterPanel.head}`}>快速筛选</div>
          <div className="flex flex-col gap-4 p-3.5">
            <div>
              <div className="mb-1.5 text-[12px] font-medium text-[var(--color-text-2)]">时间</div>
              <Segmented block size="small" options={['1h', '24h', '7d']} value="1h" />
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
            <div className="space-y-2 border-t border-[var(--color-fill-2)] pt-3">
              <div className="flex items-center justify-between text-[13px]">
                <span className="text-[var(--color-text-2)]">仅看错误</span>
                <Switch size="small" />
              </div>
              <div className="flex items-center justify-between text-[13px]">
                <span className="text-[var(--color-text-2)]">仅看回放</span>
                <Switch size="small" />
              </div>
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
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className={`${afterPanel.head} justify-between`}>
            <span>会话明细</span>
            <div className="flex items-center gap-3 text-[12px] font-normal">
              <span className="tabular-nums text-[var(--color-text-2)]">67 会话</span>
              <span className="tabular-nums text-[var(--color-fail)]">7 错误</span>
              <span className="tabular-nums text-[var(--color-text-3)]">中位 15s</span>
            </div>
          </div>
          <div className="border-b border-[var(--color-fill-2)] px-3.5 py-2.5">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] text-[var(--color-text-3)]">会话趋势</span>
            </div>
            <MiniBars />
          </div>
          <div className="flex flex-col gap-3 p-3.5">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Select
                size="small"
                className="w-28"
                value="impact"
                options={[{ value: 'impact', label: '影响力' }]}
              />
              <Input
                size="small"
                className="w-60"
                prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                placeholder="搜索会话 ID"
              />
              <Button size="small">视图</Button>
              <Button size="small" icon={<ExportOutlined />}>
                导出
              </Button>
            </div>
            <SessionTable dense />
          </div>
        </div>
      </div>
    </PageCanvas>
  );
}

/** D · Look B 会话卡网格：实体卡解剖，适合扫一眼找异常 */
export function RumSessionsOptionDCardGrid() {
  return (
    <PageCanvas label="D · Look B 会话卡网格">
      <FakeTabs />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="text-[14px] font-semibold text-[var(--color-text-1)]">
          会话
          <span className="ml-2 text-[12px] font-normal text-[var(--color-text-3)]">
            67 条 · 7 错误 · 中位 15s
          </span>
        </div>
        <ClusteredToolbar />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {SESSIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="flex min-h-[168px] flex-col rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-3 text-left shadow-2xs transition-colors hover:bg-[var(--color-fill-1)]"
          >
            <div className="flex items-start gap-2.5">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-[var(--color-fill-1)] text-[var(--color-text-2)]">
                <DesktopOutlined />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px] font-semibold leading-snug text-[var(--color-text-1)]">
                  {s.route}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-3)]">
                  {s.errors > 0 ? (
                    <>
                      <span className="size-1.5 rounded-full bg-[var(--color-fail)]" />
                      <span className="text-[var(--color-fail)]">有错误</span>
                    </>
                  ) : (
                    <>
                      <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
                      <span>正常</span>
                    </>
                  )}
                  <span>·</span>
                  <span>{s.started}</span>
                </div>
              </div>
            </div>
            <div className="mt-2 line-clamp-2 text-[12px] leading-5 text-[var(--color-text-3)]">
              {s.user} · {s.env} · {s.views} 浏览 · 时长 {s.duration}
            </div>
            <div className="mt-auto flex min-h-5 flex-wrap gap-1.5 pt-2">
              <span className="rounded bg-[var(--color-fill-1)] px-1.5 py-0.5 text-[11px] text-[var(--color-text-3)]">
                {s.id}
              </span>
              {s.replay ? (
                <span className="rounded bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 py-0.5 text-[11px] text-[var(--color-primary)]">
                  可回放
                </span>
              ) : null}
              {s.errors > 0 ? (
                <span className="rounded bg-[color-mix(in_srgb,var(--color-fail)_12%,var(--color-bg))] px-1.5 py-0.5 text-[11px] text-[var(--color-fail)]">
                  {s.errors} 错误
                </span>
              ) : null}
            </div>
            <div className="mt-2.5 flex items-center justify-between border-t border-[var(--color-fill-2)] pt-2 text-[12px]">
              <span className="text-[var(--color-text-3)]">会话</span>
              {s.replay ? (
                <span className="text-[var(--color-primary)]">回放</span>
              ) : (
                <span className="text-[var(--color-text-4)]">—</span>
              )}
            </div>
          </button>
        ))}
      </div>
    </PageCanvas>
  );
}

export const RUM_SESSIONS_OPTIONS = [
  {
    id: 'A',
    name: 'A · 当前态（对照）',
    summary: 'KPI / 趋势 / 表三段漂浮，工具条拥挤。用来对照问题。',
    render: () => <RumSessionsOptionACurrent />,
  },
  {
    id: 'B',
    name: 'B · 单面板工作台',
    summary: '一块工作台：栏头 + 内嵌摘要条 + 成组工具条 + 表。最接近 OpsPilot 设置内容面。',
    render: () => <RumSessionsOptionBSingleWorkbench />,
  },
  {
    id: 'C',
    name: 'C · 双栏工作台',
    summary: '左筛选轨 + 右明细，对齐 Studio 设置双栏。筛选项多时更干净。',
    render: () => <RumSessionsOptionCDualWorkbench />,
  },
  {
    id: 'D',
    name: 'D · Look B 会话卡',
    summary: '会话做成实体卡网格。扫异常友好，但明细对比弱于表格。',
    render: () => <RumSessionsOptionDCardGrid />,
  },
] as const;
