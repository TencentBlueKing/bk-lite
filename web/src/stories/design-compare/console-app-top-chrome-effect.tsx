'use client';

/**
 * 应用顶栏壳层 + OpsPilot 卡片对照效果图 — Storybook 示意，非改生产。
 */

import type { ReactNode } from 'react';
import Icon from '@/components/icon';
import { UnifiedOpsCard } from './opspilot-after-system';

const APP_ICONS: Record<string, string> = {
  OpsPilot: 'jiqiren2',
  OpsConsole: 'caidandaohang',
  Setting: 'system-manager',
  CMDB: 'cmdb',
  Monitor: 'monitor',
  Log: 'wendang',
  Node: 'node',
  Alarm: 'alarm',
  OpsAnalysis: 'ops-analysis',
};

const APPS_NOW = [
  'OpsPilot',
  'OpsConsole',
  'Setting',
  'CMDB',
  'Monitor',
  'Log',
  'Node',
  'Alarm',
  'OpsAnalysis',
] as const;

const APPS_PROPOSED = [
  { name: 'OpsPilot', active: true },
  { name: 'OpsConsole', active: false },
  { name: 'Setting', active: false },
  { name: 'CMDB', active: false },
  { name: 'Monitor', active: false },
  { name: 'Log', active: false },
  { name: 'Node', active: false },
  { name: 'Alarm', active: false },
  { name: 'OpsAnalysis', active: false },
  { name: 'ITSM', active: false },
  { name: 'MLOps', active: false },
  { name: 'Lab', active: false },
] as const;

const SIDE_MENUS = [
  { label: '工作台', icon: 'jiqiren2', active: true },
  { label: '智能体', icon: 'weibiaoti3', active: false },
  { label: '知识库', icon: 'zhishiku1', active: false },
  { label: '工具', icon: 'gongju-', active: false },
  { label: '记忆', icon: 'shujuguanli', active: false },
  { label: '模型', icon: 'moxing2', active: false },
] as const;

const GRADIENT_CARDS = [
  { title: '新增', add: true },
  { title: 'tdddd', desc: 'tdddd', online: true },
  { title: 'k8s配置能力检测', desc: 'k8s配置能力检测', online: true },
  { title: 'uu', desc: 'uu', online: false },
  { title: 'Web 应用巡检助手', desc: 'Web 应用巡检助手', online: true },
  { title: 'Postgres DB 助手', desc: 'Postgres DB 助手', online: true },
  { title: 'Kubernetes 助手', desc: 'Kubernetes 助手', online: false },
] as const;

const B_CARDS = [
  {
    name: 'Incident Copilot',
    description: '协调告警处置、审批跟进与变更回滚，缩短事故响应链路。',
    icon: 'jiqiren2',
    status: 'online' as const,
    updatedAt: '12m 前',
    meta: ['Chatflow', 'gpt-4o'],
    pinned: true,
    owner: 'admin',
    team: 'SRE',
  },
  {
    name: 'Knowledge Desk',
    description: '面向运维手册与 Wiki 的问答助手，减少重复翻文档。',
    icon: 'zhishiku1',
    status: 'offline' as const,
    updatedAt: '昨天',
    meta: ['Chatflow', 'RAG'],
    pinned: false,
    owner: 'admin',
    team: 'Knowledge',
  },
  {
    name: 'Runbook Flow',
    description: 'Chatflow 编排发布检查、通知与人工审批节点。',
    icon: 'jiqiren2',
    status: 'online' as const,
    updatedAt: '3h 前',
    meta: ['Chatflow', '审批流'],
    pinned: false,
    owner: 'admin',
    team: ['Ops', 'SRE', 'Platform', 'QA'],
  },
  {
    name: 'Patch Advisor',
    description: '补丁风险评估与分批发布建议，降低变更事故面。',
    icon: 'gongju-',
    status: 'online' as const,
    updatedAt: '1h 前',
    meta: ['Chatflow', '风险评估'],
    pinned: true,
    owner: 'admin',
    team: ['SRE', 'Sec'],
  },
] as const;

