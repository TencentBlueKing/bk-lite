'use client';

import React from 'react';
import Link from 'next/link';
import { MYSQL_VERSION_UNKNOWN, type MysqlHostCandidate, type MysqlProHeader } from './ia';
import { mysqlCategoryText } from './mysql-copy';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import pro from './pro.module.scss';

const ROLE_COPY: Record<MysqlProHeader['pill'], 'rolePrimary' | 'roleReplica' | 'roleGr' | 'roleGalera' | 'roleUnknown'> = {
  主库: 'rolePrimary',
  从库: 'roleReplica',
  GR: 'roleGr',
  Galera: 'roleGalera',
  角色未知: 'roleUnknown'
};

/** 从库可写才把读写改成警示字色，仍是灰字链里的一段，不是胶囊。 */
const writableReplica = (header: MysqlProHeader) => (
  header.pill === '从库' && header.aside !== '只读'
);

/** 主库关 Binlog 才把该段改成警示字色。 */
const primaryBinlogOff = (header: MysqlProHeader) => (
  header.pill === '主库' && header.binlog === 'Binlog · 已关闭'
);

const Sep = () => <span className={pro.metaSep} aria-hidden="true">·</span>;

/**
 * 专业盘标题下的单行灰字。高度锁在 22px，切实例时由调用方把 header 置空。
 */
export function MysqlInstanceBadges({
  header,
  pending,
  host,
  hostHref,
  hostPending
}: {
  header: MysqlProHeader | null;
  pending: boolean;
  host: MysqlHostCandidate | null;
  hostHref: string;
  hostPending: boolean;
}) {
  const { t } = useDashboardText();
  const unknown = mysqlCategoryText(t, 'versionUnknown');
  const versionText = header?.version && header.version !== MYSQL_VERSION_UNKNOWN
    ? header.version
    : unknown;
  const accessKey = header?.aside === '只读' ? 'readOnly' : 'writable';
  const binlogText = header?.binlog === 'Binlog · 已开启'
    ? mysqlCategoryText(t, 'binlogOn')
    : header?.binlog === 'Binlog · 已关闭'
      ? mysqlCategoryText(t, 'binlogOff')
      : null;

  const parts: React.ReactNode[] = [];
  if (!pending && header) {
    parts.push(
      <span key="role" data-mysql-identity-slot="role">
        {mysqlCategoryText(t, ROLE_COPY[header.pill])}
      </span>
    );
    const showAccess = header.pill !== '角色未知' || header.aside === '只读';
    if (showAccess) {
      parts.push(
        <span
          key="access"
          data-mysql-identity-slot="access"
          className={writableReplica(header) ? pro.metaWarn : undefined}
          data-warning={writableReplica(header) ? '' : undefined}
        >
          {mysqlCategoryText(t, accessKey)}
        </span>
      );
    }
    parts.push(
      <span key="version" data-mysql-identity-slot="version">
        {versionText}
      </span>
    );
    if (binlogText) {
      parts.push(
        <span
          key="binlog"
          data-mysql-identity-slot="binlog"
          className={primaryBinlogOff(header) ? pro.metaWarn : undefined}
          data-warning={primaryBinlogOff(header) ? '' : undefined}
        >
          {binlogText}
        </span>
      );
    }
  }
  if (!pending) {
    if (hostPending) {
      parts.push(
        <span
          key="host-pending"
          className={`${pro.identitySkeleton} ${pro.identitySkeletonHost} animate-neutral-pulse`}
        />
      );
    } else if (host) {
      parts.push(
        <span key="host" className={pro.hostSegment} data-mysql-identity-host="linked">
          <span className={pro.hostLabel}>{mysqlCategoryText(t, 'host')}</span>
          <Link className={pro.hostLink} href={hostHref} title={host.name}>
            {host.name}
          </Link>
        </span>
      );
    } else {
      parts.push(
        <span key="host" className={pro.hostUnlinked} data-mysql-identity-host="unlinked">
          {mysqlCategoryText(t, 'hostUnlinked')}
        </span>
      );
    }
  }

  return (
    <div
      className={pro.identityLine}
      data-mysql-identity=""
      data-mysql-identity-pending={pending ? '' : undefined}
      data-mysql-identity-host-pending={hostPending ? '' : undefined}
      aria-busy={pending || hostPending || undefined}
    >
      {pending ? (
        <span className={`${pro.identitySkeleton} animate-neutral-pulse`} />
      ) : parts.map((part, index) => (
        <React.Fragment key={index}>
          {index > 0 ? <Sep /> : null}
          {part}
        </React.Fragment>
      ))}
    </div>
  );
}
