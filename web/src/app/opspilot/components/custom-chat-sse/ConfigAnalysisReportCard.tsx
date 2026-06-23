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
const WORKLOAD_PREVIEW_LIMIT = 5;

interface NormalizedIssue extends ConfigAnalysisReportItem {
  degraded?: boolean;
}

interface NormalizedSection {
  severity: ConfigAnalysisSeveritySection['severity'] | 'unknown';
  title: string;
  issues: NormalizedIssue[];
  degraded: boolean;
}

interface NormalizedRecommendation {
  priority: 'P0' | 'P1' | 'P2' | 'P3';
  action: string;
  target: string;
  benefit: string;
}

const recommendationPriorityStyles: Record<NormalizedRecommendation['priority'], string> = {
  P0: 'border-rose-200 bg-rose-100 text-rose-700',
  P1: 'border-orange-200 bg-orange-100 text-orange-700',
  P2: 'border-amber-200 bg-amber-100 text-amber-700',
  P3: 'border-sky-200 bg-sky-100 text-sky-700',
};

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
      : null;

  if (!source) {
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

const normalizeRecommendations = (recommendations: unknown): NormalizedRecommendation[] => {
  if (!Array.isArray(recommendations)) {
    return [];
  }

  return recommendations
    .map((recommendation): NormalizedRecommendation | null => {
      if (!recommendation || typeof recommendation !== 'object') {
        return null;
      }

      const recommendationRecord = recommendation as Record<string, unknown>;
      const priority = typeof recommendationRecord.priority === 'string' && ['P0', 'P1', 'P2', 'P3'].includes(recommendationRecord.priority)
        ? recommendationRecord.priority as NormalizedRecommendation['priority']
        : null;
      const action = typeof recommendationRecord.action === 'string' ? recommendationRecord.action.trim() : '';
      const target = typeof recommendationRecord.target === 'string' ? recommendationRecord.target.trim() : '';
      const benefit = typeof recommendationRecord.benefit === 'string' ? recommendationRecord.benefit.trim() : '';

      if (!priority || !action || !target || !benefit) {
        return null;
      }

      return {
        priority,
        action,
        target,
        benefit,
      };
    })
    .filter((recommendation): recommendation is NormalizedRecommendation => Boolean(recommendation));
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
  const a2uiComponent = report.a2ui?.component || 'config-analysis-report';
  const a2uiVersion = report.a2ui?.version || 'legacy';
  const severitySections = Array.isArray(report.severity_sections)
    ? report.severity_sections
      .map(normalizeSection)
      .filter((section): section is NormalizedSection => Boolean(section))
    : [];
  const recommendationRows = normalizeRecommendations(report.recommendations);
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
    <section
      className="mt-3 w-full max-w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
      data-a2ui-component={a2uiComponent}
      data-a2ui-version={a2uiVersion}
      data-a2ui-event={report.a2ui?.event_name || 'config_analysis_report'}
    >
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
                      <table className="w-full min-w-[760px] table-fixed divide-y divide-slate-200 text-left text-xs">
                        <colgroup>
                          <col className="w-[22%]" />
                          <col className="w-[10%]" />
                          <col className="w-[40%]" />
                          <col className="w-[28%]" />
                        </colgroup>
                        <thead className="bg-white text-slate-500">
                          <tr>
                            <th className="px-3 py-2 font-medium">问题类别</th>
                            <th className="px-3 py-2 font-medium">影响数量</th>
                            <th className="px-3 py-2 font-medium">涉及工作负载</th>
                            <th className="px-3 py-2 font-medium">风险说明</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                          {section.issues.map((item, idx) => {
                            const visibleWorkloads = item.workloads.slice(0, WORKLOAD_PREVIEW_LIMIT);
                            const hiddenWorkloadCount = Math.max(item.workloads.length - WORKLOAD_PREVIEW_LIMIT, 0);

                            return (
                              <tr key={`${section.severity}-${item.issue}-${idx}`} className="align-top">
                                <td className="px-3 py-2.5 font-medium leading-5 text-slate-800">
                                  <div className="flex items-center gap-2">
                                    <span>{item.issue}</span>
                                    {item.degraded && (
                                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                                        信息不完整
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-3 py-2.5 leading-5">{item.count}</td>
                                <td className="px-3 py-2.5">
                                  {visibleWorkloads.length > 0 ? (
                                    <div className="flex max-w-full flex-wrap gap-1.5">
                                      {visibleWorkloads.map(workload => (
                                        <span
                                          key={workload}
                                          title={workload}
                                          className="max-w-[180px] truncate rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600"
                                        >
                                          {workload}
                                        </span>
                                      ))}
                                      {hiddenWorkloadCount > 0 && (
                                        <span
                                          title={`另有 ${hiddenWorkloadCount} 个工作负载`}
                                          className="rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-500"
                                        >
                                          +{hiddenWorkloadCount}
                                        </span>
                                      )}
                                    </div>
                                  ) : (
                                    <span className="text-slate-400">—</span>
                                  )}
                                </td>
                                <td className="px-3 py-2.5 leading-5 text-slate-600">{item.risk}</td>
                              </tr>
                            );
                          })}
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
                  <table className="w-full min-w-[760px] table-fixed divide-y divide-slate-200 text-left text-xs">
                    <colgroup>
                      <col className="w-[88px]" />
                      <col className="w-[42%]" />
                      <col className="w-[22%]" />
                      <col />
                    </colgroup>
                    <thead className="bg-white text-slate-500">
                      <tr>
                        <th className="px-4 py-2 font-medium">优先级</th>
                        <th className="px-3 py-2 font-medium">建议动作</th>
                        <th className="px-3 py-2 font-medium">目标范围</th>
                        <th className="px-3 py-2 font-medium">预期收益</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                      {recommendationRows.map(row => {
                        const priorityStyle = recommendationPriorityStyles[row.priority];

                        return (
                          <tr key={`${row.priority}-${row.action}`} className="align-top">
                            <td className="px-4 py-2.5">
                              <span className={`inline-flex h-7 min-w-10 items-center justify-center whitespace-nowrap rounded-full border px-2.5 text-xs font-semibold ${priorityStyle}`}>
                                {row.priority}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 font-medium leading-5 text-slate-800">{row.action}</td>
                            <td className="px-3 py-2.5 leading-5 text-slate-700">{row.target}</td>
                            <td className="px-3 py-2.5 leading-5 text-slate-600">{row.benefit}</td>
                          </tr>
                        );
                      })}
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
