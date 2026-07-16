import React from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import ExecutionStatusBadge from '@/components/execution-status-badge';
import {
  LogAnalysisBar,
  LogAnalysisBarLine,
  LogAnalysisCategoryBar,
  LogAnalysisDualTrend,
  LogAnalysisHeatmap,
  LogAnalysisLatestValueKpiCard,
  LogAnalysisLine,
  LogAnalysisMessageTable,
  LogAnalysisMetricsTrend,
  LogMessagePreview,
  LogAnalysisPie,
  LogAnalysisRequestErrorTrend,
  LogAnalysisSankey,
  LogAnalysisScatter,
  LogAnalysisSingle,
  LogAnalysisSummaryBreakdownPie,
  LogAnalysisTable,
} from '@/components/log-analysis-widgets';

const overviewData = [
  { _time: '2025-06-01 10:00', requests: 120, latency: 48, level: 'ERROR', count: 18 },
  { _time: '2025-06-01 10:05', requests: 162, latency: 53, level: 'WARN', count: 11 },
  { _time: '2025-06-01 10:10', requests: 148, latency: 45, level: 'INFO', count: 9 },
];

const levelDistribution = [
  { category: 'ERROR', count: 182 },
  { category: 'WARN', count: 109 },
  { category: 'INFO', count: 73 },
];

const messageRows = [
  {
    _time: '2026-06-29T10:15:12.125Z',
    _msg: 'GET /api/orders returned 502 from upstream gateway',
    collector: 'otel-sidecar',
    collect_type: 'container',
    service: 'orders-api',
  },
  {
    _time: '2026-06-29T10:16:03.421Z',
    _msg: 'Redis timeout exceeded while rebuilding recommendation cache',
    collector: 'otel-sidecar',
    collect_type: 'container',
    service: 'recommendation-worker',
  },
];

