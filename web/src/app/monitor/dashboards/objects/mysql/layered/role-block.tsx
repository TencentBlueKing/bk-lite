'use client';

import React from 'react';
import { ProSectionTitle, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR } from '../../host/config';
import classic from '../../host/index.module.scss';
import host from '../../host/layered/layered.module.scss';
import type { MysqlRoleBlockModel, MysqlRoleTone } from './ia';

const TONE_CLASS: Record<MysqlRoleTone, string> = {
  ok: host.statusCardCalm,
  warn: host.statusCardWarning,
  muted: host.statusCardNeutral
};

/** 概览角色条。高度跟主机状态卡，不铺半屏空壳。 */
export default function MysqlRoleBlock({ block }: { block: MysqlRoleBlockModel }) {
  return (
    <>
      <ProSectionTitle>实例角色</ProSectionTitle>
      <section className={`${classic.panel} ${host.chartPanel}`}>
        <div className={host.chartHead}>
          <div className={host.chartTitleGroup}>
            <div className={host.chartTitle}>{block.pill}</div>
            <div className={host.chartSubtitle}>{block.summary}</div>
          </div>
        </div>
        {block.fields.length ? (
          <div className={host.statusCards}>
            {block.fields.map((field) => (
              <div key={field.label} className={`${host.statusCard} ${TONE_CLASS[field.tone]}`}>
                <div className={host.statusLabel}>{field.label}</div>
                <div className={host.statusValue}>{field.value}</div>
              </div>
            ))}
          </div>
        ) : null}
        {block.note ? <div className={host.footnote}>{block.note}</div> : null}
        {block.delay?.length ? (
          <ThinTimeSeries
            bare
            className={host.focusChart}
            title="复制延迟"
            unit="s"
            data={block.delay}
            legends={[{ label: '延迟', color: HOST_SERIES_COLOR.memUsed }]}
          />
        ) : null}
      </section>
    </>
  );
}
