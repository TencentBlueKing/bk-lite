'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Button, Empty, Segmented, Skeleton, Tag } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import CustomTable from '@/components/custom-table';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import {
  DashboardSuccessRateCompare,
  DashboardTrend,
  JobRecord,
  JobRecordSource,
  JobRecordStatus,
} from '@/app/job/types';

type OverviewDays = 7 | 30;

interface OverviewData {
  trend: DashboardTrend[];
  successRateCompare: DashboardSuccessRateCompare | null;
}

const OVERVIEW_DAYS_OPTIONS: Array<{ label: string; value: OverviewDays }> = [
  { label: '7', value: 7 },
  { label: '30', value: 30 },
];

const SUCCESS_COLOR = '#19b87a';
const FAILURE_COLOR = '#ff5a52';
const SUCCESS_FILL = 'rgba(25, 184, 122, 0.12)';

const formatPercent = (value: number | undefined) => `${(value || 0).toFixed(1)}%`;

const formatDelta = (value: number | undefined) => {
  const safeValue = value || 0;
  const sign = safeValue > 0 ? '+' : '';
  return `${sign}${safeValue.toFixed(1)}%`;
};

const formatAxisDate = (date: string) => {
  const [year, month, day] = date.split('-');
  if (!year || !month || !day) return date;
  return `${month}-${day}`;
};

const getVisibleXAxisIndices = (length: number) => {
  if (length <= 7) return Array.from({ length }, (_, index) => index);

  const step = length <= 14 ? 2 : length <= 21 ? 3 : 5;
  const indices = new Set<number>([0, length - 1]);

  for (let index = 0; index < length; index += step) {
    indices.add(index);
  }

  return Array.from(indices).sort((a, b) => a - b);
};

const getChartPoint = (
  value: number,
  index: number,
  valuesLength: number,
  width: number,
  height: number,
  chartLeft: number,
  chartRight: number,
  chartTop: number,
  chartBottom: number,
  maxValue: number
) => {
  const drawableWidth = width - chartLeft - chartRight;
  const drawableHeight = height - chartTop - chartBottom;
  const x = valuesLength === 1 ? width / 2 : chartLeft + (index * drawableWidth) / (valuesLength - 1);
  const y = chartTop + drawableHeight - (maxValue === 0 ? 0 : (value / maxValue) * drawableHeight);

  return { x, y };
};

const buildSmoothLinePath = (
  values: number[],
  width: number,
  height: number,
  chartLeft: number,
  chartRight: number,
  chartTop: number,
  chartBottom: number,
  maxValue: number
) => {
  if (!values.length) return '';

  const points = values.map((value, index) =>
    getChartPoint(
      value,
      index,
      values.length,
      width,
      height,
      chartLeft,
      chartRight,
      chartTop,
      chartBottom,
      maxValue
    )
  );

  if (points.length === 1) {
    return `M ${points[0].x} ${points[0].y}`;
  }

  const commands = [`M ${points[0].x} ${points[0].y}`];

  for (let index = 0; index < points.length - 1; index += 1) {
    const previousPoint = points[index - 1] || points[index];
    const currentPoint = points[index];
    const nextPoint = points[index + 1];
    const afterNextPoint = points[index + 2] || nextPoint;

    const controlPoint1X = currentPoint.x + (nextPoint.x - previousPoint.x) / 6;
    const controlPoint1Y = currentPoint.y + (nextPoint.y - previousPoint.y) / 6;
    const controlPoint2X = nextPoint.x - (afterNextPoint.x - currentPoint.x) / 6;
    const controlPoint2Y = nextPoint.y - (afterNextPoint.y - currentPoint.y) / 6;

    commands.push(
      `C ${controlPoint1X} ${controlPoint1Y}, ${controlPoint2X} ${controlPoint2Y}, ${nextPoint.x} ${nextPoint.y}`
    );
  }

  return commands.join(' ');
};

