'use client';

import React from 'react';
import Link from 'next/link';
import { MYSQL_VERSION_UNKNOWN, type MysqlHostCandidate, type MysqlProHeader } from './ia';
import { mysqlCategoryText } from './mysql-copy';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import pro from './pro.module.scss';

const ROLE_COPY: Record<MysqlProHeader['pill'], 'rolePrimary' | 'roleReplica' | 'roleGr' | 'roleGalera'> = {
  主库: 'rolePrimary',
  从库: 'roleReplica',
  GR: 'roleGr',
  Galera: 'roleGalera'
};

/** 从库可写才把读写 tag 改成警示色。 */
const writableReplica = (header: MysqlProHeader) => (
  header.pill === '从库' && header.aside !== '只读'
);

/** 主库关 Binlog 才把 Binlog tag 改成警示色。 */
const primaryBinlogOff = (header: MysqlProHeader) => (
  header.pill === '主库' && header.binlog === 'Binlog · 已关闭'
);

const IdentityPill = ({
  slot,
  warning = false,
  children
}: {
  slot: string;
  warning?: boolean;
  children: React.ReactNode;
}) => (
  <span
    className={warning ? `${pro.identityPill} ${pro.identityPillWarn}` : pro.identityPill}
    data-mysql-identity-slot={slot}
    data-warning={warning ? '' : undefined}
  >
    {children}
  </span>
);

const IdentitySkeleton = () => (
  <>
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonRole} animate-neutral-pulse`} />
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonAside} animate-neutral-pulse`} />
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonVersion} animate-neutral-pulse`} />
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonBinlog} animate-neutral-pulse`} />
  </>
);

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

  return (
    <div
      className={pro.identityBadges}
      data-mysql-identity=""
      data-mysql-identity-pending={pending ? '' : undefined}
      data-mysql-identity-host-pending={hostPending ? '' : undefined}
      aria-busy={pending || hostPending || undefined}
    >
      {pending ? (
        <IdentitySkeleton />
      ) : header ? (
        <>
          <IdentityPill slot="role">
            {mysqlCategoryText(t, ROLE_COPY[header.pill])}
          </IdentityPill>
          <IdentityPill slot="access" warning={writableReplica(header)}>
            {mysqlCategoryText(t, accessKey)}
          </IdentityPill>
          <IdentityPill slot="version">
            {versionText}
          </IdentityPill>
          {binlogText ? (
            <IdentityPill slot="binlog" warning={primaryBinlogOff(header)}>
              {binlogText}
            </IdentityPill>
          ) : null}
        </>
      ) : null}
      {hostPending ? (
        <span className={`${pro.identitySkeleton} ${pro.identitySkeletonHost} animate-neutral-pulse`} />
      ) : host ? (
        <span className={pro.identityHost} data-mysql-identity-host="linked">
          <span className={pro.identityHostName} title={host.name}>{host.name}</span>
          <span className={pro.identityHostDot} aria-hidden="true">·</span>
          <Link className={pro.identityHostLink} href={hostHref}>
            {mysqlCategoryText(t, 'viewHost')}
          </Link>
        </span>
      ) : (
        <span className={pro.identityHostUnlinked} data-mysql-identity-host="unlinked">
          {mysqlCategoryText(t, 'hostUnlinked')}
        </span>
      )}
    </div>
  );
}
