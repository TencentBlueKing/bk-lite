import React from 'react';

import { ConfigAnalysisReport, ConfigAnalysisReportItem, ConfigAnalysisSeveritySection } from '@/app/opspilot/types/global';

interface ConfigAnalysisReportCardProps {
  report: ConfigAnalysisReport;
}

const severityStyles: Record<ConfigAnalysisSeveritySection['severity'] | 'unknown', { badge: string; text: string; border: string }> = {
  critical: { badge: 'bg-rose-100 text-rose-700', text: '严重', border: 'border-rose-200' },
  high: { badge: 'bg-orange-100 text-orange-700', text: '高危', border: 'border-orange-200' },
  medium: { badge: 'bg-amber-100 text-amber-700', text: '中风险', border: 'border-amber-200' },
  low: { badge: 'bg-lime-100 text-lime-700', text: '低风险', border: 'border-lime-200' },
  warning: { badge: 'bg-yellow-100 text-yellow-700', text: '警告', border: 'border-yellow-200' },
  info: { badge: 'bg-sky-100 text-sky-700', text: '提示', border: 'border-sky-200' },
  unknown: { badge: 'bg-slate-100 text-slate-700', text: '未识别', border: 'border-slate-200' },
};

const knownSeverities = new Set<ConfigAnalysisSeveritySection['severity']>([
  'critical',
  'high',
  'medium',
  'low',
  'warning',
  'info',
]);

interface NormalizedIssue extends ConfigAnalysisReportItem {
  degraded?: boolean;
}

interface NormalizedSection {
  severity: ConfigAnalysisSeveritySection['severity'] | 'unknown';
  title: string;
  issues: NormalizedIssue[];
  degraded: boolean;
}

const normalizeSeverity = (value: unknown): NormalizedSection['severity'] => {
  return typeof value === 'string' && knownSeverities.has(value as ConfigAnalysisSeveritySection['severity'])
    ? (value as ConfigAnalysisSeveritySection['severity'])
    : 'unknown';
};

const formatCount = (value?: number) => (typeof value === 'number' && Number.isFinite(value) ? value : '--');

const normalizeItems = (section: Record<string, unknown>): { items: NormalizedIssue[]; degraded: boolean } => {
  const source = Array.isArray(section.issues)
    ? section.issues
    : Array.isArray(section.items)
      ? section.items
      : [];

  if (!Array.isArray(source) || source.length === 0) {
    return { items: [], degraded: true };
  }

  const items = source
    .map((item): NormalizedIssue | null => {
      if (!item || typeof item !== 'object') {
        return null;
      }

      const itemRecord = item as Record<string, unknown>;
      const issue = typeof itemRecord.issue === 'string' ? itemRecord.issue.trim() : '';
      if (!issue) {
        return null;
      }

      const workloads = Array.isArray(itemRecord.workloads)
        ? itemRecord.workloads.filter((workload): workload is string => typeof workload === 'string' && workload.trim().length > 0)
        : [];
      const count = typeof itemRecord.count === 'number' && Number.isFinite(itemRecord.count) ? itemRecord.count : 0;
      const risk = typeof itemRecord.risk === 'string' && itemRecord.risk.trim().length > 0
        ? itemRecord.risk
        : '信息不完整，风险说明暂缺。';
      const degraded = !Array.isArray(itemRecord.workloads) || workloads.length !== itemRecord.workloads.length;

      return {
        issue,
        count,
        workloads,
        risk,
        degraded,
      };
    })
    .filter((item): item is NormalizedIssue => Boolean(item));

  return {
    items,
    degraded: items.length !== source.length,
  };
};

const normalizeSection = (section: unknown, index: number): NormalizedSection | null => {
  if (!section || typeof section !== 'object') {
    return null;
  }

  const sectionRecord = section as Record<string, unknown>;
  const title = typeof sectionRecord.title === 'string' && sectionRecord.title.trim().length > 0
    ? sectionRecord.title.trim()
    : `问题分组 ${index + 1}`;
  const severity = normalizeSeverity(sectionRecord.severity);
  const { items, degraded: itemsDegraded } = normalizeItems(sectionRecord);
  const degraded = severity === 'unknown' || itemsDegraded || !Array.isArray(sectionRecord.issues) && !Array.isArray(sectionRecord.items);

  return {
    severity,
    title,
    issues: items,
    degraded,
  };
};

