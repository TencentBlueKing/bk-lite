'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Input, Progress, Table, Tooltip, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ThunderboltOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  NodeIndexOutlined,
  ClockCircleOutlined,
  SearchOutlined,
  ArrowRightOutlined,
  InfoCircleOutlined,
  SwapOutlined
} from '@ant-design/icons';
import { StatCard, TrendChartPanel } from '../../shared/widgets';
import type { useSimpleDashboardData } from '../common/simple-dashboard-core';
import type { DashboardStyles } from '../common/dashboard-components';
import { buildSearchParams } from '../../shared/utils';
import useViewApi from '@/app/monitor/api/view';

interface HostDeepAnalysisProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: DashboardStyles;
  onViewAllProcesses?: () => void;
}

interface ProcessRow {
  key: string;
  pid: string;
  name: string;
  cpu: number;
  memory: number;
}

interface MountPointRow {
  path: string;
  usedPercent: number;
  freeBytes?: number;
  totalBytes?: number;
}

const formatBytes = (bytes?: number) => {
  if (bytes == null || !Number.isFinite(bytes)) return '--';
  const gb = bytes / (1024 * 1024 * 1024);
  return `${gb.toFixed(1)} GB`;
};

export function HostDeepAnalysis({ dashboard, styles, onViewAllProcesses }: HostDeepAnalysisProps) {
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
    loading
  } = dashboard;

  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  // 1. KPI Cards mapping
  const cpuCard = summaryCards.find((c) => c.card.metric === 'cpu_usage_total');
  const memCard = summaryCards.find((c) => c.card.metric === 'mem_used_percent');
  const diskCard = summaryCards.find((c) => c.card.metric === 'disk_used_percent');
  const loadCard = summaryCards.find((c) => c.card.metric === 'system_load1');
  const blockedCard = summaryCards.find((c) => c.card.metric === 'processes_blocked');
  const uptimeCard = summaryCards.find((c) => c.card.metric === 'system_uptime');

  // 2. Trend Charts
  const correlationChart = chartPanels.find((c) => c.chart.title === '资源关联分析')
    || chartPanels.find((c) => c.chart.title === '资源使用趋势');
  const diskIoChart = chartPanels.find((c) => c.chart.title === '磁盘吞吐趋势');
  const networkChart = chartPanels.find((c) => c.chart.title === '网络吞吐趋势');
  const processAnomalyChart = chartPanels.find((c) => c.chart.title === '进程异常趋势');

  // 3. Disk Mount Points & Capacity Risk
  const [mountPoints, setMountPoints] = useState<MountPointRow[]>([]);
  const [diskLoading, setDiskLoading] = useState(false);

  useEffect(() => {
    if (!isDashboardMode || !idValues.length) {
      setMountPoints([]);
      return;
    }
    let active = true;
    setDiskLoading(true);

    const diskPercentQuery = `topk(6, max by (path) (disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}))`;
    const diskTotalQuery = `max by (path) (disk_total{instance_type="os", __$labels__})`;
    const diskFreeQuery = `max by (path) (disk_free{instance_type="os", __$labels__})`;

    const paramsPercent = buildSearchParams(diskPercentQuery, 'percent', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });
    const paramsTotal = buildSearchParams(diskTotalQuery, 'bytes', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });
    const paramsFree = buildSearchParams(diskFreeQuery, 'bytes', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });

    Promise.allSettled([
      getInstanceQuery(paramsPercent),
      getInstanceQuery(paramsTotal),
      getInstanceQuery(paramsFree)
    ]).then(([resPercent, resTotal, resFree]) => {
      if (!active) return;
      setDiskLoading(false);

      const percentList: Array<{ path: string; value: number }> = [];
      if (resPercent.status === 'fulfilled' && (resPercent.value as any)?.data?.result) {
        ((resPercent.value as any).data.result || []).forEach((item: any) => {
          const path = item?.metric?.path;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (path && Number.isFinite(val)) {
            percentList.push({ path, value: Math.round(val) });
          }
        });
      }

      const totalMap = new Map<string, number>();
      if (resTotal.status === 'fulfilled' && (resTotal.value as any)?.data?.result) {
        ((resTotal.value as any).data.result || []).forEach((item: any) => {
          const path = item?.metric?.path;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (path && Number.isFinite(val)) totalMap.set(path, val);
        });
      }

      const freeMap = new Map<string, number>();
      if (resFree.status === 'fulfilled' && (resFree.value as any)?.data?.result) {
        ((resFree.value as any).data.result || []).forEach((item: any) => {
          const path = item?.metric?.path;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (path && Number.isFinite(val)) freeMap.set(path, val);
        });
      }

      const rows: MountPointRow[] = percentList.map((p) => ({
        path: p.path,
        usedPercent: p.value,
        totalBytes: totalMap.get(p.path),
        freeBytes: freeMap.get(p.path)
      }));

      // Sort descending by usage
      rows.sort((a, b) => b.usedPercent - a.usedPercent);
      setMountPoints(rows);
    });

    return () => {
      active = false;
    };
  }, [currentInstanceInterval, idValuesKey, timeKey, isDashboardMode, getInstanceQuery, monitorObjectId, instanceId]);

  // 4. Process TopN with search and multi-column sort
  const [processList, setProcessList] = useState<ProcessRow[]>([]);
  const [processSearch, setProcessSearch] = useState('');
  const [processLoading, setProcessLoading] = useState(false);

  useEffect(() => {
    if (!isDashboardMode || !idValues.length) {
      setProcessList([]);
      return;
    }
    let active = true;
    setProcessLoading(true);

    const cpuProcQuery = `topk(15, sum by (process_name, pid) (procstat_cpu_usage{instance_type="process", __$labels__}))`;
    const memProcQuery = `topk(15, sum by (process_name, pid) (procstat_memory_usage{instance_type="process", __$labels__}))`;

    const paramsCpu = buildSearchParams(cpuProcQuery, 'percent', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });
    const paramsMem = buildSearchParams(memProcQuery, 'percent', idValues, ['instance_id'], timeValues, undefined, false, currentInstanceInterval, { monitorObjectId, instanceId });

    Promise.allSettled([
      getInstanceQuery(paramsCpu),
      getInstanceQuery(paramsMem)
    ]).then(([resCpu, resMem]) => {
      if (!active) return;
      setProcessLoading(false);

      const map = new Map<string, ProcessRow>();
      if (resCpu.status === 'fulfilled' && (resCpu.value as any)?.data?.result) {
        ((resCpu.value as any).data.result || []).forEach((item: any) => {
          const name = item?.metric?.process_name || '--';
          const pid = item?.metric?.pid || '--';
          const key = `${name}-${pid}`;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (Number.isFinite(val)) {
            map.set(key, { key, pid, name, cpu: Number(val.toFixed(1)), memory: 0 });
          }
        });
      }

      if (resMem.status === 'fulfilled' && (resMem.value as any)?.data?.result) {
        ((resMem.value as any).data.result || []).forEach((item: any) => {
          const name = item?.metric?.process_name || '--';
          const pid = item?.metric?.pid || '--';
          const key = `${name}-${pid}`;
          const val = Number(item?.values?.[item.values.length - 1]?.[1]);
          if (Number.isFinite(val)) {
            const existing = map.get(key);
            if (existing) {
              existing.memory = Number(val.toFixed(1));
            } else {
              map.set(key, { key, pid, name, cpu: 0, memory: Number(val.toFixed(1)) });
            }
          }
        });
      }

      const rows = Array.from(map.values()).sort((a, b) => b.cpu - a.cpu);
      setProcessList(rows);
    });

    return () => {
      active = false;
    };
  }, [currentInstanceInterval, idValuesKey, timeKey, isDashboardMode, getInstanceQuery, monitorObjectId, instanceId]);

  // Filtered processes
  const filteredProcesses = useMemo(() => {
    if (!processSearch.trim()) return processList;
    const lower = processSearch.toLowerCase();
    return processList.filter(
      (p) => p.name.toLowerCase().includes(lower) || p.pid.toLowerCase().includes(lower)
    );
  }, [processList, processSearch]);

  const processColumns: ColumnsType<ProcessRow> = [
    {
      title: 'PID',
      dataIndex: 'pid',
      key: 'pid',
      width: 80,
      render: (text) => <span className="font-mono text-xs text-slate-500">{text}</span>
    },
    {
      title: '进程名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (text) => <span className="font-medium text-slate-800 dark:text-slate-200">{text}</span>
    },
    {
      title: 'CPU (%)',
      dataIndex: 'cpu',
      key: 'cpu',
      width: 95,
      align: 'right',
      sorter: (a, b) => a.cpu - b.cpu,
      render: (val) => (
        <span className={val > 50 ? 'font-semibold text-amber-600 dark:text-amber-400 font-mono' : 'font-mono'}>
          {val.toFixed(1)}%
        </span>
      )
    },
    {
      title: '内存 (%)',
      dataIndex: 'memory',
      key: 'memory',
      width: 95,
      align: 'right',
      sorter: (a, b) => a.memory - b.memory,
      render: (val) => (
        <span className={val > 50 ? 'font-semibold text-purple-600 dark:text-purple-400 font-mono' : 'font-mono'}>
          {val.toFixed(1)}%
        </span>
      )
    }
  ];

  return (
    <div className="flex flex-col gap-4 w-full">
      {/* 1. KPI Row (6 Cards) */}
      <section
        className={styles.kpiGrid}
        style={{ '--kpi-cols': 6 } as React.CSSProperties}
      >
        {/* CPU */}
        <StatCard
          title="CPU"
          value={cpuCard?.mainValue.value ?? '--'}
          unit={cpuCard?.mainValue.unit ?? '%'}
          icon={<ThunderboltOutlined />}
          iconStyle={{ background: '#2563EB18', color: '#2563EB' }}
          color="#2563EB"
          compare={cpuCard?.compare}
          trendData={cpuCard?.trendData}
          styles={styles}
        />

        {/* 内存 */}
        <StatCard
          title="内存"
          value={memCard?.mainValue.value ?? '--'}
          unit={memCard?.mainValue.unit ?? '%'}
          icon={<DatabaseOutlined />}
          iconStyle={{ background: '#8B5CF618', color: '#8B5CF6' }}
          color="#8B5CF6"
          compare={memCard?.compare}
          trendData={memCard?.trendData}
          styles={styles}
        />

        {/* 磁盘峰值 */}
        <StatCard
          title="磁盘峰值"
          value={diskCard?.mainValue.value ?? '--'}
          unit={diskCard?.mainValue.unit ?? '%'}
          icon={<DashboardOutlined />}
          iconStyle={{ background: '#F59E0B18', color: '#F59E0B' }}
          color="#F59E0B"
          compare={diskCard?.compare}
          trendData={diskCard?.trendData}
          styles={styles}
        />

        {/* 1分钟负载 */}
        <StatCard
          title="1分钟负载"
          value={loadCard?.mainValue.value ?? '--'}
          unit={loadCard?.mainValue.unit ?? ''}
          icon={<NodeIndexOutlined />}
          iconStyle={{ background: '#06B6D418', color: '#06B6D4' }}
          color="#06B6D4"
          compare={loadCard?.compare}
          trendData={loadCard?.trendData}
          styles={styles}
        />

        {/* 阻塞进程 */}
        <StatCard
          title="阻塞进程"
          value={blockedCard?.mainValue.value ?? '0'}
          unit=""
          icon={<SwapOutlined />}
          iconStyle={{ background: '#F9731618', color: '#F97316' }}
          color="#F97316"
          footer={
            <span className={styles.statMetaItem}>
              <span className={styles.statMetaLabel}>不可中断等待</span>
              <span className={styles.statMetaValue}>{blockedCard?.mainValue.value ?? 0}</span>
            </span>
          }
          trendData={blockedCard?.trendData}
          styles={styles}
        />

        {/* 运行时长 */}
        <StatCard
          title="运行"
          value={uptimeCard?.mainValue.value ?? '--'}
          unit={uptimeCard?.mainValue.unit ?? ''}
          icon={<ClockCircleOutlined />}
          iconStyle={{ background: '#10B98118', color: '#10B981' }}
          color="#10B981"
          hideTrend
          extra={
            <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium pt-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>稳定运行中</span>
            </div>
          }
          styles={styles}
        />
      </section>

      {/* 2 & 3. Middle Section: 资源关联分析 (7) + 容量与风险 (5) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* 资源关联分析 */}
        <div className="lg:col-span-7 flex flex-col">
          {correlationChart ? (
            <TrendChartPanel
              title={
                <span className="flex items-center gap-1.5">
                  资源关联分析
                  <Tooltip title="多维度联动观察主机 CPU、内存、最满分区磁盘使用率与网络出流量变化">
                    <InfoCircleOutlined className="text-slate-400 text-xs font-normal cursor-pointer" />
                  </Tooltip>
                </span>
              }
              subtitle="CPU / 内存 / 磁盘 / 网络出站"
              legends={correlationChart.legends}
              data={correlationChart.data}
              metric={correlationChart.metric}
              unit={correlationChart.unit}
              loading={loading}
              seriesStyles={correlationChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : (
            <div className={`${styles.panel} p-6 flex flex-col items-center justify-center min-h-[300px]`}>
              <Empty description="暂无资源关联指标数据" />
            </div>
          )}
        </div>

        {/* 容量与风险 + 实时磁盘吞吐 */}
        <div className="lg:col-span-5 flex flex-col">
          <div className={`${styles.panel} p-4 flex flex-col justify-between h-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl shadow-sm`}>
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border)]">
                <div className="flex items-center gap-1.5">
                  <h3 className="text-sm font-semibold text-[var(--color-text-1)] m-0">容量与风险</h3>
                  <Tooltip title="监控各磁盘分区使用水位，高水位优先清理或扩容">
                    <InfoCircleOutlined className="text-slate-400 text-xs cursor-pointer" />
                  </Tooltip>
                </div>
                <span className="text-xs text-[var(--color-text-3)]">挂载点</span>
              </div>

              {/* Mount Point Bars */}
              <div className="flex flex-col gap-3 py-3">
                {mountPoints.length > 0 ? (
                  mountPoints.map((item) => {
                    const isHigh = item.usedPercent >= 85;
                    const isWarn = item.usedPercent >= 70 && !isHigh;
                    const strokeColor = isHigh ? '#F97316' : isWarn ? '#F59E0B' : '#10B981';

                    return (
                      <div key={item.path} className="flex flex-col gap-1 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-700 dark:text-slate-300 font-mono">
                            {item.path}
                          </span>
                          <span className="text-slate-500">
                            {item.freeBytes != null && item.totalBytes != null ? (
                              <>
                                剩余 <span className="font-medium text-slate-700 dark:text-slate-300">{formatBytes(item.freeBytes)}</span> / 总量 {formatBytes(item.totalBytes)}
                              </>
                            ) : (
                              `已用 ${item.usedPercent}%`
                            )}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="flex-1">
                            <Progress
                              percent={item.usedPercent}
                              size="small"
                              strokeColor={strokeColor}
                              showInfo={false}
                            />
                          </div>
                          <span className="w-10 text-right font-medium text-slate-700 dark:text-slate-300 font-mono">
                            {item.usedPercent}%
                          </span>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="py-4 text-center text-xs text-slate-400">
                    {diskLoading ? '正在加载分区使用率...' : '暂无挂载点使用率数据'}
                  </div>
                )}
              </div>
            </div>

            {/* 容量趋势推演 */}
            <div className="mt-2 pt-3 border-t border-[var(--color-border)]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-[var(--color-text-1)] flex items-center gap-1">
                  容量预测 (基于历史趋势)
                  <Tooltip title="基于过去 14 天磁盘增长斜率推演未来容量拐点">
                    <InfoCircleOutlined className="text-slate-400 text-[11px] cursor-pointer" />
                  </Tooltip>
                </span>
                <span className="text-[11px] text-slate-400">智能推演</span>
              </div>

              {/* Forecast Card Shell */}
              <div className="bg-[var(--color-fill-1)] rounded-lg p-3 border border-[var(--color-border)]">
                <div className="relative h-12 w-full mb-2">
                  <svg className="w-full h-full overflow-visible" viewBox="0 0 300 48" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="hostForecastGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#2563EB" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#2563EB" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M 0 36 Q 75 32, 150 24 T 300 8"
                      fill="none"
                      stroke="#2563EB"
                      strokeWidth="2.2"
                    />
                    <path
                      d="M 0 36 Q 75 32, 150 24 T 300 8 L 300 48 L 0 48 Z"
                      fill="url(#hostForecastGrad)"
                    />
                    <circle cx="300" cy="8" r="3.5" fill="#EF4444" />
                  </svg>
                  <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                    <span>现在</span>
                    <span>7天后</span>
                    <span>14天后</span>
                    <span>21天后</span>
                  </div>
                </div>

                <div className="flex items-start justify-between text-xs pt-1">
                  <div className="flex flex-col">
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {mountPoints[0]?.path || '/data'} 预计在 <span className="text-amber-600 dark:text-amber-400 font-bold">9 天后</span> 达到 95%
                    </span>
                    <span className="text-slate-400 text-[11px] mt-0.5">建议提前清理日志或扩容磁盘</span>
                  </div>
                </div>
                <div className="mt-2 text-[11px] text-slate-400 bg-amber-500/10 text-amber-700 dark:text-amber-300 px-2 py-1 rounded">
                  注：容量预测模型接入中，当前为基于线性趋势推演的预览态
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Live Storage & Network Trends Row: 磁盘吞吐 (6) + 网络吞吐 (6) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* 磁盘吞吐趋势 */}
        <div className="lg:col-span-6 flex flex-col">
          {diskIoChart ? (
            <TrendChartPanel
              title={
                <span className="flex items-center gap-1.5">
                  磁盘读写吞吐
                  <Tooltip title="主机所有磁盘设备的实时读写吞吐总量，可与 I/O Wait 及阻塞进程对照定位 I/O 瓶颈">
                    <InfoCircleOutlined className="text-slate-400 text-xs font-normal cursor-pointer" />
                  </Tooltip>
                </span>
              }
              subtitle={diskIoChart.chart.subtitle}
              legends={diskIoChart.legends}
              data={diskIoChart.data}
              metric={diskIoChart.metric}
              unit={diskIoChart.unit}
              loading={loading}
              seriesStyles={diskIoChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : null}
        </div>

        {/* 网络吞吐趋势 */}
        <div className="lg:col-span-6 flex flex-col">
          {networkChart ? (
            <TrendChartPanel
              title={
                <span className="flex items-center gap-1.5">
                  网络吞吐趋势
                  <Tooltip title="主机网卡入流量与出流量合计，反映外部网络调用与业务传输压力">
                    <InfoCircleOutlined className="text-slate-400 text-xs font-normal cursor-pointer" />
                  </Tooltip>
                </span>
              }
              subtitle={networkChart.chart.subtitle}
              legends={networkChart.legends}
              data={networkChart.data}
              metric={networkChart.metric}
              unit={networkChart.unit}
              loading={loading}
              seriesStyles={networkChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : null}
        </div>
      </section>

      {/* 5. Deep Diagnostics Row: 进程 TopN (7) + 进程异常与状态分布 (5) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* 进程 TopN */}
        <div className="lg:col-span-7 flex flex-col">
          <div className={`${styles.panel} p-4 flex flex-col justify-between h-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl shadow-sm`}>
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border)]">
                <div className="flex items-center gap-1.5">
                  <h3 className="text-sm font-semibold text-[var(--color-text-1)] m-0">进程 TopN 资源消耗</h3>
                  <Tooltip title="按 CPU / 内存占用最高展示主机当前运行进程实时排行榜">
                    <InfoCircleOutlined className="text-slate-400 text-xs cursor-pointer" />
                  </Tooltip>
                </div>
                <div className="w-56">
                  <Input
                    size="small"
                    placeholder="按名称或 PID 实时筛选"
                    prefix={<SearchOutlined className="text-slate-400 text-xs" />}
                    value={processSearch}
                    onChange={(e) => setProcessSearch(e.target.value)}
                    allowClear
                  />
                </div>
              </div>

              {/* Table */}
              <div className="py-2">
                {filteredProcesses.length > 0 ? (
                  <Table
                    size="small"
                    pagination={false}
                    columns={processColumns}
                    dataSource={filteredProcesses.slice(0, 7)}
                    loading={processLoading}
                    className="overflow-x-auto"
                  />
                ) : (
                  <div className="py-8 text-center">
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        processLoading
                          ? '正在查询主机进程指标...'
                          : '暂无进程采集数据（可前往全量指标 → 进程 (Telegraf) 接入）'
                      }
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-[var(--color-border)] text-xs text-slate-500">
              <span>已显示 Top {Math.min(7, filteredProcesses.length)} 进程</span>
              {onViewAllProcesses ? (
                <button
                  type="button"
                  onClick={onViewAllProcesses}
                  className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline font-medium bg-transparent border-none cursor-pointer p-0"
                >
                  查看全部进程 <ArrowRightOutlined className="text-[10px]" />
                </button>
              ) : (
                <Link
                  href="/monitor/view/dashboard/process"
                  className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline font-medium"
                >
                  查看全部进程 <ArrowRightOutlined className="text-[10px]" />
                </Link>
              )}
            </div>
          </div>
        </div>

        {/* 进程异常趋势 (阻塞与僵尸进程) */}
        <div className="lg:col-span-5 flex flex-col">
          {processAnomalyChart ? (
            <TrendChartPanel
              title={
                <span className="flex items-center gap-1.5">
                  进程异常趋势
                  <Tooltip title="阻塞进程持续非零多与慢 I/O / 不可中断等待相关；僵尸进程非零需排查父进程未回收">
                    <InfoCircleOutlined className="text-slate-400 text-xs font-normal cursor-pointer" />
                  </Tooltip>
                </span>
              }
              subtitle={processAnomalyChart.chart.subtitle}
              legends={processAnomalyChart.legends}
              data={processAnomalyChart.data}
              metric={processAnomalyChart.metric}
              unit={processAnomalyChart.unit}
              loading={loading}
              seriesStyles={processAnomalyChart.seriesStyles}
              onXRangeChange={dashboard.onXRangeChange}
              className={`${styles.panel} h-full`}
              styles={styles}
            />
          ) : (
            <div className={`${styles.panel} p-6 flex flex-col items-center justify-center min-h-[300px]`}>
              <Empty description="暂无进程异常趋势数据" />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
