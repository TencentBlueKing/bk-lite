'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Table } from 'antd';
import type { TableColumnsType } from 'antd';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { DashboardPanel } from '../../shared/widgets';
import { buildSearchParams, formatMetricValue, runWithConcurrency } from '../../shared/utils';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { parseKafkaLagRiskRows, type KafkaLagRiskResult, type KafkaLagRiskRow } from './parse';
import { KAFKA_LAG_RISK_QUERIES } from './queries';

interface KafkaLagRiskTableProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: Record<string, string>;
}

const formatCount = (value: number | null) => {
  if (value == null) return '--';
  const formatted = formatMetricValue(value, 'counts');
  return `${formatted.value}${formatted.unit || ''}`;
};

export function KafkaLagRiskTable({ dashboard, styles }: KafkaLagRiskTableProps) {
  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams],
  );
  const [rows, setRows] = useState<KafkaLagRiskRow[]>([]);
  const [loading, setLoading] = useState(false);
  const idValuesKey = JSON.stringify(dashboard.idValues);
  const timeKey = JSON.stringify(dashboard.timeValues);

  useEffect(() => {
    if (!dashboard.isDashboardMode) {
      setRows([]);
      return;
    }

    let active = true;
    setLoading(true);
    runWithConcurrency(Array.from(KAFKA_LAG_RISK_QUERIES), 3, async (query) => {
      const result = await getInstanceQuery(
        buildSearchParams(
          query.query,
          query.unit,
          dashboard.idValues,
          instanceIdKeys,
          dashboard.timeValues,
          undefined,
          undefined,
          dashboard.currentInstanceInterval,
        ),
      ).catch(() => null);
      return [query.key, result] as const;
    }).then((entries) => {
      if (!active) return;
      setRows(parseKafkaLagRiskRows(Object.fromEntries(entries) as KafkaLagRiskResult));
      setLoading(false);
    });

    return () => {
      active = false;
    };
    // 查询需随核心盘的实例、时间和自动刷新周期同步重载。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard.currentInstanceInterval, dashboard.isDashboardMode, dashboard.loadTick, getInstanceQuery, idValuesKey, instanceIdKeys, timeKey]);

  const columns: TableColumnsType<KafkaLagRiskRow> = [
    { title: '消费者组', dataIndex: 'consumerGroup', key: 'consumerGroup', ellipsis: true },
    { title: 'Topic', dataIndex: 'topic', key: 'topic', ellipsis: true },
    { title: '分区', dataIndex: 'partition', key: 'partition', width: 76 },
    { title: '当前偏移', dataIndex: 'currentOffset', key: 'currentOffset', align: 'right', render: formatCount },
    { title: '最早偏移', dataIndex: 'oldestOffset', key: 'oldestOffset', align: 'right', render: formatCount },
    {
      title: 'Lag',
      dataIndex: 'lag',
      key: 'lag',
      align: 'right',
      render: (lag: number) => <span className={styles.riskLag}>{formatCount(lag)}</span>,
    },
  ];

  return (
    <DashboardPanel
      title="消费者组 Lag Top 10"
      subtitle="按消费者组、Topic、分区的当前 Lag 降序，定位最严重的消费积压。"
      guide={[{ label: 'Lag 风险定位', detail: '先确认 Lag 是否持续升高，再按消费者组、Topic 和分区排查消费者处理能力或消息积压。' }]}
      styles={styles}
      className={styles.riskPanel}
    >
      <div className={styles.riskTableWrap}>
        <Table<KafkaLagRiskRow>
          columns={columns}
          dataSource={rows}
          rowKey={(row) => `${row.consumerGroup}\u0000${row.topic}\u0000${row.partition}`}
          loading={loading}
          pagination={false}
          size="small"
          locale={{ emptyText: '当前时间范围内没有消费者组 Lag 数据' }}
        />
      </div>
    </DashboardPanel>
  );
}