const buildAreaPath = (
  values: number[],
  width: number,
  height: number,
  chartLeft: number,
  chartRight: number,
  chartTop: number,
  chartBottom: number,
  maxValue: number
) => {
  if (!values.length) return '';

  const linePoints = values.map((value, index) =>
    getChartPoint(
      value,
      index,
      values.length,
      width,
      height,
      chartLeft,
      chartRight,
      chartTop,
      chartBottom,
      maxValue
    )
  );

  const baselineY = height - chartBottom;
  const firstPoint = linePoints[0];
  const lastPoint = linePoints[linePoints.length - 1];
  const smoothLinePath = buildSmoothLinePath(
    values,
    width,
    height,
    chartLeft,
    chartRight,
    chartTop,
    chartBottom,
    maxValue
  );

  return `${smoothLinePath} L ${lastPoint.x} ${baselineY} L ${firstPoint.x} ${baselineY} Z`;
};

const TrendMiniChart = ({ data, t }: { data: DashboardTrend[]; t: (key: string) => string }) => {
  const width = 960;
  const height = 220;
  const chartLeft = 18;
  const chartRight = 18;
  const chartTop = 22;
  const chartBottom = 30;
  const yAxisValues = [0, 1, 2, 3];
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const maxValue = Math.max(
    ...data.flatMap((item) => [item.execution_count, item.success_count, item.failed_count]),
    0
  );
  const visibleXAxisIndices = useMemo(() => getVisibleXAxisIndices(data.length), [data.length]);
  const hoveredData = hoveredIndex !== null ? data[hoveredIndex] : null;
  const hoveredSuccessPoint = hoveredData
    ? getChartPoint(
      hoveredData.success_count,
      hoveredIndex,
      data.length,
      width,
      height,
      chartLeft,
      chartRight,
      chartTop,
      chartBottom,
      maxValue
    )
    : null;
  const hoveredFailurePoint = hoveredData
    ? getChartPoint(
      hoveredData.failed_count,
      hoveredIndex,
      data.length,
      width,
      height,
      chartLeft,
      chartRight,
      chartTop,
      chartBottom,
      maxValue
    )
    : null;
  const hoveredX = hoveredSuccessPoint?.x;
  const tooltipWidth = 164;
  const tooltipHeight = 102;
  const tooltipX = hoveredX
    ? Math.max(chartLeft, Math.min(hoveredX - tooltipWidth / 2, width - chartRight - tooltipWidth))
    : 0;
  const tooltipY = 10;

  if (!data.length) {
    return (
      <div className="h-65 flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
      </div>
    );
  }

  return (
    <div className="w-full relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-55 overflow-visible">
        {yAxisValues.map((step) => {
          const y = chartTop + ((height - chartTop - chartBottom) / (yAxisValues.length - 1)) * step;
          return (
            <g key={step}>
              <line
                x1={chartLeft}
                y1={y}
                x2={width - chartRight}
                y2={y}
                stroke="#e9f1f8"
                strokeDasharray="4 4"
              />
            </g>
          );
        })}
        <path
          d={buildAreaPath(
            data.map((item) => item.success_count),
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          )}
          fill={SUCCESS_FILL}
        />
        <path
          d={buildSmoothLinePath(
            data.map((item) => item.success_count),
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          )}
          fill="none"
          stroke={SUCCESS_COLOR}
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={buildSmoothLinePath(
            data.map((item) => item.failed_count),
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          )}
          fill="none"
          stroke={FAILURE_COLOR}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="10 8"
        />
        {hoveredData && hoveredX ? (
          <g pointerEvents="none">
            <line
              x1={hoveredX}
              y1={chartTop}
              x2={hoveredX}
              y2={height - chartBottom}
              stroke="#b8cde2"
              strokeDasharray="4 4"
            />
            {hoveredSuccessPoint ? (
              <g>
                <circle cx={hoveredSuccessPoint.x} cy={hoveredSuccessPoint.y} r="5" fill="#fff" stroke={SUCCESS_COLOR} strokeWidth="2" />
              </g>
            ) : null}
            {hoveredFailurePoint ? (
              <g>
                <circle cx={hoveredFailurePoint.x} cy={hoveredFailurePoint.y} r="5" fill="#fff" stroke={FAILURE_COLOR} strokeWidth="2" />
              </g>
            ) : null}
            <g>
              <rect
                x={tooltipX}
                y={tooltipY}
                width={tooltipWidth}
                height={tooltipHeight}
                rx="12"
                fill="rgba(18, 26, 38, 0.92)"
              />
              <text x={tooltipX + 14} y={tooltipY + 22} fontSize="12" fontWeight="600" fill="#ffffff">
                {formatAxisDate(hoveredData.date)}
              </text>
              {[
                { key: 'success', color: SUCCESS_COLOR, label: t('job.successCount'), value: hoveredData.success_count },
                { key: 'failed', color: FAILURE_COLOR, label: t('job.failedCount'), value: hoveredData.failed_count },
                { key: 'execution', color: '#8fa6bf', label: t('job.executionCount'), value: hoveredData.execution_count },
              ].map((item, index) => (
                <g key={item.key}>
                  <circle cx={tooltipX + 18} cy={tooltipY + 40 + index * 20} r="4" fill={item.color} />
                  <text x={tooltipX + 30} y={tooltipY + 44 + index * 20} fontSize="11" fill="#dce7f2">
                    {item.label}: {item.value}
                  </text>
                </g>
              ))}
            </g>
          </g>
        ) : null}
        {data.map((item, index) => {
          const currentPoint = getChartPoint(
            item.success_count,
            index,
            data.length,
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          );
          const previousPoint =
            index > 0
              ? getChartPoint(
                data[index - 1].success_count,
                index - 1,
                data.length,
                width,
                height,
                chartLeft,
                chartRight,
                chartTop,
                chartBottom,
                maxValue
              )
              : null;
          const nextPoint =
            index < data.length - 1
              ? getChartPoint(
                data[index + 1].success_count,
                index + 1,
                data.length,
                width,
                height,
                chartLeft,
                chartRight,
                chartTop,
                chartBottom,
                maxValue
              )
              : null;
          const leftBound = previousPoint ? (previousPoint.x + currentPoint.x) / 2 : chartLeft;
          const rightBound = nextPoint ? (currentPoint.x + nextPoint.x) / 2 : width - chartRight;

          return (
            <rect
              key={item.date}
              x={leftBound}
              y={chartTop}
              width={Math.max(18, rightBound - leftBound)}
              height={height - chartTop - chartBottom}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            />
          );
        })}
        {data.map((item, index) => {
          const successPoint = getChartPoint(
            item.success_count,
            index,
            data.length,
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          );
          const failurePoint = getChartPoint(
            item.failed_count,
            index,
            data.length,
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          );

          return (
            <g key={`point-${item.date}`} pointerEvents="none">
              <text
                x={successPoint.x}
                y={successPoint.y - 10}
                textAnchor="middle"
                fontSize="8"
                fontWeight="700"
                fill={SUCCESS_COLOR}
              >
                {item.success_count}
              </text>
              <circle cx={successPoint.x} cy={successPoint.y} r="4" fill="#fff" stroke={SUCCESS_COLOR} strokeWidth="2" />
              <circle cx={failurePoint.x} cy={failurePoint.y} r="4" fill="#fff" stroke={FAILURE_COLOR} strokeWidth="2" />
              <text
                x={failurePoint.x}
                y={failurePoint.y - 10}
                textAnchor="middle"
                fontSize="8"
                fontWeight="700"
                fill={FAILURE_COLOR}
              >
                {item.failed_count}
              </text>
            </g>
          );
        })}
        {data.map((item, index) => {
          if (!visibleXAxisIndices.includes(index)) {
            return null;
          }

          const { x } = getChartPoint(
            item.success_count,
            index,
            data.length,
            width,
            height,
            chartLeft,
            chartRight,
            chartTop,
            chartBottom,
            maxValue
          );

          return (
            <text
              key={item.date}
              x={x}
              y={height - 8}
              textAnchor={index === 0 ? 'start' : index === data.length - 1 ? 'end' : 'middle'}
              fontSize="11"
              fontWeight="500"
              fill="#8092a8"
            >
              {formatAxisDate(item.date)}
            </text>
          );
        })}
      </svg>
    </div>
  );
};

