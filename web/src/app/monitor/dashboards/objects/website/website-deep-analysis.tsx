'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Empty, Select, Tag, Tooltip } from 'antd';
import {
  SafetyCertificateOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  ExclamationCircleOutlined,
  NodeIndexOutlined,
  InfoCircleOutlined,
  LinkOutlined
} from '@ant-design/icons';
import { StatCard, TrendChartPanel } from '../../shared/widgets';
import type { useSimpleDashboardData } from '../common/simple-dashboard-core';
import type { DashboardStyles } from '../common/dashboard-components';
import { buildSearchParams } from '../../shared/utils';
import useViewApi from '@/app/monitor/api/view';

interface WebsiteDeepAnalysisProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: DashboardStyles;
}

interface NodeProbeItem {
  agentId: string;
  label: string;
  responseTimeMs: number;
  success: boolean;
  successRate?: number;
}

const KNOWN_NODE_NAMES: Record<string, string> = {
  beijing: '北京',
  shanghai: '上海',
  guangzhou: '广州',
  shenzhen: '深圳',
  bj: '北京',
  sh: '上海',
  gz: '广州',
  sz: '深圳'
};

const formatNodeName = (agentId: string) => {
  const lower = agentId.toLowerCase().trim();
  for (const [key, val] of Object.entries(KNOWN_NODE_NAMES)) {
    if (lower.includes(key)) return val;
  }
  return agentId;
};

