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
import { buildConversationTopQuery } from './queries';
import { parseConversationRows, type FlowConversationRow } from './parse-conversation-rows';
import { formatProtocolShortName } from './protocol-labels';
import { resolveFlowRankClass } from './rank-class';

interface FlowConversationTableProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  protocol: FlowProtocol;
  instanceType: string;
  styles: Record<string, string>;
}

const CONVERSATION_GUIDE = [{
  label: 'Top 会话',
  detail: '所选时间窗内平均流量速率最高的 10 组会话，按源/目的地址、端口与协议聚合展示。',
}];

const formatBytesRate = (value: number | null) => {
  if (value == null) return '--';
  const formatted = formatMetricValue(value, 'byteps');
  return `${formatted.value}${formatted.unit || ''}`;
};

const resolveProtocolClass = (label: string, styles: Record<string, string>) => {
  const normalized = formatProtocolShortName(label).toUpperCase();
  if (normalized === 'TCP') return styles.flowProtocolTcp;
  if (normalized === 'UDP') return styles.flowProtocolUdp;
  if (normalized === 'ICMP' || normalized === 'ICMPV6') return styles.flowProtocolIcmp;
  return styles.flowProtocolOther;
};

const formatPort = (port: string) => {
  const normalized = String(port || '').trim();
  if (!normalized || normalized === '--' || normalized === '0') return '*';
  return normalized;
};

export function FlowConversationTable({
  dashboard,
  protocol,
  instanceType,
  styles,
}: FlowConversationTableProps) {
  const { getInstanceInstantQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams],
  );
  const [rows, setRows] = useState<FlowConversationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const conversationQuery = useMemo(
    () => buildConversationTopQuery(instanceType, protocol),
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
          conversationQuery,
          'byteps',
          dashboard.idValues,
          instanceIdKeys,
          dashboard.timeValues,
          undefined,
          false,
        ),
      ).catch(() => null);

      if (!active) return;
      setRows(parseConversationRows(result, protocol));
      setLoading(false);
    };

    void load();

    return () => {
      active = false;
    };
  }, [
    conversationQuery,
    dashboard.currentInstanceInterval,
    dashboard.idValues,
    dashboard.isDashboardMode,
    dashboard.loadTick,
    dashboard.timeValues,
    getInstanceInstantQuery,
    instanceIdKeys,
    instanceType,
    protocol,
  ]);

  const peakRate = useMemo(
    () => (rows.length ? Math.max(...rows.map((row) => row.bytesRate)) : 0),
    [rows],
  );

  return (
    <DashboardPanel
      title="Top 会话"
      subtitle="Top 10 会话 · 按源/目的地址、端口与协议聚合"
      guide={CONVERSATION_GUIDE}
      className={`${styles.span8} ${styles.flowConversationPanel}`}
      bodyClassName={styles.flowConversationBody}
      styles={styles}
    >
      <Spin spinning={loading}>
        {!loading && rows.length === 0 ? (
          <div className={styles.flowConversationEmpty}>
            <ChartEmptyState description="所选时间窗内无 Flow 会话数据" compact />
          </div>
        ) : (
          <div
            className={[
              styles.flowConversationTableWrap,
              protocol === 'netflow' ? styles.flowConversationNetflow : styles.flowConversationSflow,
            ].join(' ')}
          >
            <table className={styles.flowConversationTable}>
              <colgroup>
                <col className={styles.flowColRank} />
                <col className={styles.flowColIp} />
                <col className={styles.flowColIp} />
                <col className={styles.flowColPort} />
                <col className={styles.flowColPort} />
                <col className={styles.flowColProtocol} />
                <col className={styles.flowColTraffic} />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className={styles.flowColRank}>#</th>
                  <th scope="col" className={styles.flowColIp}>源地址</th>
                  <th scope="col" className={styles.flowColIp}>目的地址</th>
                  <th scope="col" className={styles.flowColPort}>源端口</th>
                  <th scope="col" className={styles.flowColPort}>目的端口</th>
                  <th scope="col" className={styles.flowColProtocol}>协议</th>
                  <th scope="col" className={styles.flowColTraffic}>流量</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const share = peakRate > 0 ? (row.bytesRate / peakRate) * 100 : 0;
                  return (
                    <tr key={row.rowKey} className={resolveFlowRankClass(index, styles)}>
                      <td className={styles.flowCellRank}>
                        <span className={styles.flowProtocolRankMark}>{index + 1}</span>
                      </td>
                      <td className={styles.flowCellIp} title={row.srcIp}>{row.srcIp}</td>
                      <td className={styles.flowCellIp} title={row.dstIp}>{row.dstIp}</td>
                      <td className={styles.flowCellPort}>{formatPort(row.srcPort)}</td>
                      <td className={styles.flowCellPort}>{formatPort(row.dstPort)}</td>
                      <td className={styles.flowCellProtocol}>
                        <span
                          className={[
                            styles.flowProtocolBadge,
                            resolveProtocolClass(row.protocol, styles),
                          ].join(' ')}
                        >
                          {formatProtocolShortName(row.protocol)}
                        </span>
                      </td>
                      <td className={styles.flowCellTraffic}>
                        <span className={styles.flowTrafficValue}>{formatBytesRate(row.bytesRate)}</span>
                        <span className={styles.flowTrafficTrack}>
                          <span
                            className={styles.flowTrafficFill}
                            style={{ width: `${Math.max(share, 4)}%` }}
                          />
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Spin>
    </DashboardPanel>
  );
}
