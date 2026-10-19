'use client';

import React, { useMemo } from 'react';
import { KpiStrip, type KpiCardModel } from '../../host/layered/signal-bar';
import classic from '../../host/index.module.scss';
import host from '../../host/layered/layered.module.scss';
import {
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  type MysqlFocusCard,
  type MysqlOverviewReadings
} from './ia';
import MysqlHostRail from './host-rail';
import type { MysqlHostCandidate } from './ia';
import pro from './pro.module.scss';

interface OverviewPaneProps {
  readings: MysqlOverviewReadings;
  previous: Pick<MysqlOverviewReadings, 'slowPerSecond' | 'connectionUtilization' | 'bufferPoolHit'>;
  loading: boolean;
  statementsCollected: boolean;
  host: MysqlHostCandidate | null;
  hostHref: string;
  cpuPercent: number | null;
  memPercent: number | null;
  alertsOpen: boolean;
  onOpenAlerts: () => void;
  onOpenFocus: (card: MysqlFocusCard) => void;
}

export default function OverviewPane({
  readings,
  previous,
  loading,
  statementsCollected,
  host: linkedHost,
  hostHref,
  cpuPercent,
  memPercent,
  alertsOpen,
  onOpenAlerts,
  onOpenFocus
}: OverviewPaneProps) {
  const cards = useMemo<KpiCardModel[]>(() => (
    buildMysqlOverviewKpis(readings).map((card) => ({
      key: card.key,
      label: card.label,
      value: card.value,
      detail: card.detail,
      tone: card.tone,
      onActivate: card.key === 'alerts' ? onOpenAlerts : undefined,
      expanded: card.key === 'alerts' ? alertsOpen : undefined
    }))
  ), [alertsOpen, onOpenAlerts, readings]);
  const focus = useMemo(
    () => buildMysqlFocusCards(readings, previous, statementsCollected),
    [previous, readings, statementsCollected]
  );

  return (
    <>
      <div className={host.sectionHead}>
        <div className={`${classic.sectionLabel} ${host.sectionTitle}`}>健康概览</div>
      </div>
      {cards.length > 0 ? <KpiStrip items={cards} /> : null}
      {!loading && cards.length === 0 ? (
        <div className={pro.emptyHint}>当前窗口没有可展示的实例指标</div>
      ) : null}

      <div className={host.sectionHead}>
        <div className={`${classic.sectionLabel} ${host.sectionTitle}`}>所属主机</div>
      </div>
      <MysqlHostRail
        host={linkedHost}
        href={hostHref}
        cpuPercent={cpuPercent}
        memPercent={memPercent}
      />

      {focus.length > 0 ? (
        <>
          <div className={host.sectionHead}>
            <div className={`${classic.sectionLabel} ${host.sectionTitle}`}>重点关注</div>
          </div>
          <div className={host.shortcutGrid}>
            {focus.map((card) => (
              <button
                key={card.key}
                type="button"
                className={`${classic.panel} ${host.shortcutCard} ${pro.focusBtn}`}
                onClick={() => onOpenFocus(card)}
              >
                <div className={host.shortcutCopy}>
                  <div className={host.shortcutLabel}>{card.label}</div>
                  <div className={host.shortcutMain}>{card.value}</div>
                  {card.delta ? (
                    <div className={host.shortcutValue} style={card.deltaTone ? { color: card.deltaTone } : undefined}>
                      {card.delta}
                    </div>
                  ) : null}
                  <div className={host.shortcutSub}>{card.hint}</div>
                </div>
              </button>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}
