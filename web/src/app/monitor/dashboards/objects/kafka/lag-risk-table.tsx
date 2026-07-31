'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Table } from 'antd';
import type { TableColumnsType } from 'antd';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { DashboardPanel, TrendChartPanel } from '../../shared/widgets';
import { buildSearchParams, formatMetricValue } from '../../shared/utils';
import { renderChart } from '@/app/monitor/utils/common';
import { ChartData } from '@/app/monitor/types';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  getSortedChartValueKeys,
  kafkaLagRowDimensionKey,
  mapChartSeriesToLagDimensions,
  parseKafkaLagRiskRows,
  type KafkaLagRiskResult,
  type KafkaLagRiskRow,
} from './parse';
import { buildKafkaTopNExactQuery, KAFKA_LAG_TOP_QUERY } from './queries';

interface KafkaLagRiskTableProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: Record<string, string>;
}

const LAG_TREND_COLORS = [
  '#2f6bff', '#13c2c2', '#722ed1', '#eb2f96', '#fa8c16',
  '#52c41a', '#1890ff', '#f5222d', '#a0d911', '#faad14',
];
// 表格保留 Top 10；趋势只画前 5，避免 10 条长标签曲线挤在一起。
const LAG_TREND_SERIES_LIMIT = 5;

const formatCount = (value: number | null) => {
  if (value == null) return '--';
  const formatted = formatMetricValue(value, 'counts');
  return `${formatted.value}${formatted.unit || ''}`;
};

