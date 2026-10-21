'use client';

import React from 'react';
import Link from 'next/link';
import { Dropdown, Tag } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { MYSQL_VERSION_UNKNOWN, type MysqlHostCandidate, type MysqlProHeader } from './ia';
import { mysqlCategoryText } from './mysql-copy';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import shell from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';

const ROLE_COPY: Record<MysqlProHeader['pill'], 'rolePrimary' | 'roleReplica' | 'roleGr' | 'roleGalera'> = {
  主库: 'rolePrimary',
  从库: 'roleReplica',
  GR: 'roleGr',
  Galera: 'roleGalera'
};

/** 从库可写、主库关 Binlog 才着色，其余中性。 */
const writableReplica = (header: MysqlProHeader) => (
  header.pill === '从库' && header.aside !== '只读'
);

const binlogTagColor = (header: MysqlProHeader) => (
  header.pill === '主库' && header.binlog === 'Binlog · 已关闭' ? 'warning' : undefined
);

const IdentitySkeleton = () => (
  <>
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonRole} animate-neutral-pulse`} />
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonAside} animate-neutral-pulse`} />
    <span className={`${pro.identitySkeleton} ${pro.identitySkeletonMore} animate-neutral-pulse`} />
  </>
);

export function MysqlInstanceBadges({
  header,
  pending,
  instanceId,
  timezone
}: {
  header: MysqlProHeader | null;
  pending: boolean;
  instanceId?: string;
  timezone?: string;
}) {
  const { t } = useDashboardText();
  const unknown = mysqlCategoryText(t, 'versionUnknown');
  const binlogValue = header?.binlog === 'Binlog · 已开启'
    ? mysqlCategoryText(t, 'binlogOn')
    : header?.binlog === 'Binlog · 已关闭'
      ? mysqlCategoryText(t, 'binlogOff')
      : unknown;
  const versionValue = header?.version && header.version !== MYSQL_VERSION_UNKNOWN
    ? header.version
    : unknown;
  const moreRows = [
    { key: 'id', label: mysqlCategoryText(t, 'instanceId'), value: instanceId?.trim() || unknown },
    { key: 'timezone', label: mysqlCategoryText(t, 'timezone'), value: timezone?.trim() || unknown },
    {
      key: 'binlog',
      label: mysqlCategoryText(t, 'binlog'),
      value: binlogValue,
      warning: header ? Boolean(binlogTagColor(header)) : false
    },
    { key: 'version', label: mysqlCategoryText(t, 'version'), value: versionValue }
  ];
  const morePanel = (
    <div className={pro.identityMorePanel} data-mysql-identity-more="">
      {moreRows.map((row) => (
        <div key={row.key} className={pro.identityMoreRow}>
          <span className={pro.identityMoreLabel}>{row.label}</span>
          <span
            className={pro.identityMoreValue}
            data-warning={row.warning ? '' : undefined}
          >
            {row.value}
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <div
      className={pro.identityBadges}
      data-mysql-identity=""
      data-mysql-identity-pending={pending ? '' : undefined}
      aria-busy={pending || undefined}
    >
      {pending ? (
        <IdentitySkeleton />
      ) : (
        <>
          {header?.pill ? (
            <Tag className={`!m-0 ${pro.identityPill}`}>
              {mysqlCategoryText(t, ROLE_COPY[header.pill])}
            </Tag>
          ) : null}
          {header?.pill === '从库' || header?.aside ? (
            <Tag className={`!m-0 ${pro.identityPill}`} color={header && writableReplica(header) ? 'warning' : undefined}>
              {mysqlCategoryText(t, header?.aside === '只读' ? 'readOnly' : 'writable')}
            </Tag>
          ) : null}
          <Dropdown trigger={['click']} menu={{ items: [] }} popupRender={() => morePanel}>
            <button
              type="button"
              className={pro.identityMoreBtn}
              aria-haspopup="dialog"
              aria-label={mysqlCategoryText(t, 'more')}
            >
              <span>{mysqlCategoryText(t, 'more')}</span>
              <DownOutlined className={pro.identityMoreCaret} aria-hidden="true" />
            </button>
          </Dropdown>
        </>
      )}
    </div>
  );
}

/** 健康概览标题下的所属主机旁注。只留主机名和跳转，不要资源数字或进度条。 */
export function MysqlHostNote({
  host,
  href,
  hostLoading = false
}: {
  host: MysqlHostCandidate | null;
  href: string;
  hostLoading?: boolean;
}) {
  const { t } = useDashboardText();
  const pending = hostLoading && !host;
  return (
    <div
      className={pro.hostNote}
      data-host-note=""
      data-host-note-pending={pending ? '' : undefined}
      aria-busy={pending || undefined}
    >
      <span className={shell.shortcutSub}>{mysqlCategoryText(t, 'host')}</span>
      {pending ? (
        <span className={`${pro.hostNoteSkeleton} animate-neutral-pulse`} />
      ) : host ? (
        <>
          <span className={pro.hostNoteName} title={host.name}>{host.name}</span>
          <Link className={pro.hostNoteJump} href={href}>
            {mysqlCategoryText(t, 'viewHost')}
          </Link>
        </>
      ) : (
        <span className={shell.shortcutSub}>{mysqlCategoryText(t, 'hostUnlinked')}</span>
      )}
    </div>
  );
}