const ConfigAnalysisReportCard: React.FC<ConfigAnalysisReportCardProps> = ({ report }) => {
  const severitySections = Array.isArray(report.severity_sections)
    ? report.severity_sections
      .map(normalizeSection)
      .filter((section): section is NormalizedSection => Boolean(section))
    : [];
  const recommendationRows = Array.isArray(report.recommendations) ? report.recommendations : [];
  const problematicCount = typeof report.summary.problematic === 'number' && Number.isFinite(report.summary.problematic)
    ? report.summary.problematic
    : 0;
  const hasIssues = severitySections.length > 0 || problematicCount > 0;
  const hasIssueDetails = severitySections.length > 0 || recommendationRows.length > 0;
  const degradedCount = severitySections.filter(section => section.degraded).length;
  const summaryText =
    report.summary.top_recommendation?.trim() ||
    (hasIssues
      ? '当前报告返回了问题统计，但结构化明细暂未返回，请结合原始扫描结果继续排查。'
      : '当前扫描结果未发现明显风险，暂无额外修复建议。');
  const scopeItems = [
    report.scope?.cluster_name || report.cluster_name,
    report.scope?.namespace ? `命名空间：${report.scope.namespace}` : null,
    report.scope?.instance_name ? `实例：${report.scope.instance_name}` : null,
    report.scope?.target_name
      ? `对象：${report.scope.target_name}`
      : report.scope?.name
        ? `对象：${report.scope.name}`
        : null,
  ].filter(Boolean);
  const hasScanRange = typeof report.scan_range?.offset === 'number' && typeof report.scan_range?.limit === 'number';
  const scanRangeStart = hasScanRange ? report.scan_range!.offset! + 1 : null;
  const scanRangeEnd = hasScanRange ? report.scan_range!.offset! + report.scan_range!.limit! : null;

  return (
    <section className="mt-3 max-w-[720px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-200 bg-gradient-to-r from-sky-50 via-white to-white px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-700">
            配置分析
          </span>
          <h3 className="text-sm font-semibold text-slate-900">{report.title}</h3>
          <span className="ml-auto rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
            {report.cluster_name}
          </span>
        </div>
        {scopeItems.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
            {scopeItems.map(item => (
              <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1">
                {item}
              </span>
            ))}
          </div>
        )}
      </header>

      <div className="space-y-4 px-4 py-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            { label: '扫描对象', value: formatCount(report.summary.total), tone: 'text-slate-900' },
            { label: '发现问题', value: formatCount(report.summary.problematic), tone: 'text-rose-600' },
            { label: '健康对象', value: formatCount(report.summary.healthy), tone: 'text-emerald-600' },
          ].map(card => (
            <div key={card.label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
              <div className="text-xs text-slate-500">{card.label}</div>
              <div className={`mt-1 text-2xl font-semibold ${card.tone}`}>{card.value}</div>
            </div>
          ))}
        </div>

        <div className="rounded-xl border border-sky-100 bg-sky-50 px-3 py-3 text-sm text-slate-700">
          <div className="text-xs font-medium uppercase tracking-wide text-sky-700">建议摘要</div>
          <div className="mt-1">{summaryText}</div>
          {hasScanRange && report.scan_range?.has_more && (
            <div className="mt-2 text-xs text-sky-700">
              当前展示第 {scanRangeStart} - {scanRangeEnd} 项结果，仍有更多对象待继续检查。
            </div>
          )}
        </div>

        {degradedCount > 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
            结构化明细存在不完整字段，已自动跳过异常分组并降级展示。
          </div>
        )}

        {!hasIssues ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4">
            <div className="text-sm font-semibold text-emerald-700">未发现明显配置问题</div>
            <div className="mt-1 text-sm text-emerald-700/80">
              当前扫描范围内的工作负载配置表现正常，可继续按需巡检。
            </div>
          </div>
        ) : !hasIssueDetails ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4">
            <div className="text-sm font-semibold text-amber-800">已发现配置问题，但明细暂不可用</div>
            <div className="mt-1 text-sm text-amber-800/80">
              当前报告仅返回问题统计，详细分项尚未提供，请结合原始扫描结果继续排查。
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {severitySections.map(section => {
              const style = severityStyles[section.severity];

              return (
                <div key={`${report.report_id}-${section.severity}`} className={`overflow-hidden rounded-xl border ${style.border}`}>
                  <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${style.badge}`}>
                      {style.text}
                    </span>
                    <span className="text-sm font-medium text-slate-800">{section.title}</span>
                    <span className="ml-auto text-xs text-slate-500">问题类别</span>
                  </div>
                  <div className="overflow-x-auto">
                    {section.issues.length > 0 ? (
                      <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                        <thead className="bg-white text-slate-500">
                          <tr>
                            <th className="px-3 py-2 font-medium">问题类别</th>
                            <th className="px-3 py-2 font-medium">影响数量</th>
                            <th className="px-3 py-2 font-medium">涉及工作负载</th>
                            <th className="px-3 py-2 font-medium">风险说明</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                          {section.issues.map((item, idx) => (
                            <tr key={`${section.severity}-${item.issue}-${idx}`}>
                              <td className="px-3 py-3 font-medium text-slate-800">
                                <div className="flex items-center gap-2">
                                  <span>{item.issue}</span>
                                  {item.degraded && (
                                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                                      信息不完整
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="px-3 py-3">{item.count}</td>
                              <td className="px-3 py-3">
                                {item.workloads.length > 0 ? (
                                  <div className="flex flex-wrap gap-1.5">
                                    {item.workloads.map(workload => (
                                      <span
                                        key={workload}
                                        className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600"
                                      >
                                        {workload}
                                      </span>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-slate-400">—</span>
                                )}
                              </td>
                              <td className="px-3 py-3 text-slate-600">{item.risk}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="px-3 py-3 text-sm text-slate-500">
                        当前分组缺少完整的问题明细，已保留分组标题以便继续排查原始结果。
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {recommendationRows.length > 0 && (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <div className="border-b border-slate-200 bg-slate-50 px-3 py-3 text-sm font-medium text-slate-800">
                  修复建议
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                    <thead className="bg-white text-slate-500">
                      <tr>
                        <th className="px-3 py-2 font-medium">优先级</th>
                        <th className="px-3 py-2 font-medium">建议动作</th>
                        <th className="px-3 py-2 font-medium">目标范围</th>
                        <th className="px-3 py-2 font-medium">预期收益</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                      {recommendationRows.map(row => (
                        <tr key={`${row.priority}-${row.action}`}>
                          <td className="px-3 py-3">
                            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                              {row.priority}
                            </span>
                          </td>
                          <td className="px-3 py-3 font-medium text-slate-800">{row.action}</td>
                          <td className="px-3 py-3">{row.target}</td>
                          <td className="px-3 py-3 text-slate-600">{row.benefit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
};

export default ConfigAnalysisReportCard;