const STATUS_COLOR_MAP: Record<JobRecordStatus, string> = {
  pending: '#faad14',
  running: '#1890ff',
  success: '#52c41a',
  failed: '#ff4d4f',
  canceled: '#8c8c8c',
};

const getSourceConfig = (source: JobRecordSource | string | undefined) => {
  const configs: Record<string, { color: string; bg: string; border: string }> = {
    manual: { color: '#2d87ff', bg: 'rgba(45, 135, 255, 0.08)', border: '#2d87ff' },
    scheduled: { color: '#ff6600', bg: 'rgba(255, 102, 0, 0.08)', border: '#ff6600' },
    api: { color: '#722ed1', bg: 'rgba(114, 46, 209, 0.08)', border: '#722ed1' },
  };
  return configs[source || 'manual'] || configs.manual;
};

const JobHomePage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading: isApiReady } = useApiClient();
  const { getDashboardSuccessRateCompare, getDashboardTrend, getJobRecordList } = useJobApi();

  const [recentJobs, setRecentJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [selectedOverviewDays, setSelectedOverviewDays] = useState<OverviewDays>(7);
  const [overviewDataMap, setOverviewDataMap] = useState<Record<OverviewDays, OverviewData>>({
    7: { trend: [], successRateCompare: null },
    30: { trend: [], successRateCompare: null },
  });

  const cardColors = [
    { bg: 'rgba(45, 135, 255, 0.08)', icon: '#2d87ff' },
    { bg: 'rgba(45, 199, 165, 0.08)', icon: '#2dc7a5' },
    { bg: 'rgba(255, 156, 60, 0.08)', icon: '#ff9c3c' },
  ];

  const featureCards = [
    {
      key: 'script',
      icon: 'wenbenfenlei',
      title: t('job.scriptExecution'),
      description: t('job.scriptExecutionDesc'),
      link: '/job/execution/quick-exec',
    },
    {
      key: 'file',
      icon: 'shitishu',
      title: t('job.fileDistribution'),
      description: t('job.fileDistributionDesc'),
      link: '/job/execution/file-dist',
    },
    {
      key: 'cron',
      icon: 'shixuyuce',
      title: t('job.scheduledTask'),
      description: t('job.scheduledTaskDesc'),
      link: '/job/execution/cron-task',
    },
  ];

  const fetchRecentJobs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getJobRecordList({ page: 1, page_size: 20 });
      setRecentJobs(res.items || res.results || []);
    } catch {
      setRecentJobs([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchOverviewData = useCallback(async () => {
    setOverviewLoading(true);
    try {
      const [trend7, compare7, trend30, compare30] = await Promise.all([
        getDashboardTrend(7),
        getDashboardSuccessRateCompare(7),
        getDashboardTrend(30),
        getDashboardSuccessRateCompare(30),
      ]);

      setOverviewDataMap({
        7: { trend: trend7 || [], successRateCompare: compare7 || null },
        30: { trend: trend30 || [], successRateCompare: compare30 || null },
      });
    } catch {
      setOverviewDataMap({
        7: { trend: [], successRateCompare: null },
        30: { trend: [], successRateCompare: null },
      });
    } finally {
      setOverviewLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isApiReady) {
      fetchRecentJobs();
      fetchOverviewData();
    }
  }, [isApiReady, fetchOverviewData, fetchRecentJobs]);

  const selectedOverviewData = useMemo(
    () => overviewDataMap[selectedOverviewDays],
    [overviewDataMap, selectedOverviewDays]
  );

  const overviewSummary = useMemo(() => {
    const currentPeriod = selectedOverviewData.successRateCompare?.current_period;

    return {
      executionTotal: currentPeriod?.execution_total ?? 0,
      successCount: currentPeriod?.success_count ?? 0,
      failedCount: currentPeriod?.failed_count ?? 0,
      successRate: currentPeriod?.success_rate ?? 0,
      successRateIncrease: selectedOverviewData.successRateCompare?.success_rate_increase ?? 0,
    };
  }, [selectedOverviewData.successRateCompare]);

  const showOverviewSection = useMemo(() => {
    const trend = selectedOverviewData.trend || [];
    const totalFromTrend = trend.reduce((sum, item) => sum + (item.execution_count || 0), 0);
    const totalFromCompare = selectedOverviewData.successRateCompare?.current_period?.execution_total || 0;
    return totalFromTrend > 0 || totalFromCompare > 0;
  }, [selectedOverviewData]);

  const formatTime = (timeStr: string | null | undefined) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const getStatusText = (status: JobRecordStatus) => {
    const statusTextMap: Record<JobRecordStatus, string> = {
      pending: t('job.statusPending'),
      running: t('job.statusRunning'),
      success: t('job.statusSuccess'),
      failed: t('job.statusFailed'),
      canceled: t('job.statusCanceled'),
    };
    return statusTextMap[status] || status;
  };

  const getSourceText = (source: JobRecordSource | undefined) => {
    if (!source) return '-';
    const sourceTextMap: Record<JobRecordSource, string> = {
      manual: t('job.manual'),
      scheduled: t('job.scheduled'),
      api: 'API',
    };
    return sourceTextMap[source] || source;
  };

  const handleViewDetail = (record: JobRecord) => {
    router.push(`/job/execution/job-record?id=${record.id}`);
  };

  const recentJobColumns = [
    {
      title: t('job.jobName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: t('job.jobType'),
      dataIndex: 'job_type_display',
      key: 'job_type_display',
      width: 120,
      render: (text: string) => (
        <Tag
          style={{
            color: 'var(--color-text-3)',
            backgroundColor: 'var(--color-bg)',
            borderColor: 'var(--color-border-1)',
            margin: 0,
          }}
        >
          {text}
        </Tag>
      ),
    },
    {
      title: t('job.triggerSource'),
      dataIndex: 'trigger_source',
      key: 'trigger_source',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const source = record.trigger_source || record.source;
        const display = record.trigger_source_display || record.source_display;
        const style = getSourceConfig(source);
        return (
          <Tag
            style={{
              color: style.color,
              backgroundColor: style.bg,
              borderColor: style.border,
              margin: 0,
            }}
          >
            {display || getSourceText(source as JobRecordSource)}
          </Tag>
        );
      },
    },
    {
      title: t('job.executionStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const color = STATUS_COLOR_MAP[record.status] || '#8c8c8c';
        return (
          <Tag
            style={{
              color,
              backgroundColor: `${color}10`,
              borderColor: color,
              margin: 0,
            }}
          >
            {record.status_display || getStatusText(record.status)}
          </Tag>
        );
      },
    },
    {
      title: t('job.startTime'),
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (_: unknown, record: JobRecord) => formatTime(record.started_at),
    },
    {
      title: t('job.operation'),
      key: 'action',
      width: 100,
      render: (_: unknown, record: JobRecord) => (
        <a
          className="text-(--color-primary) cursor-pointer"
          onClick={() => handleViewDetail(record)}
        >
          {t('job.viewDetail')}
        </a>
      ),
    },
  ];

  return (
    <div className="w-full">
      {/* Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {featureCards.map((card, index) => (
          <div
            key={card.key}
            className="bg-(--color-bg) rounded-lg p-6 shadow-sm border border-(--color-border-1) flex h-full flex-col"
          >
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
              style={{ backgroundColor: cardColors[index].bg }}
            >
              <Icon
                type={card.icon}
                className="text-2xl"
                style={{ color: cardColors[index].icon }}
              />
            </div>
            <h3 className="text-base font-semibold mb-2">{card.title}</h3>
            <p className="text-sm text-(--color-text-3) leading-relaxed mb-6">
              {card.description}
            </p>
            <div className="mt-auto">
              <Button
                type="primary"
                block
                onClick={() => router.push(card.link)}
              >
                {t('job.enter')}
              </Button>
            </div>
          </div>
        ))}
      </div>

      {(overviewLoading || showOverviewSection) && (
        <div className="bg-(--color-bg) rounded-lg p-6 shadow-sm border border-(--color-border-1) mb-4">
          <div className="mb-4">
            <h3 className="text-base font-semibold text-(--color-text-1) mb-1">{t('job.operationsOverview')}</h3>
            <p className="text-sm text-(--color-text-3)">{t('job.operationsOverviewDesc')}</p>
          </div>

          {overviewLoading ? (
            <Skeleton active paragraph={{ rows: 6 }} />
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-[176px_minmax(0,1fr)] gap-4 items-stretch xl:min-h-95">
              <div className="flex h-full flex-col gap-4">
                <div className="flex-1 rounded-2xl border border-[#e8eef5] bg-[#ffffff] px-5 py-4 shadow-[0_2px_10px_rgba(15,23,42,0.04)] flex flex-col">
                  <div className="text-sm font-medium text-(--color-text-2) mb-4">{t('job.executionCount')}</div>
                  <div className="flex-1 flex flex-col justify-center">
                    <div className="text-[46px] leading-none font-semibold tracking-[-0.03em] text-[#0f172a] mb-3">{overviewSummary.executionTotal}</div>
                    <div className="text-xs leading-6 text-[#7c8da1]">
                      {t('job.successCount')} {overviewSummary.successCount} / {t('job.failedCount')} {overviewSummary.failedCount}
                    </div>
                  </div>
                </div>
                <div className="flex-1 rounded-2xl border border-[#e8eef5] bg-[#ffffff] px-5 py-4 shadow-[0_2px_10px_rgba(15,23,42,0.04)] flex flex-col">
                  <div className="text-sm font-medium text-(--color-text-2) mb-4">{t('job.successRate')}</div>
                  <div className="flex-1 flex flex-col justify-center">
                    <div className="text-[46px] leading-none font-semibold tracking-[-0.03em] text-[#19b87a] mb-3">
                      {formatPercent(overviewSummary.successRate)}
                    </div>
                    <div className={`text-xs font-medium ${overviewSummary.successRateIncrease >= 0 ? 'text-[#7c8da1]' : 'text-[#d85f28]'}`}>
                      {t('job.successRateChange')} {formatDelta(overviewSummary.successRateIncrease)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex h-full flex-col rounded-2xl border border-[#e8eef5] bg-[#ffffff] px-5 py-4 shadow-[0_2px_10px_rgba(15,23,42,0.04)]">
                <div className="flex items-start justify-between mb-2 gap-3 flex-wrap">
                  <div>
                    <div className="text-lg font-semibold text-[#1f2937] mb-1">{t('job.executionTrend')}</div>
                    <div className="text-sm text-[#8a9ab0]">{selectedOverviewDays === 7 ? t('job.last7Days') : t('job.last30Days')}</div>
                  </div>
                  <Segmented
                    className="w-fit"
                    options={OVERVIEW_DAYS_OPTIONS.map((option) => ({
                      label: option.value === 7 ? t('job.last7Days') : t('job.last30Days'),
                      value: option.value,
                    }))}
                    value={selectedOverviewDays}
                    onChange={(value) => setSelectedOverviewDays(value as OverviewDays)}
                  />
                </div>
                <div className="flex-1">
                  <TrendMiniChart data={selectedOverviewData.trend} t={t} />
                </div>
                <div className="flex items-center gap-5 mt-2 flex-wrap text-xs text-[#7c8da1]">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full border-[3px] border-[#19b87a] bg-white" />
                    <span>{t('job.success')}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full border-[3px] border-[#ff5a52] bg-white" />
                    <span>{t('job.failed')}</span>
                  </div>
                  <div className="text-xs text-[#9aa9bc]">悬停查看成功/失败/总执行</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recent Jobs Table */}
      <div className="bg-(--color-bg) rounded-lg p-6 shadow-sm border border-(--color-border-1)">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-(--color-text-1)">{t('job.recentJobs')}</h3>
          <a
            className="text-sm text-(--color-primary) cursor-pointer"
            onClick={() => router.push('/job/execution/job-record')}
          >
            {t('job.viewAll')} →
          </a>
        </div>
        <CustomTable
          columns={recentJobColumns}
          dataSource={recentJobs}
          loading={loading}
          rowKey="id"
          pagination={false}
          size="middle"
        />
      </div>
    </div>
  );
};

export default JobHomePage;