function Watermark() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-[-120px] rotate-[-22deg] text-[13px] leading-[64px] tracking-wide text-[var(--color-text-4)] opacity-[0.35]"
    >
      {Array.from({ length: 22 }).map((_, i) => (
        <div key={i}>
          WeOpsX - admin - 2024-09-01　　WeOpsX - admin - 2024-09-01　　WeOpsX - admin - 2024-09-01
        </div>
      ))}
    </div>
  );
}

function AppChip({
  name,
  active,
  flat,
}: {
  name: string;
  active?: boolean;
  flat?: boolean;
}) {
  const icon = APP_ICONS[name] || 'cmdb';
  return (
    <div
      className={`relative flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[8px] px-2.5 text-[13px] ${
        flat
          ? 'font-medium text-[var(--color-text-2)]'
          : active
            ? 'bg-[var(--color-fill-2)] font-semibold text-[var(--color-primary)]'
            : 'font-medium text-[var(--color-text-3)] hover:bg-[var(--color-fill-1)]'
      }`}
    >
      <Icon
        type={icon}
        className={`h-3.5 w-3.5 shrink-0 ${
          flat
            ? 'text-[var(--color-primary)]'
            : active
              ? 'text-[var(--color-primary)]'
              : 'text-[var(--color-text-4)]'
        }`}
      />
      {name}
      {!flat && active ? (
        <span className="absolute inset-x-2.5 bottom-0 h-0.5 rounded-full bg-[var(--color-primary)]" />
      ) : null}
    </div>
  );
}

function SideItem({
  label,
  icon,
  active,
}: {
  label: string;
  icon: string;
  active?: boolean;
}) {
  return (
    <div
      className={`flex h-10 items-center gap-2.5 rounded-[10px] px-3 text-sm ${
        active
          ? 'bg-[var(--color-fill-2)] font-semibold text-[var(--color-primary)]'
          : 'font-normal text-[var(--color-text-2)]'
      }`}
    >
      <Icon
        type={icon}
        className={`h-4 w-4 shrink-0 ${
          active ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'
        }`}
      />
      {label}
    </div>
  );
}

function GradientAddCard() {
  return (
    <div className="flex h-[176px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg)] text-[var(--color-text-3)] shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--color-border-2)] text-[22px] font-light leading-none">
        +
      </div>
      <div className="text-sm">新增</div>
    </div>
  );
}

