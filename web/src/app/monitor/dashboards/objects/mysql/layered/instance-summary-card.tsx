'use client';

import React from 'react';
import Link from 'next/link';
import { Tag } from 'antd';
import { ProDashLoading, ProSectionTitle } from '../../host/layered/pro-chrome';
import { MYSQL_VERSION_UNKNOWN, type MysqlHostCandidate, type MysqlProHeader } from './ia';
import classic from '../../host/index.module.scss';
import shell from '../../host/layered/layered.module.scss';

interface MysqlInstanceSummaryCardProps {
  header: MysqlProHeader | null;
  headerPending: boolean;
  host: MysqlHostCandidate | null;
  href: string;
  cpuPercent: number | null;
  memPercent: number | null;
  hostLoading?: boolean;
}

const ROLE_TAG_COLOR: Record<MysqlProHeader['pill'], string> = {
  主库: 'geekblue',
  从库: 'purple',
  GR: 'cyan',
  Galera: 'cyan'
};

const percentText = (value: number | null) => (
  value != null && Number.isFinite(value) ? `${Math.round(value)}%` : '—'
);

const clampPercent = (value: number | null) => (
  value != null && Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0
);

const binlogStatus = (binlog: MysqlProHeader['binlog']) => {
  if (binlog === 'Binlog · 已开启') return { label: '已开启', color: 'green' };
  if (binlog === 'Binlog · 已关闭') return { label: '已关闭', color: 'default' };
  return null;
};

function BadgeField({
  label,
  children
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs leading-4 text-[var(--color-text-3)]">{label}</span>
      <div className="flex items-center gap-1.5">{children}</div>
    </div>
  );
}

function HostUsageMeter({
  label,
  value
}: {
  label: string;
  value: number | null;
}) {
  const fill = clampPercent(value);
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <span className="shrink-0 whitespace-nowrap text-xs leading-4 text-[var(--color-text-3)]">
        {label}{' '}
        <b className="font-semibold tabular-nums text-[var(--color-text-1)]">{percentText(value)}</b>
      </span>
      <span
        className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--color-fill-2)]"
        aria-hidden="true"
      >
        <span
          className="block h-full rounded-full bg-[var(--color-primary)]"
          style={{ width: `${fill}%` }}
        />
      </span>
    </div>
  );
}

/**
 * 概览 Tab 下、健康概览前的通栏实例摘要。
 * 左徽章贴内容，右宿主段 flex 吃满剩余宽；进度条再在宿主段里吃满。
 * pending 时忽略 header，避免切实例还亮着上一份角色 / 只读 / Binlog / 版本。
 */
export default function MysqlInstanceSummaryCard({
  header,
  headerPending,
  host,
  href,
  cpuPercent,
  memPercent,
  hostLoading = false
}: MysqlInstanceSummaryCardProps) {
  const binlog = binlogStatus(header?.binlog);
  const hostPending = hostLoading && !host;

  return (
    <div
      className={`${classic.panel} box-border w-full min-w-0 p-4`}
      data-instance-summary=""
      data-instance-summary-pending={headerPending || hostPending ? '' : undefined}
      aria-busy={headerPending || hostPending ? true : undefined}
    >
      <div className="flex w-full min-w-0 flex-col gap-4 lg:flex-row lg:items-stretch lg:gap-6">
        <div className="flex shrink-0 flex-col gap-3">
          <ProSectionTitle>实例摘要</ProSectionTitle>
          {headerPending ? (
            <ProDashLoading size="small" layout="inline" />
          ) : (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
              {header?.pill ? (
                <BadgeField label="角色">
                  <Tag className="!m-0" color={ROLE_TAG_COLOR[header.pill]}>{header.pill}</Tag>
                </BadgeField>
              ) : null}
              {header?.aside ? (
                <BadgeField label="读写">
                  <Tag className="!m-0" color={header.aside === '只读' ? 'blue' : 'gold'}>
                    {header.aside}
                  </Tag>
                </BadgeField>
              ) : null}
              {binlog ? (
                <BadgeField label="Binlog">
                  <Tag className="!m-0" color={binlog.color}>{binlog.label}</Tag>
                </BadgeField>
              ) : null}
              <BadgeField label="版本">
                <Tag className="!m-0">{header?.version || MYSQL_VERSION_UNKNOWN}</Tag>
              </BadgeField>
            </div>
          )}
        </div>

        <div
          className="h-px w-full shrink-0 bg-[var(--color-border)] lg:h-auto lg:w-px lg:self-stretch"
          aria-hidden="true"
        />

        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2">
          {hostPending ? (
            <ProDashLoading layout="inline" />
          ) : host ? (
            <>
              <span className="text-xs leading-4 text-[var(--color-text-3)]">所属主机</span>
              <span className="min-w-0 truncate font-medium text-[var(--color-text-1)]" title={host.name}>
                {host.name}
              </span>
              <div className="flex w-full min-w-0 items-center gap-6">
                <HostUsageMeter label="CPU" value={cpuPercent} />
                <HostUsageMeter label="内存" value={memPercent} />
              </div>
              <Link
                className={`${shell.jumpBtn} !mt-0 w-fit shrink-0 self-start whitespace-nowrap no-underline`}
                href={href}
              >
                查看主机 →
              </Link>
            </>
          ) : (
            <>
              <span className="text-xs leading-4 text-[var(--color-text-3)]">所属主机</span>
              <span className="text-[var(--color-text-3)]">未关联主机</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
