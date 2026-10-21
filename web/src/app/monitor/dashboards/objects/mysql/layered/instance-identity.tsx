'use client';

import React from 'react';
import Link from 'next/link';
import { Tag } from 'antd';
import { ProDashLoading } from '../../host/layered/pro-chrome';
import { HOST_THRESHOLD_COLOR, hostThresholdColor } from '../../host/config';
import { MYSQL_VERSION_UNKNOWN, type MysqlHostCandidate, type MysqlProHeader } from './ia';
import { mysqlCategoryText } from './mysql-copy';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import classic from '../../host/index.module.scss';
import shell from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';

const ROLE_COPY: Record<MysqlProHeader['pill'], 'rolePrimary' | 'roleReplica' | 'roleGr' | 'roleGalera'> = {
  主库: 'rolePrimary',
  从库: 'roleReplica',
  GR: 'roleGr',
  Galera: 'roleGalera'
};

const percentText = (value: number | null) => (
  value != null && Number.isFinite(value) ? `${Math.round(value)}%` : '—'
);

const clampPercent = (value: number | null) => (
  value != null && Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0
);

const meterColor = (value: number | null) => (
  value != null && Number.isFinite(value) ? hostThresholdColor(value) : HOST_THRESHOLD_COLOR.ok
);

/** 从库可写、主库关 Binlog 才着色，其余中性。 */
const writableReplica = (header: MysqlProHeader) => (
  header.pill === '从库' && header.aside !== '只读'
);

const binlogTagColor = (header: MysqlProHeader) => (
  header.pill === '主库' && header.binlog === 'Binlog · 已关闭' ? 'warning' : undefined
);

export function MysqlInstanceBadges({
  header,
  pending
}: {
  header: MysqlProHeader | null;
  pending: boolean;
}) {
  const { t } = useDashboardText();
  return (
    <div
      className={pro.identityBadges}
      data-mysql-identity=""
      data-mysql-identity-pending={pending ? '' : undefined}
      aria-busy={pending || undefined}
    >
      {pending ? (
        <ProDashLoading size="small" layout="inline" />
      ) : (
        <>
          {header?.pill ? (
            <Tag className="!m-0">
              {mysqlCategoryText(t, ROLE_COPY[header.pill])}
            </Tag>
          ) : null}
          {header?.pill === '从库' || header?.aside ? (
            <Tag className="!m-0" color={header && writableReplica(header) ? 'warning' : undefined}>
              {mysqlCategoryText(t, header?.aside === '只读' ? 'readOnly' : 'writable')}
            </Tag>
          ) : null}
          {header?.binlog ? (
            <Tag className="!m-0" color={binlogTagColor(header)}>
              {mysqlCategoryText(t, header.binlog === 'Binlog · 已开启' ? 'binlogOn' : 'binlogOff')}
            </Tag>
          ) : null}
          <Tag className="!m-0">
            {header?.version && header.version !== MYSQL_VERSION_UNKNOWN
              ? header.version
              : mysqlCategoryText(t, 'versionUnknown')}
          </Tag>
        </>
      )}
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
    <div className={pro.hostMeter}>
      <span className={shell.shortcutSub}>
        {label}{' '}
        <b className={pro.hostMeterValue}>{percentText(value)}</b>
      </span>
      <span className={pro.hostMeterTrack} aria-hidden="true">
        <span
          className={pro.hostMeterFill}
          style={{ width: `${fill}%`, background: meterColor(value) }}
        />
      </span>
    </div>
  );
}

/** 健康概览上方的所属主机条。通栏薄条，进度条吃满到按钮前。 */
export function MysqlHostStrip({
  host,
  href,
  cpuPercent,
  memPercent,
  hostLoading = false
}: {
  host: MysqlHostCandidate | null;
  href: string;
  cpuPercent: number | null;
  memPercent: number | null;
  hostLoading?: boolean;
}) {
  const { t } = useDashboardText();
  const pending = hostLoading && !host;
  return (
    <div
      className={`${classic.panel} ${pro.hostStrip}`}
      data-host-strip=""
      data-host-strip-pending={pending ? '' : undefined}
      aria-busy={pending || undefined}
    >
      <span className={shell.shortcutSub}>{mysqlCategoryText(t, 'host')}</span>
      {pending ? (
        <ProDashLoading size="small" layout="inline" />
      ) : host ? (
        <>
          <span className={pro.hostStripName} title={host.name}>{host.name}</span>
          <HostUsageMeter label={mysqlCategoryText(t, 'cpu')} value={cpuPercent} />
          <HostUsageMeter label={mysqlCategoryText(t, 'memory')} value={memPercent} />
          <Link className={`${shell.jumpBtn} ${pro.hostStripJump}`} href={href}>
            {mysqlCategoryText(t, 'viewHost')}
          </Link>
        </>
      ) : (
        <span className={shell.shortcutSub}>{mysqlCategoryText(t, 'hostUnlinked')}</span>
      )}
    </div>
  );
}
