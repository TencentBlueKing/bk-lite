'use client';

import React, { useEffect, useState } from 'react';
import { Modal, Tag } from 'antd';
import { FileTextOutlined, RightOutlined } from '@ant-design/icons';
import { ConfigDiffReport, ConfigDiffItem } from './types';
import { getDiffReportItemPresentation } from './diffReportItemPresentation';
import useApiClient, { isSilentRequestError } from './host';
import { useTranslation } from './host';
import { buildLiveYamlRequest } from './liveYamlRequest';

type DiffOp = 'equal' | 'add' | 'remove';
interface DiffLine { op: DiffOp; text: string; leftNo?: number; rightNo?: number }

/** 简单 LCS 行级 diff,够 YAML 这种小片段用;不引入 diff 库避免 bundle 膨胀。 */
function computeLineDiff(before: string, after: string): { left: DiffLine[]; right: DiffLine[] } {
  const a = before.split('\n');
  const b = after.split('\n');
  const n = a.length;
  const m = b.length;
  // dp[i][j] = LCS 长度
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const left: DiffLine[] = [];
  const right: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      left.push({ op: 'equal', text: a[i], leftNo: i + 1, rightNo: j + 1 });
      right.push({ op: 'equal', text: b[j], leftNo: i + 1, rightNo: j + 1 });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      left.push({ op: 'remove', text: a[i], leftNo: i + 1 });
      i++;
    } else {
      right.push({ op: 'add', text: b[j], rightNo: j + 1 });
      j++;
    }
  }
  while (i < n) {
    left.push({ op: 'remove', text: a[i], leftNo: i + 1 });
    i++;
  }
  while (j < m) {
    right.push({ op: 'add', text: b[j], rightNo: j + 1 });
    j++;
  }
  return { left, right };
}

interface DiffReportCardProps {
  report: ConfigDiffReport;
}

