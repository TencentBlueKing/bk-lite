'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Table, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { DashboardPanel } from '../../shared/widgets';
import { buildSearchParams, formatMetricValue } from '../../shared/utils';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import type { FlowProtocol } from './constants';
import { buildConversationTopQuery } from './queries';
import { parseConversationRows, type FlowConversationRow } from './parse-conversation-rows';

interface FlowConversationTableProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  protocol: FlowProtocol;
  instanceType: string;
  styles: Record<string, string>;
}

const formatBytesRate = (value: number | null) => {
  if (value == null) return '--';
  const formatted = formatMetricValue(value, 'byteps');
  return `${formatted.value}${formatted.unit || ''}`;
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

    load();

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

  const columns: TableColumnsType<FlowConversationRow> = [
    {
      title: '#',
      key: 'rank',
      width: 48,
      render: (_value, _row, index) => index + 1,
    },
    {
      title: '源 IP',
      dataIndex: 'srcIp',
      key: 'srcIp',
      width: 132,
      ellipsis: true,
    },
    {
      title: (
        <Tooltip title="会话聚合维度不含源端口，当前版本显示为 --">
          <span>源端口</span>
        </Tooltip>
      ),
      dataIndex: 'srcPort',
      key: 'srcPort',
      width: 72,
      align: 'center',
    },
    {
      title: '目的 IP',
      dataIndex: 'dstIp',
      key: 'dstIp',
      width: 132,
      ellipsis: true,
    },
    { title: '目的端口', dataIndex: 'dstPort', key: 'dstPort', width: 88, align: 'center' },
    { title: '协议', dataIndex: 'protocol', key: 'protocol', width: 108, ellipsis: true },
    {
      title: '流量速率',
      dataIndex: 'bytesRate',
      key: 'bytesRate',
      align: 'right',
      width: 112,
      render: (value: number) => formatBytesRate(value),
    },
  ];

  return (
    <DashboardPanel
      title="Top 会话"
      subtitle="当前时间窗流量最高的 10 组会话，按源/目的 IP、目的端口与协议聚合"
      className={`${styles.span12} ${styles.flowTablePanel}`}
      bodyClassName={styles.flowTableWrap}
      styles={styles}
    >
      <Table<FlowConversationRow>
        rowKey="rowKey"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: '当前时间窗无 Flow 会话数据' }}
      />
    </DashboardPanel>
  );
}
