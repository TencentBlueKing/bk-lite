'use client';

import type { ReactNode } from 'react';
import { Switch } from 'antd';

/** 双栏左轨固定宽：会话 / 视图 / 错误 / 漏斗共用，保证竖分割线左右对齐。 */
export const RUM_WORKBENCH_ASIDE_WIDTH = 'w-[200px]';

/** 双栏栏头固定高：左右 border-b 落在同一水平线；禁止内容撑破行高。 */
export const RUM_WORKBENCH_HEAD =
  'flex h-10 shrink-0 items-center overflow-hidden border-b border-[var(--color-fill-2)] px-3.5 text-[14px] font-semibold tracking-tight text-[var(--color-text-1)]';

/**
 * RUM 双栏工作台（选型 C）：筛选项过多时用。
 * 左筛选轨 + 右内容面；外层不加描边，靠内部分割线成面。
 * 页级淡底交给全局 body（system-bg）。
 */
export function RumDualWorkbench({
  asideTitle,
  aside,
  mainTitle,
  mainExtra,
  main,
  className,
}: {
  asideTitle: ReactNode;
  aside: ReactNode;
  mainTitle: ReactNode;
  mainExtra?: ReactNode;
  main: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={[
        'flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg bg-[var(--color-bg)]',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <aside
        className={`flex ${RUM_WORKBENCH_ASIDE_WIDTH} shrink-0 flex-col border-r border-[var(--color-fill-2)]`}
      >
        <div className={RUM_WORKBENCH_HEAD}>{asideTitle}</div>
        <div className="flex flex-col gap-4 overflow-y-auto p-3.5">{aside}</div>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className={`${RUM_WORKBENCH_HEAD} justify-between gap-3`}>
          <div className="min-w-0 truncate">{mainTitle}</div>
          {mainExtra ? (
            <div className="flex shrink-0 flex-wrap items-center gap-3 text-[12px] font-normal">
              {mainExtra}
            </div>
          ) : null}
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-3.5">{main}</div>
      </div>
    </div>
  );
}

/**
 * RUM 单栏工作台：筛选项不多时用。
 * 与双栏同一白面圆角壳；顶栏菜单已表达页面名时不重复标题条。
 * 工具条 + 表格放在内容区。
 */
export function RumSingleWorkbench({
  title,
  extra,
  toolbar,
  children,
  className,
}: {
  /** @deprecated 单栏页勿再传；顶部分段菜单已承担命名 */
  title?: ReactNode;
  extra?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={[
        'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg bg-[var(--color-bg)]',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {title != null ? (
        <div className={`${RUM_WORKBENCH_HEAD} justify-between gap-3`}>
          <div className="min-w-0 truncate">{title}</div>
          {extra ? (
            <div className="flex shrink-0 flex-wrap items-center gap-3 text-[12px] font-normal">
              {extra}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-hidden p-3.5">
        {toolbar}
        {children}
      </div>
    </div>
  );
}

export function RumFilterBlock({
  title,
  children,
  className,
}: {
  title: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="mb-1.5 text-[12px] font-medium text-[var(--color-text-2)]">{title}</div>
      {children}
    </div>
  );
}

export function RumFilterSwitchRow({
  label,
  checked,
  onChange,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-[13px]">
      <span className="min-w-0 text-[var(--color-text-2)]">{label}</span>
      <Switch size="small" checked={checked} onChange={onChange} />
    </div>
  );
}