function GradientEntityCard({
  title,
  desc,
  online,
}: {
  title: string;
  desc: string;
  online?: boolean;
}) {
  return (
    <div className="flex h-[176px] flex-col overflow-hidden rounded-xl border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="relative h-[58px] shrink-0 bg-[color-mix(in_srgb,var(--color-primary)_72%,#7c5cbf)]">
        <div className="absolute left-3 top-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-white/20">
          <span className="h-2 w-2 rounded-sm bg-white" />
        </div>
        <div className="absolute right-3 top-2 text-sm tracking-[2px] text-white/90">···</div>
        <div className="absolute bottom-[-18px] right-4 flex h-10 w-10 items-center justify-center rounded-full border-[3px] border-[var(--color-bg)] bg-[var(--color-bg)] shadow-sm">
          <Icon type="jiqiren2" className="h-4 w-4 text-[var(--color-primary)]" />
        </div>
      </div>
      <div className="flex flex-1 flex-col px-3.5 pb-3 pt-5">
        <div className="truncate text-[14px] font-semibold text-[var(--color-text-1)]">{title}</div>
        <div className="mt-1 line-clamp-1 text-xs text-[var(--color-text-3)]">{desc}</div>
        <div className="mt-auto flex items-center justify-between pt-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ${
              online
                ? 'bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-bg))] text-[var(--color-text-2)]'
                : 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                online ? 'bg-[var(--color-success)]' : 'bg-[var(--color-text-4)]'
              }`}
            />
            {online ? '上线' : '下线'}
          </span>
          <span className="text-[11px] text-[var(--color-text-4)]">管理组织: Default</span>
        </div>
      </div>
    </div>
  );
}

function IssuesPill() {
  return (
    <div className="absolute bottom-4 left-4 z-[3] flex h-7 items-center gap-2 rounded-full bg-[var(--color-fail)] px-2.5 pl-1.5 text-xs font-semibold text-white">
      <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-white text-[11px] font-bold text-[var(--color-fail)]">
        N
      </span>
      7 Issues
      <span className="ml-0.5">×</span>
    </div>
  );
}

function WhaleFab() {
  return (
    <div
      aria-hidden
      className="absolute bottom-3 right-5 z-[3] h-8 w-12 rounded-[18px_18px_10px_18px] bg-[var(--color-primary)]"
      style={{
        boxShadow: 'inset -6px -4px 0 color-mix(in srgb, white 18%, transparent)',
      }}
    />
  );
}

function ContentToolbar({ proposed }: { proposed: boolean }) {
  if (!proposed) {
    return (
      <div className="mb-4 flex justify-end">
        <div className="flex items-center">
          <div className="flex h-9 w-[220px] items-center rounded-l-lg border border-r-0 border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 text-[13px] text-[var(--color-text-4)]">
            搜索...
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded-r-lg bg-[var(--color-primary)]">
            <Icon type="search-f" className="h-4 w-4 text-white" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-[var(--color-text-1)]">工作台</span>
            <span className="rounded-full bg-[var(--color-fill-2)] px-2 py-0.5 text-[11px] text-[var(--color-text-3)]">
              4 bots
            </span>
          </div>
          <div className="mt-1 text-xs text-[var(--color-text-3)]">
            全模块统一 B 卡：Pin · 状态 · tag · Owner/Team
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex h-8 overflow-hidden rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)]">
            <span className="flex w-8 items-center justify-center bg-[var(--color-fill-2)] text-[var(--color-primary)]">
              ▦
            </span>
            <span className="flex w-8 items-center justify-center text-[var(--color-text-4)]">☰</span>
          </div>
          <button
            type="button"
            className="h-8 rounded-md bg-[var(--color-primary)] px-3 text-xs font-medium text-white"
          >
            + 新建
          </button>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-3 py-1 text-xs font-medium text-[var(--color-primary)]">
            全部 4
          </span>
          <span className="rounded-full px-3 py-1 text-xs text-[var(--color-text-3)]">置顶 2</span>
          <span className="rounded-full px-3 py-1 text-xs text-[var(--color-text-3)]">Online 3</span>
        </div>
        <div className="flex h-8 w-[220px] items-center gap-2 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-2.5 text-xs text-[var(--color-text-4)]">
          <Icon type="search-f" className="h-3.5 w-3.5" />
          搜索名称、团队
        </div>
      </div>
    </div>
  );
}

function ChromeShell({
  caption,
  proposed,
}: {
  caption: ReactNode;
  proposed: boolean;
}) {
  const chromeClass = proposed ? 'bg-[var(--color-fill-1)]' : 'bg-[var(--color-bg)]';

  return (
    <div className="relative min-h-[820px] overflow-hidden bg-[var(--color-background-body)] font-sans text-[var(--color-text-1)]">
      <Watermark />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[42%] bg-[radial-gradient(ellipse_at_bottom,var(--color-fill-1),transparent_70%)]" />

      <div className="relative z-[1] flex min-h-[820px] flex-col">
        <header
          className={`grid h-14 shrink-0 grid-cols-[240px_minmax(0,1fr)_auto] items-center border-b ${
            proposed ? 'border-[var(--color-border-1)]' : 'border-transparent'
          } ${chromeClass}`}
        >
          <div className="flex items-center gap-2 px-4">
            <span className="relative flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)]">
              <span className="h-2 w-2 rounded-full bg-white" />
              <span className="absolute inset-[3px] rounded-full border border-white/70" />
            </span>
            <span className="text-base font-bold tracking-tight text-[var(--color-text-1)]">WeOpsX</span>
          </div>
          <div className="flex min-w-0 items-center pr-2">
            <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto overflow-y-hidden pl-1 [scrollbar-width:none] [mask-image:linear-gradient(to_right,#000_calc(100%-18px),transparent)]">
              {proposed
                ? APPS_PROPOSED.map((app) => (
                    <AppChip key={app.name} name={app.name} active={app.active} />
                ))
                : APPS_NOW.map((name) => <AppChip key={name} name={name} flat />)}
            </div>
            {proposed && (
              <span
                aria-hidden
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-bg-1)_28%,transparent)] text-[var(--color-text-3)] backdrop-blur-[2px]"
              >
                <svg viewBox="0 0 12 12" className="h-2.5 w-2.5">
                  <path
                    d="M4.2 2.35 8.15 6 4.2 9.65"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.35"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
            )}
          </div>
          <div className="flex items-center gap-3.5 px-4">
            <Icon type="search-f" className="h-4 w-4 text-[var(--color-text-3)]" />
            <Icon type="shiyongwendang" className="h-4 w-4 text-[var(--color-text-3)]" />
            <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-[var(--color-primary)] text-[11px] font-bold text-white">
              A
            </span>
            <div className="flex flex-col leading-tight">
              <span className="text-xs font-semibold">admin</span>
              <span className="text-[10px] text-[var(--color-text-3)]">Default</span>
            </div>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <aside
            className={`flex w-60 shrink-0 flex-col gap-1 px-3 py-4 ${
              proposed ? 'border-r border-[var(--color-border-1)]' : ''
            } ${chromeClass}`}
          >
            {SIDE_MENUS.map((item) => (
              <SideItem
                key={item.label}
                label={item.label}
                icon={item.icon}
                active={item.active}
              />
            ))}
          </aside>

          <main className="relative min-w-0 flex-1 p-5">
            <ContentToolbar proposed={proposed} />
            {proposed ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {B_CARDS.map((card) => (
                  <UnifiedOpsCard key={card.name} {...card} showPin footer="entity" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3.5 xl:grid-cols-4">
                {GRADIENT_CARDS.map((card) =>
                  card.add ? (
                    <GradientAddCard key="add" />
                  ) : (
                    <GradientEntityCard
                      key={card.title}
                      title={card.title}
                      desc={card.desc}
                      online={card.online}
                    />
                  ),
                )}
              </div>
            )}
          </main>
        </div>
      </div>

      <IssuesPill />
      <WhaleFab />

      <div className="absolute left-4 top-4 z-[4] max-w-[460px] rounded-lg border border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-bg)_94%,transparent)] px-3 py-2 text-xs leading-relaxed text-[var(--color-text-2)] backdrop-blur-sm">
        {caption}
      </div>
    </div>
  );
}

export function ConsoleAppTopChromeNow() {
  return (
    <ChromeShell
      proposed={false}
      caption={
        <>
          <div className="font-semibold text-[var(--color-text-1)]">现状 · 渐变头卡</div>
          顶栏无选中态；卡片靠大面积蓝紫渐变吸睛，信息层（状态/组织）偏弱，模块间难统一。
        </>
      }
    />
  );
}

export function ConsoleAppTopChromeProposed() {
  return (
    <ChromeShell
      proposed
      caption={
        <>
          <div className="font-semibold text-[var(--color-text-1)]">建议 · 壳层 + Look B 统一卡</div>
          OpsPilot 选中清晰；卡片固定解剖（图标/标题/状态/摘要/tag/Owner·Team），内容字段可因模块而异。
        </>
      }
    />
  );
}