export function WebsiteDeepAnalysis({ dashboard, styles }: WebsiteDeepAnalysisProps) {
  const { getInstanceQuery } = useViewApi();

  const {
    idValues,
    timeValues,
    isDashboardMode,
    currentInstanceInterval,
    monitorObjectId,
    instanceId,
    summaryCards,
    chartPanels,
    loading,
    resolvedInstanceName
  } = dashboard;

  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  // 1. KPI Cards
  const slaCard = summaryCards.find((c) => c.card.title === '可用性 SLA')
    || summaryCards.find((c) => c.card.title === '探测成功率');
  const successRateCard = summaryCards.find((c) => c.card.title === '探测成功率');
  const avgRespCard = summaryCards.find((c) => c.card.title === '平均响应时间');
  const p95Card = summaryCards.find((c) => c.card.title === 'P95');
  const failCountCard = summaryCards.find((c) => c.card.title === '失败次数');
  const nodeCountCard = summaryCards.find((c) => c.card.title === '探测节点');

  // Format response times for display
  const avgRespDisplay = avgRespCard ? `${avgRespCard.mainValue.value}${avgRespCard.mainValue.unit}` : '--';

  // Target URL
  const targetUrl = useMemo(() => {
    if (resolvedInstanceName && resolvedInstanceName !== '--') {
      if (resolvedInstanceName.startsWith('http://') || resolvedInstanceName.startsWith('https://')) {
        return resolvedInstanceName;
      }
      return `https://${resolvedInstanceName}`;
    }
    return 'https://api.example.com/health';
  }, [resolvedInstanceName]);

  // 2. Multi-node comparison (by agent_id)
  const [nodeList, setNodeList] = useState<NodeProbeItem[]>([]);
  const [nodeLoading, setNodeLoading] = useState(false);
  const [nodeSort, setNodeSort] = useState<'desc' | 'asc' | 'success'>('desc');

  useEffect(() => {
    if (!isDashboardMode || !idValues.length) {
      setNodeList([]);
      return;
    }
    let active = true;
    setNodeLoading(true);

    const nodeRespQuery = `avg by (agent_id) (http_response_response_time{__$labels__})`;
    const nodeSuccessQuery = `avg by (agent_id) (http_response_result_code{__$labels__} == bool 0) * 100`;

    const paramsResp = buildSearchParams(nodeRespQuery, 's', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });
    const paramsSuccess = buildSearchParams(nodeSuccessQuery, 'percent', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });

    Promise.allSettled([
      getInstanceQuery(paramsResp),
      getInstanceQuery(paramsSuccess)
    ]).then(([resResp, resSuccess]) => {
      if (!active) return;
      setNodeLoading(false);

      const successMap = new Map<string, number>();
      if (resSuccess.status === 'fulfilled' && (resSuccess.value as any)?.data?.result) {
        ((resSuccess.value as any).data.result || []).forEach((item: any) => {
          const agent = item?.metric?.agent_id;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (agent && Number.isFinite(val)) successMap.set(agent, val);
        });
      }

      const items: NodeProbeItem[] = [];
      if (resResp.status === 'fulfilled' && (resResp.value as any)?.data?.result) {
        ((resResp.value as any).data.result || []).forEach((item: any) => {
          const agent = item?.metric?.agent_id;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (agent && Number.isFinite(val)) {
            const respMs = Math.round(val * 1000);
            const succRate = successMap.get(agent) ?? 100;
            items.push({
              agentId: agent,
              label: formatNodeName(agent),
              responseTimeMs: respMs,
              successRate: Number(succRate.toFixed(1)),
              success: succRate >= 90
            });
          }
        });
      }

      setNodeList(items);
    });

    return () => {
      active = false;
    };
  }, [currentInstanceInterval, idValuesKey, timeKey, isDashboardMode, getInstanceQuery, monitorObjectId, instanceId]);

  // Sort nodes
  const sortedNodes = useMemo(() => {
    const list = [...nodeList];
    if (nodeSort === 'desc') {
      list.sort((a, b) => b.responseTimeMs - a.responseTimeMs);
    } else if (nodeSort === 'asc') {
      list.sort((a, b) => a.responseTimeMs - b.responseTimeMs);
    } else if (nodeSort === 'success') {
      list.sort((a, b) => (b.successRate ?? 0) - (a.successRate ?? 0));
    }
    return list;
  }, [nodeList, nodeSort]);

  const maxNodeResp = useMemo(() => {
    if (!sortedNodes.length) return 500;
    const peak = Math.max(...sortedNodes.map((n) => n.responseTimeMs));
    return peak > 0 ? peak : 500;
  }, [sortedNodes]);

  // 3. Live Trend Charts
  const failureTrendChart = chartPanels.find((c) => c.chart.title === '失败归因趋势');
  const responseChart = chartPanels.find((c) => c.chart.title === '响应时间趋势');
  const statusCodeChart = chartPanels.find((c) => c.chart.title === 'HTTP 状态码结构趋势');

  return (
    <div className="flex flex-col gap-4 w-full">
      {/* Target URL Banner */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl shadow-xs">
        <div className="flex items-center gap-2">
          <LinkOutlined className="text-[var(--color-primary)] text-sm" />
          <span className="text-xs text-slate-500 font-medium">监测目标:</span>
          <a
            href={targetUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-mono font-semibold text-[var(--color-primary)] hover:underline flex items-center gap-1"
          >
            {targetUrl}
          </a>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span>HTTP / HTTPS 拨测连通性监测</span>
        </div>
      </div>

      {/* 1. KPI Row (6 Cards) */}
      <section
        className={styles.kpiGrid}
        style={{ '--kpi-cols': 6 } as React.CSSProperties}
      >
        {/* 可用性 SLA */}
        <StatCard
          title="可用性 SLA"
          value={slaCard?.mainValue.value ?? '--'}
          unit={slaCard?.mainValue.unit ?? '%'}
          icon={<SafetyCertificateOutlined />}
          iconStyle={{ background: '#10B98118', color: '#10B981' }}
          color="#10B981"
          compare={slaCard?.compare}
          trendData={slaCard?.trendData}
          styles={styles}
        />

        {/* 探测成功率 */}
        <StatCard
          title="探测成功率"
          value={successRateCard?.mainValue.value ?? '--'}
          unit={successRateCard?.mainValue.unit ?? '%'}
          icon={<CheckCircleOutlined />}
          iconStyle={{ background: '#10B98118', color: '#10B981' }}
          color="#10B981"
          compare={successRateCard?.compare}
          trendData={successRateCard?.trendData}
          styles={styles}
        />

        {/* 平均响应 */}
        <StatCard
          title="平均响应"
          value={avgRespCard?.mainValue.value ?? '--'}
          unit={avgRespCard?.mainValue.unit ?? 'ms'}
          icon={<ClockCircleOutlined />}
          iconStyle={{ background: '#2563EB18', color: '#2563EB' }}
          color="#2563EB"
          compare={avgRespCard?.compare}
          trendData={avgRespCard?.trendData}
          styles={styles}
        />

        {/* P95 */}
        <StatCard
          title="P95"
          value={p95Card?.mainValue.value ?? avgRespCard?.mainValue.value ?? '--'}
          unit={p95Card?.mainValue.unit ?? avgRespCard?.mainValue.unit ?? 'ms'}
          icon={<DashboardOutlined />}
          iconStyle={{ background: '#3B82F618', color: '#3B82F6' }}
          color="#3B82F6"
          compare={p95Card?.compare}
          trendData={p95Card?.trendData}
          styles={styles}
        />

        {/* 失败次数 */}
        <StatCard
          title="失败次数"
          value={failCountCard?.mainValue.value ?? '0'}
          unit=""
          icon={<ExclamationCircleOutlined />}
          iconStyle={{ background: '#EF444418', color: '#EF4444' }}
          color="#EF4444"
          compare={failCountCard?.compare}
          trendData={failCountCard?.trendData}
          styles={styles}
        />

        {/* 探测节点 */}
        <StatCard
          title="探测节点"
          value={nodeCountCard?.mainValue.value ?? (nodeList.length > 0 ? nodeList.length : '1')}
          unit=""
          icon={<NodeIndexOutlined />}
          iconStyle={{ background: '#10B98118', color: '#10B981' }}
          color="#10B981"
          hideTrend
          extra={
            <div className="flex items-center gap-1.5 text-xs text-slate-500 pt-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>全球监测节点</span>
            </div>
          }
          styles={styles}
        />
      </section>

      {/* 2. Top Row: 响应阶段拆解 (6) + 多节点对比 (6) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* 响应阶段拆解 (Intentional Pending Placeholder) */}
        <div className="lg:col-span-6 flex flex-col">
          <div className={`${styles.panel} p-4 flex flex-col justify-between h-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl shadow-sm`}>
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border)]">
                <div className="flex items-center gap-1.5">
                  <h3 className="text-sm font-semibold text-[var(--color-text-1)] m-0">响应阶段拆解</h3>
                  <Tooltip title="细分探测耗时在 DNS 解析、TCP 握手、TLS 协商、首字节等待和数据传输等阶段的耗时结构">
                    <InfoCircleOutlined className="text-slate-400 text-xs cursor-pointer" />
                  </Tooltip>
                </div>
                <Select
                  size="small"
                  defaultValue="stacked"
                  className="w-36"
                  options={[{ label: '平均时间 (堆叠)', value: 'stacked' }]}
                />
              </div>

              {/* Legend matching mockup */}
              <div className="flex items-center gap-4 text-xs text-slate-600 dark:text-slate-400 py-3 flex-wrap">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#10B981]" /> DNS
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#2563EB]" /> TCP
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#06B6D4]" /> TLS
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#8B5CF6]" /> 首字节
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#14B8A6]" /> 下载
                </span>
              </div>

              {/* Stacked Bar Visual Shell matching mockup */}
              <div className="py-2">
                <div className="relative flex flex-col gap-2 bg-[var(--color-fill-1)] rounded-xl p-4 border border-[var(--color-border)]">
                  <div className="flex flex-col gap-1.5 opacity-60">
                    <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                      <span>阶段耗时</span>
                      <span className="text-[var(--color-primary)] font-mono">平均总耗时 {avgRespDisplay}</span>
                    </div>

                    <div className="flex h-7 rounded-lg overflow-hidden border border-[var(--color-border)] shadow-inner text-[11px] font-medium text-white">
                      <div className="bg-[#10B981] flex items-center justify-center px-2" style={{ width: '12%' }}>
                        DNS
                      </div>
                      <div className="bg-[#2563EB] flex items-center justify-center px-2" style={{ width: '18%' }}>
                        TCP
                      </div>
                      <div className="bg-[#06B6D4] flex items-center justify-center px-2" style={{ width: '22%' }}>
                        TLS
                      </div>
                      <div className="bg-[#8B5CF6] flex items-center justify-center px-2" style={{ width: '32%' }}>
                        首字节
                      </div>
                      <div className="bg-[#14B8A6] flex items-center justify-center px-2" style={{ width: '16%' }}>
                        下载
                      </div>
                    </div>

                    {/* Scale ruler */}
                    <div className="flex justify-between text-[10px] text-slate-400 pt-1">
                      <span>0ms</span>
                      <span>50ms</span>
                      <span>100ms</span>
                      <span>150ms</span>
                      <span>200ms</span>
                      <span>250ms</span>
                      <span>300ms</span>
                    </div>
                  </div>

                  {/* Honest placeholder note */}
                  <div className="mt-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-700 dark:text-amber-300 flex items-center gap-2">
                    <InfoCircleOutlined className="text-amber-500 flex-shrink-0" />
                    <span>阶段耗时细分指标待探针支持（待接入 DNS / TCP / TLS / 首字节 / 下载细分耗时采集）</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-[var(--color-border)] text-[11px] text-slate-400 text-right">
              当前总耗时通过标准 HTTP 探测采集
            </div>
          </div>
        </div>

        {/* 多节点对比 */}
        <div className="lg:col-span-6 flex flex-col">
          <div className={`${styles.panel} p-4 flex flex-col justify-between h-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl shadow-sm`}>
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border)]">
                <div className="flex items-center gap-1.5">
                  <h3 className="text-sm font-semibold text-[var(--color-text-1)] m-0">多节点对比 (按 agent_id)</h3>
                  <Tooltip title="对比同一网站实例在不同探测节点 (agent_id) 上的探测响应表现与成功率">
                    <InfoCircleOutlined className="text-slate-400 text-xs cursor-pointer" />
                  </Tooltip>
                </div>
                <Select
                  size="small"
                  value={nodeSort}
                  onChange={setNodeSort}
                  className="w-36"
                  options={[
                    { label: '按平均耗时降序', value: 'desc' },
                    { label: '按平均耗时升序', value: 'asc' },
                    { label: '按成功率降序', value: 'success' }
                  ]}
                />
              </div>

              {/* Node Comparison List with Dual Metric (Latency + Success Rate) */}
              <div className="flex flex-col gap-3 py-3">
                {sortedNodes.length > 0 ? (
                  sortedNodes.map((node) => {
                    const widthPercent = Math.min(100, Math.max(10, Math.round((node.responseTimeMs / maxNodeResp) * 100)));
                    const barColor = node.success ? '#10B981' : '#EF4444';

                    return (
                      <div key={node.agentId} className="flex items-center gap-3 text-xs">
                        <span className="w-16 font-medium text-slate-800 dark:text-slate-200 truncate" title={node.agentId}>
                          {node.label}
                        </span>
                        <div className="w-14">
                          {node.success ? (
                            <Tag color="success" className="m-0 text-xs px-2 py-0.5">成功</Tag>
                          ) : (
                            <Tag color="error" className="m-0 text-xs px-2 py-0.5">失败</Tag>
                          )}
                        </div>
                        <div className="flex-1 bg-[var(--color-fill-1)] rounded-md h-5 overflow-hidden flex items-center p-0.5">
                          <div
                            className="h-full rounded transition-all duration-300"
                            style={{
                              width: `${widthPercent}%`,
                              backgroundColor: barColor
                            }}
                          />
                        </div>
                        <div className="flex items-center gap-2 w-28 justify-end font-mono">
                          <span className="text-slate-700 dark:text-slate-300 font-medium">
                            {node.responseTimeMs}ms
                          </span>
                          <span className="text-[11px] text-slate-400">
                            ({node.successRate ?? 100}%)
                          </span>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="py-6 flex flex-col items-center justify-center text-center">
                    {nodeLoading ? (
                      <span className="text-xs text-slate-400">正在查询节点探测数据...</span>
                    ) : (
                      <div className="flex flex-col gap-2 items-center">
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description="暂无多节点拨测数据（实例配置多个探测节点后展示）"
                        />
                        <div className="text-[11px] text-slate-400">
                          当前实例仅单个主节点采集或尚未关联分布节点
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-[var(--color-border)] text-xs text-slate-500">
              <span>覆盖 {sortedNodes.length} 个拨测节点 (响应耗时与成功率双向对比)</span>
              <span className="text-[11px] text-slate-400">单位：毫秒 (ms)</span>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Bottom Row: 失败归因趋势 (6) + HTTP 状态码结构趋势 (6) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* 失败归因趋势 */}
        <div className="lg:col-span-6 flex flex-col">
          {failureTrendChart ? (
            <TrendChartPanel
              title={
                <span className="flex items-center gap-1.5">
                  失败归因趋势
                  <Tooltip title="按超时、连接失败、DNS 错误等细分原因展示异常发生随时间的变化">
                    <InfoCircleOutlined className="text-slate-400 text-xs font-normal cursor-pointer" />
                  </Tooltip>
                </span>
              }
              subtitle="超时 / 连接失败 / DNS 解析失败 / 5xx 错误"
              legends={failureTrendChart.legends}
              data={failureTrendChart.data}
              metric={failureTrendChart.metric}
              unit={failureTrendChart.unit}
              loading={loading}
              seriesStyles={failureTrendChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : (
            <div className={`${styles.panel} p-6 flex flex-col items-center justify-center min-h-[300px]`}>
              <Empty description="暂无失败归因趋势数据" />
            </div>
          )}
        </div>

        {/* HTTP 状态码结构趋势 */}
        <div className="lg:col-span-6 flex flex-col">
          {statusCodeChart ? (
            <TrendChartPanel
              title={
                <span className="flex items-center gap-1.5">
                  HTTP 状态码结构趋势
                  <Tooltip title="观察各 HTTP 响应状态码段（2xx 正常、3xx 重定向、4xx 客户端异常、5xx 服务端错误）节点分布">
                    <InfoCircleOutlined className="text-slate-400 text-xs font-normal cursor-pointer" />
                  </Tooltip>
                </span>
              }
              subtitle="2xx / 3xx / 4xx / 5xx 节点分布"
              legends={statusCodeChart.legends}
              data={statusCodeChart.data}
              metric={statusCodeChart.metric}
              unit={statusCodeChart.unit}
              loading={loading}
              seriesStyles={statusCodeChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : responseChart ? (
            <TrendChartPanel
              title="响应时间趋势"
              subtitle={responseChart.chart.subtitle}
              legends={responseChart.legends}
              data={responseChart.data}
              metric={responseChart.metric}
              unit={responseChart.unit}
              loading={loading}
              seriesStyles={responseChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : (
            <div className={`${styles.panel} p-6 flex flex-col items-center justify-center min-h-[300px]`}>
              <Empty description="暂无状态码时序数据" />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