export function KafkaLagRiskTable({ dashboard, styles }: KafkaLagRiskTableProps) {
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams],
  );
  const [rows, setRows] = useState<KafkaLagRiskRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState<ChartData[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const idValuesKey = JSON.stringify(dashboard.idValues);
  const timeKey = JSON.stringify(dashboard.timeValues);

  useEffect(() => {
    if (!dashboard.isDashboardMode) {
      setRows([]);
      setSelectedKey(null);
      return;
    }

    let active = true;
    setLoading(true);
    setSelectedKey(null);
    const load = async () => {
      // 首屏只做一次 instant Top 10 查询；负 Lag 不参与正常风险排行。
      const lag = await getInstanceInstantQuery(buildSearchParams(
        KAFKA_LAG_TOP_QUERY, 'counts', dashboard.idValues, instanceIdKeys, dashboard.timeValues,
      )).catch(() => null);
      if (!active) return;
      const topRows = parseKafkaLagRiskRows({ lag } as KafkaLagRiskResult);
      const dimensions = topRows.map((row) => ({ consumerGroup: row.consumerGroup, topic: row.topic, partition: row.partition }));
      if (!dimensions.length) {
        setRows([]);
        setHistory([]);
        setLoading(false);
        return;
      }
      const trendDimensions = dimensions.slice(0, LAG_TREND_SERIES_LIMIT);
      // 只为 Top 10 精确维度请求当前/最早 Offset，不再进行全量范围查询。
      const currentQuery = buildKafkaTopNExactQuery('kafka_consumergroup_current_offset_gauge', dimensions, true);
      const oldestQuery = buildKafkaTopNExactQuery('kafka_topic_partition_oldest_offset_gauge', dimensions, false);
      const historyQuery = buildKafkaTopNExactQuery('kafka_consumergroup_lag_gauge', trendDimensions, true);
      setHistoryLoading(true);
      const currentOffsetPromise = getInstanceInstantQuery(buildSearchParams(currentQuery, 'counts', dashboard.idValues, instanceIdKeys, dashboard.timeValues)).catch(() => null);
      const oldestOffsetPromise = getInstanceInstantQuery(buildSearchParams(oldestQuery, 'counts', dashboard.idValues, instanceIdKeys, dashboard.timeValues)).catch(() => null);
      const historyPromise = getInstanceQuery(buildSearchParams(historyQuery, 'counts', dashboard.idValues, instanceIdKeys, dashboard.timeValues, undefined, undefined, dashboard.currentInstanceInterval)).catch(() => null);
      const [currentOffset, oldestOffset] = await Promise.all([
        currentOffsetPromise,
        oldestOffsetPromise,
      ]);
      if (!active) return;
      setRows(parseKafkaLagRiskRows({ lag, currentOffset, oldestOffset } as KafkaLagRiskResult));
      setLoading(false);
      // 表格先显示；前 N 名曲线合并为一次 query_range 在后台补齐。
      const historyResult = await historyPromise;
      if (!active) return;
      setHistory(renderChart(historyResult?.data?.result || [], [{
        instance_id_values: dashboard.idValues,
        instance_name: '',
        instance_id_keys: instanceIdKeys,
        dimensions: [
          { name: 'consumergroup', description: '消费者组' },
          { name: 'topic', description: 'Topic' },
          { name: 'partition', description: '分区' },
        ],
        title: 'Lag',
      }]));
      setHistoryLoading(false);
    };
    load();

    return () => {
      active = false;
    };
    // 查询需随核心盘的实例、时间和自动刷新周期同步重载。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard.currentInstanceInterval, dashboard.isDashboardMode, dashboard.loadTick, getInstanceInstantQuery, getInstanceQuery, idValuesKey, instanceIdKeys, timeKey]);

  const trendRows = useMemo(
    () => rows.slice(0, LAG_TREND_SERIES_LIMIT),
    [rows],
  );

  const rankByDimension = useMemo(() => {
    const ranks = new Map<string, number>();
    trendRows.forEach((row, index) => {
      ranks.set(kafkaLagRowDimensionKey(row), index);
    });
    return ranks;
  }, [trendRows]);

  const seriesKeyToDimension = useMemo(
    () => mapChartSeriesToLagDimensions(history),
    [history],
  );

  const sortedValueKeys = useMemo(
    () => getSortedChartValueKeys(history),
    [history],
  );

  const trendLegends = useMemo(
    () => trendRows.map((row, index) => ({
      label: `#${index + 1}`,
      color: LAG_TREND_COLORS[index],
      primary: selectedKey
        ? kafkaLagRowDimensionKey(row) === selectedKey
        : index === 0,
    })),
    [selectedKey, trendRows],
  );

  const trendSeriesStyles = useMemo(() => {
    const styleForRank = (rank: number, dimensionKey: string) => {
      const isSelected = selectedKey != null && selectedKey === dimensionKey;
      const isDimmed = selectedKey != null && selectedKey !== dimensionKey;
      const isPrimary = selectedKey == null ? rank === 0 : isSelected;
      return {
        color: LAG_TREND_COLORS[rank] || LAG_TREND_COLORS[0],
        fillOpacity: isPrimary ? 0.08 : 0,
        strokeOpacity: isDimmed ? 0.22 : (isPrimary ? 1 : Math.max(0.45, 0.85 - rank * 0.08)),
        strokeWidth: isPrimary ? 2.8 : (isDimmed ? 1.2 : (rank < 3 ? 2.2 : 1.6)),
      };
    };

    // seriesStyles 下标必须与 ECharts 的 sorted valueKeys 对齐，再按维度映射回表格名次颜色。
    return sortedValueKeys.map((valueKey) => {
      const dimensionKey = seriesKeyToDimension.get(valueKey);
      if (!dimensionKey) {
        return {
          color: '#bfbfbf',
          fillOpacity: 0,
          strokeOpacity: 0.35,
          strokeWidth: 1.4,
        };
      }
      const rank = rankByDimension.get(dimensionKey) ?? 0;
      return styleForRank(rank, dimensionKey);
    });
  }, [rankByDimension, selectedKey, seriesKeyToDimension, sortedValueKeys]);

  const columns: TableColumnsType<KafkaLagRiskRow> = [
    {
      title: '#',
      key: 'rank',
      width: 52,
      render: (_value, _row, index) => (
        <span className={styles.riskRank}>
          {index < LAG_TREND_SERIES_LIMIT ? (
            <span
              className={styles.riskRankDot}
              style={{ background: LAG_TREND_COLORS[index] }}
              title={`趋势曲线 #${index + 1}`}
            />
          ) : (
            <span className={styles.riskRankDotPlaceholder} aria-hidden />
          )}
          <span className={styles.riskRankNum}>{index + 1}</span>
        </span>
      ),
    },
    { title: '消费者组', dataIndex: 'consumerGroup', key: 'consumerGroup', ellipsis: true },
    { title: 'Topic', dataIndex: 'topic', key: 'topic', ellipsis: true },
    { title: '分区', dataIndex: 'partition', key: 'partition', width: 100 },
    {
      title: '当前偏移',
      dataIndex: 'currentOffset',
      key: 'currentOffset',
      align: 'right',
      width: 120,
      render: formatCount,
    },
    {
      title: '最早偏移',
      dataIndex: 'oldestOffset',
      key: 'oldestOffset',
      align: 'right',
      width: 120,
      render: formatCount,
    },
    {
      title: 'Lag',
      dataIndex: 'lag',
      key: 'lag',
      align: 'right',
      width: 100,
      render: (lag: number) => <span className={styles.riskLag}>{formatCount(lag)}</span>,
    },
  ];

  return (
    <section className={`${styles.dashboardSection} ${styles.lagRankSection}`}>
      <div className={`${styles.sectionGrid} ${styles.riskLayout}`}>
        <DashboardPanel
          title="消费者组 Lag Top 10"
          subtitle="按消费者组、Topic、分区的当前 Lag 降序，定位最严重的消费积压。"
          guide={[{ label: 'Lag 排行', detail: '优先关注 Lag 持续升高的消费者组；点击前 5 名行可高亮下方对应趋势曲线。' }]}
          styles={styles}
          className={`${styles.span12} ${styles.riskTablePanel}`}
          bodyClassName={styles.riskTableWrap}
        >
          <Table<KafkaLagRiskRow>
            columns={columns}
            dataSource={rows}
            rowKey={(row) => kafkaLagRowDimensionKey(row)}
            loading={loading}
            pagination={false}
            size="small"
            locale={{ emptyText: '当前时间范围内没有消费者组 Lag 数据' }}
            onRow={(row, index) => {
              const dimensionKey = kafkaLagRowDimensionKey(row);
              const inTrend = (index ?? -1) < LAG_TREND_SERIES_LIMIT;
              return {
                onClick: () => {
                  if (!inTrend) return;
                  setSelectedKey((prev) => (prev === dimensionKey ? null : dimensionKey));
                },
                className: [
                  inTrend ? styles.riskRowClickable : '',
                  selectedKey === dimensionKey ? styles.riskRowSelected : '',
                ].filter(Boolean).join(' ') || undefined,
              };
            }}
          />
        </DashboardPanel>
        <TrendChartPanel
          title="Top Lag 历史趋势"
          subtitle={`表格前 ${LAG_TREND_SERIES_LIMIT} 名的 Lag 变化；点击表格行可高亮对应曲线。`}
          guide={[{ label: 'Lag 趋势', detail: '曲线颜色与表格前 5 名色点一致；点击行可聚焦单条曲线，再次点击取消。' }]}
          legends={trendLegends}
          seriesStyles={trendSeriesStyles}
          data={history}
          metric={{ id: 0, metric_group: 0, metric_object: 0, name: 'kafka_consumergroup_lag_gauge', type: 'number', display_name: 'Lag', dimensions: [], viewData: history } as any}
          unit="counts"
          loading={historyLoading}
          allowSelect
          onXRangeChange={dashboard.onXRangeChange}
          styles={styles}
          className={`${styles.span12} ${styles.riskTrendPanel}`}
          chartWrapClassName={styles.riskTrendChart}
        />
      </div>
    </section>
  );
}
