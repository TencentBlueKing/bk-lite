'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import ChartEmptyState from '@/components/chart-empty-state';
import { DashboardPanel } from '../../shared/widgets';
import { buildSearchParams, formatMetricValue } from '../../shared/utils';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import type { FlowProtocol } from './constants';
import { buildProtocolTopQuery } from './queries';
import { parseProtocolRows } from './parse-protocol-rows';
import { formatProtocolShortName } from './protocol-labels';
import { resolveFlowRankClass } from './rank-class';

interface FlowProtocolBreakdownProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  protocol: FlowProtocol;
  instanceType: string;
  styles: Record<string, string>;
}

const PROTOCOL_GUIDE = [{
  label: 'Top 协议',
  detail: '所选时间窗内流量速率最高的协议分布，便于快速识别 TCP/UDP/ICMP 等占比。',
}];

const resolveProtocolClass = (label: string, styles: Record<string, string>) => {
  const normalized = formatProtocolShortName(label).toUpperCase();
  if (normalized === 'TCP') return styles.flowProtocolTcp;
  if (normalized === 'UDP') return styles.flowProtocolUdp;
  if (normalized === 'ICMP' || normalized === 'ICMPV6') return styles.flowProtocolIcmp;
  return styles.flowProtocolOther;
};

const formatBytesRate = (value: number) => {
  const formatted = formatMetricValue(value, 'byteps');
  return `${formatted.value}${formatted.unit || ''}`;
};

export function FlowProtocolBreakdown({
  dashboard,
  protocol,
  instanceType,
  styles,
}: FlowProtocolBreakdownProps) {
  const { getInstanceInstantQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams],
  );
  const [rows, setRows] = useState<ReturnType<typeof parseProtocolRows>>([]);
  const [loading, setLoading] = useState(false);
  const protocolQuery = useMemo(
    () => buildProtocolTopQuery(instanceType, protocol),
    [instanceType, protocol],
  );

  useEffect(() => {
    if (!dashboard.isDashboardMode || !instanceType) {
      setRows([]);
      return;
    }

    let active = true;
    setLoading(true);

    const load = async () => {
      const result = await getInstanceInstantQuery(
        buildSearchParams(
          protocolQuery,
          'byteps',
          dashboard.idValues,
          instanceIdKeys,
          dashboard.timeValues,
          undefined,
          false,
        ),
      ).catch(() => null);

      if (!active) return;
      setRows(parseProtocolRows(result, protocol));
      setLoading(false);
    };

    void load();

    return () => {
      active = false;
    };
  }, [
    dashboard.currentInstanceInterval,
    dashboard.idValues,
    dashboard.isDashboardMode,
    dashboard.loadTick,
    dashboard.timeValues,
    getInstanceInstantQuery,
    instanceIdKeys,
    instanceType,
    protocol,
    protocolQuery,
  ]);

  const peakRate = useMemo(
    () => (rows.length ? Math.max(...rows.map((row) => row.bytesRate)) : 0),
    [rows],
  );

  return (
    <DashboardPanel
      title="Top 协议"
      subtitle="按协议聚合的流量速率 Top 10"
      guide={PROTOCOL_GUIDE}
      className={`${styles.span4} ${styles.flowProtocolPanel}`}
      bodyClassName={styles.flowProtocolBody}
      styles={styles}
    >
      <Spin spinning={loading}>
        {!loading && rows.length === 0 ? (
          <div className={styles.flowProtocolEmpty}>
            <ChartEmptyState description="所选时间窗内无协议分布数据" compact />
          </div>
        ) : (
          <div
            className={[
              styles.flowProtocolListWrap,
              protocol === 'netflow' ? styles.flowProtocolNetflow : styles.flowProtocolSflow,
            ].join(' ')}
          >
            <div className={styles.flowProtocolListHead}>
              <span className={styles.flowProtocolHeadRank}>#</span>
              <span className={styles.flowProtocolHeadName}>协议</span>
              <span className={styles.flowProtocolHeadRate}>流量</span>
            </div>
            <ul className={styles.flowProtocolList}>
              {rows.map((row, index) => {
                const share = peakRate > 0 ? (row.bytesRate / peakRate) * 100 : 0;
                return (
                  <li
                    key={row.rowKey}
                    className={[styles.flowProtocolItem, resolveFlowRankClass(index, styles)].join(' ')}
                  >
                    <span className={styles.flowProtocolRankMark}>{index + 1}</span>
                    <span
                      className={[
                        styles.flowProtocolName,
                        resolveProtocolClass(row.label, styles),
                      ].join(' ')}
                    >
                      {formatProtocolShortName(row.label)}
                    </span>
                    <span className={styles.flowProtocolRate}>{formatBytesRate(row.bytesRate)}</span>
                    <div className={styles.flowProtocolTrack}>
                      <div
                        className={styles.flowProtocolFill}
                        style={{ width: `${Math.max(share, 6)}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </Spin>
    </DashboardPanel>
  );
}