const FamilyOverview = () => {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisBar
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisBar
              rawData={[
                { bucket: 'api-gateway', value: 1820 },
                { bucket: 'orders', value: 1090 },
                { bucket: 'inventory', value: 730 },
              ]}
              config={{
                direction: 'horizontal',
                displayMaps: {
                  key: 'bucket',
                  value: 'value',
                },
              }}
            />
          </div>
          <div style={{ height: 260 }}>
            <LogAnalysisBar
              rawData={[
                { name: 'ERROR', count: 182 },
                { name: 'WARN', count: 109 },
                { name: 'INFO', count: 73 },
              ]}
              config={{
                displayMaps: {
                  key: 'name',
                  value: 'count',
                },
              }}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                MySQL instance preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisBar
                  rawData={[
                    { node_ip: '10.0.0.21', slow_count: 182 },
                    { node_ip: '10.0.0.18', slow_count: 126 },
                    { node_ip: '10.0.0.11', slow_count: 78 },
                  ]}
                  config={{
                    direction: 'horizontal',
                    displayMaps: {
                      key: 'node_ip',
                      value: 'slow_count',
                    },
                  }}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Redis instance preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisBar
                  rawData={[
                    { node_ip: '10.0.1.9', log_count: 1460 },
                    { node_ip: '10.0.1.7', log_count: 1040 },
                    { node_ip: '10.0.1.5', log_count: 820 },
                  ]}
                  config={{
                    direction: 'horizontal',
                    displayMaps: {
                      key: 'node_ip',
                      value: 'log_count',
                    },
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisCategoryBar
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisCategoryBar
              rawData={[
                { name: 'api-gateway', count: 1820 },
                { name: 'orders', count: 1090 },
                { name: 'inventory', count: 730 },
              ]}
              config={{
                displayMaps: {
                  key: 'name',
                  value: 'count',
                },
              }}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Flow preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisCategoryBar
                  rawData={[
                    { edge: '10.0.0.1 -> 10.0.1.10', bytes: 8600 },
                    { edge: '10.0.0.3 -> 10.0.1.14', bytes: 6240 },
                    { edge: '10.0.0.7 -> 10.0.1.18', bytes: 4110 },
                  ]}
                  config={{
                    displayMaps: {
                      key: 'edge',
                      value: 'bytes',
                    },
                    categoryLabelWidth: 110,
                    categoryLabelMaxLength: 14,
                  }}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Redis node compare preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisCategoryBar
                  rawData={[
                    { node_ip: '10.0.1.9', log_count: 1460, err_count: 42 },
                    { node_ip: '10.0.1.7', log_count: 1040, err_count: 31 },
                    { node_ip: '10.0.1.5', log_count: 820, err_count: 18 },
                  ]}
                  config={{
                    displayMaps: {
                      key: 'node_ip',
                    },
                    series: [
                      { label: '日志量', dataKey: 'log_count', colorIndex: 0 },
                      { label: '错误数', dataKey: 'err_count', colorIndex: 4 },
                    ],
                    showLegend: true,
                    categoryLabelWidth: 110,
                    categoryLabelMaxLength: 16,
                    gridRight: 32,
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisRequestErrorTrend
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisRequestErrorTrend
              rawData={[
                { _time: '2025-06-01 10:00', total_count: 1280, error4xx: 64, error5xx: 11 },
                { _time: '2025-06-01 10:05', total_count: 1460, error4xx: 78, error5xx: 15 },
                { _time: '2025-06-01 10:10', total_count: 1390, error4xx: 58, error5xx: 9 },
              ]}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Nginx preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisRequestErrorTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 1820, error4xx: 92, error5xx: 14 },
                    { _time: '2025-06-01 10:05', total_count: 1940, error4xx: 108, error5xx: 19 },
                    { _time: '2025-06-01 10:10', total_count: 1760, error4xx: 81, error5xx: 12 },
                  ]}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Apache preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisRequestErrorTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 990, error4xx: 35, error5xx: 6 },
                    { _time: '2025-06-01 10:05', total_count: 1110, error4xx: 41, error5xx: 8 },
                    { _time: '2025-06-01 10:10', total_count: 1075, error4xx: 39, error5xx: 7 },
                  ]}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisLine
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisLine
              rawData={overviewData}
              config={{
                displayMaps: {
                  key: '_time',
                  value: 'latency',
                  tooltipField: '延迟',
                },
              }}
            />
          </div>
          <div style={{ height: 260 }}>
            <LogAnalysisLine
              rawData={[
                { _time: '2025-06-01 10:00', errors: 12 },
                { _time: '2025-06-01 10:05', errors: 18 },
                { _time: '2025-06-01 10:10', errors: 9 },
              ]}
              config={{
                displayMaps: {
                  key: '_time',
                  value: 'errors',
                  tooltipField: '错误数',
                },
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisSingle
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisSingle
              rawData={{ error_rate: 3.17 }}
              config={{
                color: '#fd666d',
                displayMaps: {
                  value: 'error_rate',
                },
              }}
            />
          </div>
          <div style={{ height: 260 }}>
            <LogAnalysisSingle
              rawData={[{ requests: 18240 }]}
              config={{
                color: '#366ce4',
                displayMaps: {
                  value: 'requests',
                },
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisLatestValueKpiCard
        </h3>
        <div className="space-y-4">
          <div style={{ height: 220 }}>
            <LogAnalysisLatestValueKpiCard
              rawData={[
                { _time: '2025-06-01 10:00', total_count: 920 },
                { _time: '2025-06-01 10:05', total_count: 1010 },
                { _time: '2025-06-01 10:10', total_count: 1140 },
              ]}
              config={{
                metricMode: 'latest',
                displayMaps: {
                  value: 'total_count',
                },
              }}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Syslog preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisLatestValueKpiCard
                  rawData={[
                    { _time: '2025-06-01 10:00', high_count: 18 },
                    { _time: '2025-06-01 10:05', high_count: 24 },
                    { _time: '2025-06-01 10:10', high_count: 27 },
                  ]}
                  config={{
                    metricMode: 'latest',
                    displayMaps: {
                      value: 'high_count',
                    },
                  }}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                PostgreSQL preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisLatestValueKpiCard
                  rawData={[
                    { _time: '2025-06-01 10:00', client_count: 46 },
                    { _time: '2025-06-01 10:05', client_count: 53 },
                    { _time: '2025-06-01 10:10', client_count: 58 },
                  ]}
                  config={{
                    metricMode: 'latest',
                    displayMaps: {
                      value: 'client_count',
                    },
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisDualTrend
        </h3>
        <div className="space-y-4">
          <div style={{ height: 220 }}>
            <LogAnalysisDualTrend
              rawData={[
                { _time: '2025-06-01 10:00', total_count: 920, error_count: 36 },
                { _time: '2025-06-01 10:05', total_count: 1040, error_count: 44 },
                { _time: '2025-06-01 10:10', total_count: 1180, error_count: 29 },
              ]}
              primaryField="total_count"
              primaryLabel="日志总量"
              secondaryField="error_count"
              secondaryLabel="错误数"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Docker preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisDualTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', logcount: 860, warn_count: 12 },
                    { _time: '2025-06-01 10:05', logcount: 940, warn_count: 18 },
                    { _time: '2025-06-01 10:10', logcount: 910, warn_count: 15 },
                  ]}
                  primaryField="logcount"
                  primaryLabel="日志总量"
                  secondaryField="warn_count"
                  secondaryLabel="Warning"
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                MySQL preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisDualTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', slow_count: 81, lock_count: 6 },
                    { _time: '2025-06-01 10:05', slow_count: 96, lock_count: 8 },
                    { _time: '2025-06-01 10:10', slow_count: 74, lock_count: 5 },
                  ]}
                  primaryField="slow_count"
                  primaryLabel="慢查询"
                  secondaryField="lock_count"
                  secondaryLabel="锁等待"
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Redis preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisDualTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 1160, err_count: 42 },
                    { _time: '2025-06-01 10:05', total_count: 1230, err_count: 51 },
                    { _time: '2025-06-01 10:10', total_count: 1105, err_count: 37 },
                  ]}
                  primaryField="total_count"
                  primaryLabel="日志总量"
                  secondaryField="err_count"
                  secondaryLabel="ERR 错误"
                  hideSecondaryWhenEmpty
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisMetricsTrend
        </h3>
        <div className="space-y-4">
          <div style={{ height: 220 }}>
            <LogAnalysisMetricsTrend
              rawData={[
                { _time: '2025-06-01 10:00', total_count: 920, error_count: 36, warning_count: 20, slow_count: 8 },
                { _time: '2025-06-01 10:05', total_count: 1040, error_count: 44, warning_count: 18, slow_count: 11 },
                { _time: '2025-06-01 10:10', total_count: 1180, error_count: 29, warning_count: 14, slow_count: 7 },
              ]}
              primary={{ label: '总日志数', dataKey: 'total_count' }}
              secondary={[
                { label: 'Error', dataKey: 'error_count' },
                { label: 'Warning', dataKey: 'warning_count' },
                { label: '慢日志', dataKey: 'slow_count' },
              ]}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Kafka preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisMetricsTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 1620, error_count: 84, warning_count: 43, stack_count: 16 },
                    { _time: '2025-06-01 10:05', total_count: 1740, error_count: 92, warning_count: 39, stack_count: 14 },
                    { _time: '2025-06-01 10:10', total_count: 1695, error_count: 71, warning_count: 34, stack_count: 11 },
                  ]}
                  primary={{ label: '总日志数', dataKey: 'total_count' }}
                  secondary={[
                    { label: 'Error / Fatal', dataKey: 'error_count' },
                    { label: 'Warning', dataKey: 'warning_count' },
                    { label: '异常堆栈日志数', dataKey: 'stack_count' },
                  ]}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                PostgreSQL preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisMetricsTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 680, error_count: 21, slow_count: 17, client_count: 46 },
                    { _time: '2025-06-01 10:05', total_count: 740, error_count: 18, slow_count: 22, client_count: 53 },
                    { _time: '2025-06-01 10:10', total_count: 705, error_count: 16, slow_count: 14, client_count: 58 },
                  ]}
                  primary={{ label: '总日志数', dataKey: 'total_count' }}
                  secondary={[
                    { label: 'Error / Fatal', dataKey: 'error_count' },
                    { label: '慢 SQL', dataKey: 'slow_count' },
                    { label: '客户端活跃数', dataKey: 'client_count' },
                  ]}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Elasticsearch preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisMetricsTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 1180, error_count: 64, warn_count: 27, slow_count: 19 },
                    { _time: '2025-06-01 10:05', total_count: 1250, error_count: 59, warn_count: 31, slow_count: 23 },
                    { _time: '2025-06-01 10:10', total_count: 1215, error_count: 52, warn_count: 24, slow_count: 18 },
                  ]}
                  primary={{ label: '总日志数', dataKey: 'total_count' }}
                  secondary={[
                    { label: 'Error 日志数', dataKey: 'error_count' },
                    { label: 'Warn 日志数', dataKey: 'warn_count' },
                    { label: '慢日志数', dataKey: 'slow_count' },
                  ]}
                  primaryType="line"
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Windows Event preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisMetricsTrend
                  rawData={[
                    { _time: '2025-06-01 10:00', total_count: 1180, security_count: 264, warning_count: 153, login_fail: 41 },
                    { _time: '2025-06-01 10:05', total_count: 1250, security_count: 281, warning_count: 147, login_fail: 36 },
                    { _time: '2025-06-01 10:10', total_count: 1215, security_count: 259, warning_count: 165, login_fail: 49 },
                  ]}
                  primary={{ label: '总事件数', dataKey: 'total_count' }}
                  secondary={[
                    { label: '安全事件数', dataKey: 'security_count' },
                    { label: '错误/警告事件数', dataKey: 'warning_count' },
                    { label: '登录失败数', dataKey: 'login_fail' },
                  ]}
                  primaryType="line"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisBarLine
        </h3>
        <div style={{ height: 260 }}>
          <LogAnalysisBarLine
            rawData={overviewData}
            config={{
              displayMaps: {
                key: '_time',
                bar: 'requests',
                line: 'latency',
                barLabel: '请求数',
                lineLabel: '延迟',
              },
            }}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisHeatmap
        </h3>
        <div style={{ height: 260 }}>
          <LogAnalysisHeatmap
            rawData={[
              { _time: '2026-06-29 10:00:00', container_name: 'api-gateway', errcount: 4 },
              { _time: '2026-06-29 10:05:00', container_name: 'api-gateway', errcount: 7 },
              { _time: '2026-06-29 10:10:00', container_name: 'api-gateway', errcount: 2 },
              { _time: '2026-06-29 10:00:00', container_name: 'worker', errcount: 1 },
              { _time: '2026-06-29 10:05:00', container_name: 'worker', errcount: 5 },
              { _time: '2026-06-29 10:10:00', container_name: 'worker', errcount: 8 },
            ]}
            config={{
              displayMaps: {
                time: '_time',
                category: 'container_name',
                value: 'errcount',
              },
              limit: 8,
            }}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisPie
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisPie
              rawData={levelDistribution}
              config={{
                displayMaps: {
                  key: 'category',
                  value: 'count',
                },
              }}
            />
          </div>
          <div style={{ height: 260 }}>
            <LogAnalysisPie
              rawData={[
                { category: 'A', count: 42 },
                { category: 'B', count: 38 },
                { category: 'C', count: 32 },
                { category: 'D', count: 27 },
                { category: 'E', count: 24 },
                { category: 'F', count: 18 },
              ]}
              config={{
                displayMaps: {
                  key: 'category',
                  value: 'count',
                },
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisSummaryBreakdownPie
        </h3>
        <div className="space-y-4">
          <div style={{ height: 260 }}>
            <LogAnalysisSummaryBreakdownPie
              rawData={[
                {
                  total_count: 128,
                  error_count: 42,
                  warn_count: 31,
                  info_count: 28,
                  debug_count: 19,
                },
              ]}
              buckets={[
                { field: 'error_count', label: 'ERROR' },
                { field: 'warn_count', label: 'WARN' },
                { field: 'info_count', label: 'INFO' },
                { field: 'debug_count', label: 'DEBUG' },
              ]}
              totalField="total_count"
              remainderLabel="UNKNOWN"
              nameField="level"
              valueField="cnt"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                MySQL preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisSummaryBreakdownPie
                  rawData={[
                    {
                      cnt_lt01: 48,
                      cnt_01_1: 39,
                      cnt_1_10: 22,
                      cnt_gt10: 11,
                    },
                  ]}
                  buckets={[
                    { field: 'cnt_lt01', label: '快速 <0.1s' },
                    { field: 'cnt_01_1', label: '普通 0.1–1s' },
                    { field: 'cnt_1_10', label: '慢 1–10s' },
                    { field: 'cnt_gt10', label: '严重 >10s' },
                  ]}
                  nameField="bucket"
                  valueField="cnt"
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Redis preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisSummaryBreakdownPie
                  rawData={[
                    {
                      total_count: 160,
                      err_count: 36,
                      type_err_count: 19,
                      auth_err_count: 11,
                      cmd_count: 74,
                    },
                  ]}
                  buckets={[
                    { field: 'err_count', label: 'ERR 错误' },
                    { field: 'type_err_count', label: '类型/集群错误' },
                    { field: 'auth_err_count', label: '认证失败' },
                    { field: 'cmd_count', label: '命令日志' },
                  ]}
                  totalField="total_count"
                  remainderLabel="其他"
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--color-text-2)]">
                Docker preset
              </div>
              <div style={{ height: 220 }}>
                <LogAnalysisSummaryBreakdownPie
                  rawData={[
                    {
                      total_count: 210,
                      error_count: 52,
                      warn_count: 44,
                      info_count: 71,
                      debug_count: 27,
                    },
                  ]}
                  buckets={[
                    { field: 'error_count', label: 'ERROR' },
                    { field: 'warn_count', label: 'WARN' },
                    { field: 'info_count', label: 'INFO' },
                    { field: 'debug_count', label: 'DEBUG' },
                  ]}
                  totalField="total_count"
                  remainderLabel="UNKNOWN"
                  nameField="level"
                  valueField="cnt"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisScatter
        </h3>
        <div style={{ height: 260 }}>
          <LogAnalysisScatter
            rawData={[
              { request_count: 120, error_count: 18, service: 'api-gateway' },
              { request_count: 98, error_count: 42, service: 'orders' },
              { request_count: 210, error_count: 16, service: 'inventory' },
              { request_count: 64, error_count: 71, service: 'auth' },
            ]}
            config={{
              displayMaps: {
                xField: 'request_count',
                yField: 'error_count',
                labelField: 'service',
                xLabel: '请求数',
                yLabel: '错误数',
              },
            }}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 lg:col-span-2">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisSankey
        </h3>
        <div style={{ height: 320 }}>
          <LogAnalysisSankey
            rawData={[
              { 'source.ip': '10.0.0.1', 'destination.ip': '10.0.1.10', flow_bytes: 1200 },
              { 'source.ip': '10.0.0.1', 'destination.ip': '10.0.1.11', flow_bytes: 860 },
              { 'source.ip': '10.0.0.2', 'destination.ip': '10.0.1.10', flow_bytes: 640 },
            ]}
            config={{
              displayMaps: {
                sourceField: 'source.ip',
                targetField: 'destination.ip',
                valueField: 'flow_bytes',
              },
            }}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 lg:col-span-2">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisTable
        </h3>
        <div className="space-y-4">
          <LogAnalysisTable
            rawData={overviewData}
            config={{
              showIndex: true,
              columns: [
                { title: 'Time', dataIndex: '_time', key: '_time' },
                { title: 'Level', dataIndex: 'level', key: 'level' },
                { title: 'Count', dataIndex: 'count', key: 'count' },
                { title: 'Latency', dataIndex: 'latency', key: 'latency' },
              ],
            }}
          />
          <LogAnalysisTable
            rawData={[
              { path: '/api/orders', count: 58 },
              { path: '/api/inventory', count: 34 },
              { path: '/api/auth', count: 19 },
            ]}
            config={{
              columns: [
                { title: 'Path', dataIndex: 'path', key: 'path' },
                { title: 'Events', dataIndex: 'count', key: 'count' },
              ],
            }}
          />
          <div style={{ height: 260 }}>
            <LogAnalysisTable
              rawData={[
                { _time: '2025-06-01 10:00', node_ip: '10.0.1.9', _msg: 'ERR maxmemory reached', 'log.file.path': '/data/redis/sentinel/redis.log' },
                { _time: '2025-06-01 10:05', node_ip: '10.0.1.7', _msg: 'WARNING persistence delayed', 'log.file.path': '/data/redis/cluster/redis.log' },
              ]}
              config={{
                scrollX: 'max-content',
                columns: [
                  { title: '时间', dataIndex: '_time', key: '_time', width: 130 },
                  { title: '节点 IP', dataIndex: 'node_ip', key: 'node_ip', width: 120 },
                  { title: '日志内容', dataIndex: '_msg', key: '_msg', width: 320 },
                  { title: '文件路径', dataIndex: 'log.file.path', key: 'log.file.path', width: 240 },
                ],
              }}
            />
          </div>
          <div style={{ height: 260 }}>
            <LogAnalysisTable
              rawData={[
                { time: '10:00:21', container: 'api-gateway', stream: 'stdout', level: 'INFO', message: 'service started on port 8080' },
                { time: '10:01:04', container: 'worker', stream: 'stderr', level: 'ERROR', message: 'failed to flush queue batch' },
              ]}
              config={{
                scrollX: 'max-content',
                columns: [
                  { title: '时间', dataIndex: 'time', key: 'time', width: 72 },
                  { title: '容器', dataIndex: 'container', key: 'container', width: 88 },
                  { title: '日志流', dataIndex: 'stream', key: 'stream', width: 60 },
                  { title: '级别', dataIndex: 'level', key: 'level', width: 56 },
                  { title: '日志内容', dataIndex: 'message', key: 'message', width: 320 },
                ],
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 lg:col-span-2">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogAnalysisMessageTable
        </h3>
        <div className="space-y-4">
          <div style={{ height: 280 }}>
            <LogAnalysisMessageTable
              rawData={messageRows}
              config={{
                columns: [
                  { title: 'Message', dataIndex: '_msg', key: '_msg' },
                  { title: 'Service', dataIndex: 'service', key: 'service', width: 180 },
                  { title: 'Collector', dataIndex: 'collector', key: 'collector', width: 150 },
                ],
              }}
            />
          </div>
          <div style={{ height: 280 }}>
            <LogAnalysisMessageTable
              rawData={[
                {
                  _time: '2026-06-29T10:15:12.125Z',
                  _msg: 'GET /api/orders returned 502 from upstream gateway',
                  collector: 'otel-sidecar',
                  collect_type: 'container',
                  service: 'orders-api',
                  host: 'node-01',
                },
                {
                  _time: '2026-06-29T10:16:03.421Z',
                  _msg: 'Redis timeout exceeded while rebuilding recommendation cache',
                  collector: 'otel-sidecar',
                  collect_type: 'container',
                  service: 'recommendation-worker',
                  host: 'node-02',
                },
              ]}
              config={{
                columns: [
                  { title: 'Message', dataIndex: '_msg', key: '_msg' },
                  { title: 'Service', dataIndex: 'service', key: 'service', width: 180 },
                  { title: 'Collector', dataIndex: 'collector', key: 'collector', width: 150 },
                ],
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          LogMessagePreview
        </h3>
        <div className="space-y-4">
          <LogMessagePreview
            value="SELECT service, status, COUNT(*) FROM request_logs WHERE latency_ms > 500 GROUP BY service, status ORDER BY COUNT(*) DESC LIMIT 20;"
            previewLength={60}
          />
          <LogMessagePreview
            value={'ERROR 1126 (HY000): Can not open shared library "/usr/lib/mysql/plugin/semisync_master.so" (errno: 2 cannot open shared object file: No such file or directory)'}
            previewLength={120}
            monospace={false}
          />
          <LogMessagePreview value="" />
          <LogMessagePreview value="Workflow execution failed: upstream connector returned HTTP 504 after retry exhaustion.">
            <ExecutionStatusBadge status="failed" label="Failed" />
          </LogMessagePreview>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Log/Analysis/Widgets/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1120, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
