'use client';

import React from 'react';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR } from '../../host/config';
import host from '../../host/layered/layered.module.scss';
import type { MysqlRoleBlockModel, MysqlRoleTone } from './ia';

const TONE_CLASS: Record<MysqlRoleTone, string> = {
  ok: host.statusCardCalm,
  warn: host.statusCardWarning,
  muted: host.statusCardNeutral
};

/** 有采才出的紧凑复制条。不铺「实例角色」全宽卡，单卡也不拉成整行绿条。 */
export default function MysqlRoleBlock({ block }: { block: MysqlRoleBlockModel | null }) {
  if (!block || block.fields.length === 0) return null;
  return (
    <>
      <div className={host.statusCards}>
        {block.fields.map((field) => (
          <div
            key={field.label}
            className={`${host.statusCard} ${TONE_CLASS[field.tone]} !min-w-[140px] !max-w-[220px] !flex-[0_1_220px]`}
          >
            <div className={host.statusLabel}>{field.label}</div>
            <div className={host.statusValue}>{field.value}</div>
          </div>
        ))}
      </div>
      {block.delay?.length ? (
        <ThinTimeSeries
          bare
          className={`${host.focusChart} max-w-[360px]`}
          title="复制延迟"
          unit="s"
          data={block.delay}
          legends={[{ label: '延迟', color: HOST_SERIES_COLOR.memUsed }]}
        />
      ) : null}
    </>
  );
}
