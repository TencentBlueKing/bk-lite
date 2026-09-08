'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Input, Pagination, Spin } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import useViewApi from '@/app/monitor/api/view';
import ChartEmptyState from '@/components/chart-empty-state';
import { DashboardPanel } from '../../shared/widgets';
import { buildSearchParams, formatMetricValue } from '../../shared/utils';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import type { FlowProtocol } from './constants';
import { buildConversationTopQuery } from './queries';
import { mapConversationPageItems, type FlowConversationPage, type FlowConversationRow } from './parse-conversation-rows';
import { formatProtocolShortName } from './protocol-labels';
import { resolveFlowRankClass } from './rank-class';

interface FlowConversationTableProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  protocol: FlowProtocol;
  instanceType: string;
  styles: Record<string, string>;
}

const DEFAULT_PAGE_SIZE = 10;
const SEARCH_DEBOUNCE_MS = 300;

const CONVERSATION_GUIDE = [{
  label: 'Top 会话',
  detail: '所选时间窗内的全量会话，按源/目的地址、端口与协议聚合，并按平均流量速率排序。可按源或目的地址关键字过滤后分页查看。',
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
  const { queryFlowConversations } = useViewApi();
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [count, setCount] = useState(0);
  const [rows, setRows] = useState<FlowConversationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const conversationQuery = useMemo(
    () => buildConversationTopQuery(instanceType, protocol),
    [instanceType, protocol],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const nextKeyword = keywordInput.trim();
      if (nextKeyword === keyword) return;
      setKeyword(nextKeyword);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [keyword, keywordInput]);

  useEffect(() => {
    if (!dashboard.isDashboardMode || !instanceType || !dashboard.idValues.length) {
      setRows([]);
      setCount(0);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);

    const load = async () => {
      const result = await queryFlowConversations({
        ...buildSearchParams(
          conversationQuery,
          'byteps',
          dashboard.idValues,
          ['instance_id'],
          dashboard.timeValues,
          undefined,
          false,
          dashboard.currentInstanceInterval,
          { monitorObjectId: dashboard.monitorObjectId, instanceId: dashboard.instanceId },
        ),
        keyword,
        page,
        page_size: pageSize,
      }).catch(() => null) as FlowConversationPage | null;

      if (!active) return;
      const nextCount = Number(result?.count) || 0;
      setRows(mapConversationPageItems(result?.items));
      setCount(nextCount);
      const maxPage = Math.max(1, Math.ceil(nextCount / pageSize) || 1);
      if (page > maxPage) setPage(maxPage);
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
    dashboard.instanceId,
    dashboard.isDashboardMode,
    dashboard.loadTick,
    dashboard.monitorObjectId,
    dashboard.timeValues,
    instanceType,
    keyword,
    page,
    pageSize,
    queryFlowConversations,
  ]);

  const peakRate = useMemo(
    () => (rows.length ? Math.max(...rows.map((row) => row.bytesRate)) : 0),
    [rows],
  );

  const emptyDescription = keyword
    ? '未找到匹配的 Flow 会话'
    : '所选时间窗内无 Flow 会话数据';

  return (
    <DashboardPanel
      title="Top 会话"
      subtitle="全量会话 · 按源/目的地址、端口与协议聚合，支持搜索与分页"
      guide={CONVERSATION_GUIDE}
      className={`${styles.span8} ${styles.flowConversationPanel}`}
      bodyClassName={styles.flowConversationBody}
      styles={styles}
    >
      <Spin spinning={loading}>
        <div className="mb-2.5 flex items-center justify-between gap-2">
          <Input
            allowClear
            size="small"
            prefix={<SearchOutlined className="text-gray-400" />}
            value={keywordInput}
            placeholder="搜索源/目的地址"
            onChange={(event) => setKeywordInput(event.target.value)}
            className="w-60"
          />
        </div>
        {!loading && rows.length === 0 ? (
          <div className={styles.flowConversationEmpty}>
            <ChartEmptyState description={emptyDescription} compact />
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
                {rows.map((row) => {
                  const rank = row.rank ?? 0;
                  const share = peakRate > 0 ? (row.bytesRate / peakRate) * 100 : 0;
                  return (
                    <tr key={row.rowKey} className={resolveFlowRankClass(Math.max(rank - 1, 0), styles)}>
                      <td className={styles.flowCellRank}>
                        <span className={styles.flowProtocolRankMark}>{rank || '--'}</span>
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
        {count > 0 ? (
          <div className="mt-3 flex items-center justify-end">
            <Pagination
              size="small"
              current={page}
              pageSize={pageSize}
              total={count}
              showSizeChanger
              pageSizeOptions={['10', '20', '50']}
              showTotal={(total) => `共 ${total} 条会话`}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPageSize === pageSize ? nextPage : 1);
                setPageSize(nextPageSize);
              }}
            />
          </div>
        ) : null}
      </Spin>
    </DashboardPanel>
  );
}