const DiffReportCard: React.FC<DiffReportCardProps> = ({ report }) => {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const [selectedItem, setSelectedItem] = useState<ConfigDiffItem | null>(null);
  const [fetchedYaml, setFetchedYaml] = useState<{ yaml: string; loading: boolean; error: string | null }>({
    yaml: '',
    loading: false,
    error: null,
  });

  // modal 一开就自动 fetch,没 skill_id 就跳过
  useEffect(() => {
    if (!selectedItem) return;
    const liveYamlRequest = buildLiveYamlRequest(report, selectedItem, t);
    if (!liveYamlRequest) return;
    if (liveYamlRequest.kind === 'unavailable') {
      setFetchedYaml({ yaml: '', loading: false, error: liveYamlRequest.message });
      return;
    }

    let cancelled = false;
    setFetchedYaml({ yaml: '', loading: true, error: null });
    (async () => {
      try {
        const data = await post<{ yaml: string }>(liveYamlRequest.endpoint, liveYamlRequest.payload);
        if (!cancelled) {
          setFetchedYaml({ yaml: data.yaml, loading: false, error: null });
        }
      } catch (error: unknown) {
        if (!cancelled) {
          const errorMessage = isSilentRequestError(error)
            ? null
            : error instanceof Error ? error.message : 'network error';
          setFetchedYaml({ yaml: '', loading: false, error: errorMessage });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [post, report, selectedItem]);
  const a2uiComponent = report.a2ui?.component || 'config-diff-report';
  const a2uiVersion = report.a2ui?.version || 'legacy';
  const selectedPresentation = selectedItem ? getDiffReportItemPresentation(selectedItem, t) : null;

  return (
    <div
      className="mt-3 w-full max-w-full overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-sm"
      data-a2ui-component={a2uiComponent}
      data-a2ui-version={a2uiVersion}
      data-a2ui-event={report.a2ui?.event_name || 'repair_diff_report'}
    >
      {/* Header */}
      <div className="px-4 py-3    border-b border-[var(--color-border-1)] flex items-center gap-2">
        <FileTextOutlined className="text-[var(--color-primary)] text-base" />
        <span className="font-semibold text-sm text-[var(--color-text-2)]">{report.title}</span>
        <Tag className="ml-auto !mb-0" color="blue">{report.cluster_name}</Tag>
      </div>

      {/* Items */}
      <div className="divide-y divide-gray-100">
        {report.items.map((item, idx) => {
          const presentation = getDiffReportItemPresentation(item, t);
          const isAllMode = item.workload_type.trim().toLowerCase() === 'all';
          return (
            <div
              key={idx}
              className="px-4 py-3 cursor-pointer hover:bg-[var(--color-fill-1)]/50 transition-colors group"
              onClick={() => setSelectedItem(item)}
            >
              <div className="flex items-center gap-2">
                <Tag color={presentation.badgeTone} className="!m-0 text-xs">{presentation.badgeLabel}</Tag>
                <span className="text-sm font-medium text-[var(--color-text-2)] font-mono">
                  {presentation.targetLabel}
                </span>
                {!isAllMode && (
                  <span className="text-xs text-[var(--color-text-2)] shrink-0">
                    {item.workload_type}
                  </span>
                )}
                {presentation.riskLabel && (
                  <span className="text-xs text-[var(--color-text-2)] shrink-0">{presentation.riskLabel}</span>
                )}
                <RightOutlined className="ml-auto text-[var(--color-text-2)] text-xs group-hover:text-[var(--color-primary)] transition-colors" />
              </div>
              <div className="mt-1.5 ml-[52px] text-xs text-[var(--color-text-2)] leading-relaxed">
                {item.summary}
              </div>
            </div>
          );
        })}
      </div>

      {/* Diff Modal */}
      <Modal
        open={!!selectedItem}
        onCancel={() => setSelectedItem(null)}
        title={
          selectedPresentation && (
            <div className="flex items-center gap-2">
              <Tag color={selectedPresentation.badgeTone}>{selectedPresentation.badgeLabel}</Tag>
              <span className="font-medium">{selectedPresentation.targetLabel}</span>
              {selectedPresentation.riskLabel && (
                <span className="text-[var(--color-text-2)] text-sm font-normal">({selectedPresentation.riskLabel})</span>
              )}
            </div>
          )
        }
        footer={null}
        width="90vw"
        zIndex={10010}
        styles={{ body: { padding: 0, maxHeight: '70vh', overflow: 'auto' } }}
      >
        {selectedItem && (() => {
          // before / after 算 LCS 行 diff,只对有 YAML 内容的才做(纯文字的退化)
          const beforeYaml = (selectedItem.before_yaml || '').trim();
          const afterYaml = (selectedItem.after_yaml || '').trim();
          const looksLikeYaml = beforeYaml.includes(':') || afterYaml.includes(':');
          const diff = looksLikeYaml
            ? computeLineDiff(beforeYaml || t('chat.diffReport.emptyLine'), afterYaml || t('chat.diffReport.emptyLine'))
            : null;
          return (
            <div>
              <div className="px-4 py-3 bg-[var(--color-fill-1)]/50 border-b border-[var(--color-border-1)]">
                <div className="text-sm font-medium text-[var(--color-text-2)]">
                  {selectedItem.summary}
                </div>
                <div className="mt-1 text-xs text-[var(--color-text-2)]">
                  {selectedItem.namespace} / {selectedItem.workload_name} ({selectedItem.workload_type})
                </div>
              </div>
              {/* 配置修改对比 — 并排两列,行级 diff 高亮(新增绿、删除红) */}
              {diff && (
                <div className="px-4 py-3 border-b border-[var(--color-border-1)]">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="inline-flex h-6 items-center rounded-md bg-[var(--color-fill-1)] px-2 text-xs font-medium text-[var(--color-primary)] border border-[var(--color-border-1)]">
                      {t('chat.diffReport.title')}
                    </span>
                    <span className="text-xs text-[var(--color-text-2)]">
                      <span className="inline-block w-3 h-3 bg-[var(--color-fill-1)] border border-[var(--color-border-1)] mr-1 align-middle" />
                      {t('chat.diffReport.removed')}
                      <span className="inline-block w-3 h-3 bg-[var(--color-fill-1)] border border-[var(--color-border-1)] mx-1 ml-2 align-middle" />
                      {t('chat.diffReport.added')}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-md border border-[var(--color-border-1)] overflow-hidden">
                      <div className="px-3 py-1.5 bg-[var(--color-fill-1)]/60 border-b border-[var(--color-border-1)] text-xs font-medium text-[var(--color-primary)]">
                        {t('chat.diffReport.before')}
                      </div>
                      <pre className="m-0 p-3 text-xs font-mono leading-5 text-[var(--color-text-2)] overflow-x-auto bg-[var(--color-bg)]">
                        {diff.left.map((line, idx) => (
                          <div
                            key={`l-${idx}`}
                            className={
                              line.op === 'remove'
                                ? 'bg-[var(--color-fill-1)] text-[var(--color-primary)] -mx-3 px-3'
                                : 'text-[var(--color-text-2)]'
                            }
                          >
                            <span className="inline-block w-8 text-right pr-2 text-[var(--color-text-2)] select-none">
                              {line.leftNo || ''}
                            </span>
                            <span className="text-[var(--color-text-2)] select-none mr-1">
                              {line.op === 'remove' ? '-' : ' '}
                            </span>
                            {line.text || ' '}
                          </div>
                        ))}
                      </pre>
                    </div>
                    <div className="rounded-md border border-[var(--color-border-1)] overflow-hidden">
                      <div className="px-3 py-1.5 bg-[var(--color-fill-1)]/60 border-b border-[var(--color-border-1)] text-xs font-medium text-[var(--color-primary)]">
                        {t('chat.diffReport.after')}
                      </div>
                      <pre className="m-0 p-3 text-xs font-mono leading-5 text-[var(--color-text-2)] overflow-x-auto bg-[var(--color-bg)]">
                        {diff.right.map((line, idx) => (
                          <div
                            key={`r-${idx}`}
                            className={
                              line.op === 'add'
                                ? 'bg-[var(--color-fill-1)] text-[var(--color-primary)] -mx-3 px-3'
                                : 'text-[var(--color-text-2)]'
                            }
                          >
                            <span className="inline-block w-8 text-right pr-2 text-[var(--color-text-2)] select-none">
                              {line.rightNo || ''}
                            </span>
                            <span className="text-[var(--color-text-2)] select-none mr-1">
                              {line.op === 'add' ? '+' : ' '}
                            </span>
                            {line.text || ' '}
                          </div>
                        ))}
                      </pre>
                    </div>
                  </div>
                </div>
              )}
              {/* 文字说明兜底:非 YAML 的旧数据走文字版 */}
              {!diff && selectedItem.fix_description && (
                <div className="px-4 py-3 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/30">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="inline-flex h-6 items-center rounded-md bg-[var(--color-fill-1)] px-2 text-xs font-medium text-[var(--color-primary)] border border-[var(--color-border-1)]">
                      {t('chat.diffReport.fixSuggestion')}
                    </span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words rounded-md bg-[var(--color-bg)] border border-[var(--color-border-1)] p-3 text-sm text-[var(--color-text-2)]">
                    {selectedItem.fix_description}
                  </pre>
                </div>
              )}
              {/* 真实 deployment YAML — modal 一开就自动 fetch,不再多点 */}
              {(report.skill_id || selectedItem.skill_id) && (
                <div className="px-4 py-3 border-t border-[var(--color-border-1)] bg-[var(--color-fill-1)]">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="inline-flex h-6 items-center rounded-md bg-[var(--color-fill-1)] px-2 text-xs font-medium text-[var(--color-text-2)] border border-[var(--color-border-1)]">
                      {t('chat.diffReport.liveYaml')}
                    </span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words rounded-md bg-[var(--color-bg)] border border-[var(--color-border-1)] p-3 text-xs font-mono text-[var(--color-text-2)] max-h-80 overflow-auto">
                    {fetchedYaml.loading
                      ? t('chat.diffReport.loading')
                      : fetchedYaml.error || fetchedYaml.yaml || t('chat.diffReport.loadFailed')}
                  </pre>
                </div>
              )}
            </div>
          );
        })()}
      </Modal>
    </div>
  );
};

export default DiffReportCard;
