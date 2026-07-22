'use client';

import React, { useEffect, useState } from 'react';
import { Modal, Tag } from 'antd';
import { FileTextOutlined, RightOutlined } from '@ant-design/icons';
import { ConfigDiffReport, ConfigDiffItem } from '@/app/opspilot/types/global';

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

const severityConfig = {
  critical: { color: '#f5222d', label: '严重', tagColor: 'error' },
  high: { color: '#fa541c', label: '高危', tagColor: 'volcano' },
  medium: { color: '#fa8c16', label: '中风险', tagColor: 'warning' },
  low: { color: '#52c41a', label: '低风险', tagColor: 'success' },
  warning: { color: '#fa8c16', label: '警告', tagColor: 'warning' },
  info: { color: '#1890ff', label: '提示', tagColor: 'processing' },
} as const;

// 防御:severity 字段值不在预设里就 fallback 到 info,避免 sev.tagColor 报错
const getSeverity = (s: string | undefined) => severityConfig[s as keyof typeof severityConfig] ?? severityConfig.info;

const DiffReportCard: React.FC<DiffReportCardProps> = ({ report }) => {
  const [selectedItem, setSelectedItem] = useState<ConfigDiffItem | null>(null);
  const [fetchedYaml, setFetchedYaml] = useState<{ yaml: string; loading: boolean; error: string | null }>({
    yaml: '',
    loading: false,
    error: null,
  });

  // modal 一开就自动 fetch,没 skill_id 就跳过
  useEffect(() => {
    if (!selectedItem?.skill_id) return;
    setFetchedYaml({ yaml: '', loading: true, error: null });
    (async () => {
      try {
        const token = localStorage.getItem('access_token') ||
          document.cookie.split('; ').find(c => c.startsWith('access_token='))?.split('=')[1] || '';
        const apiBase = (window as any).__NEXT_DATA__?.props?.pageProps?.apiBase
          || window.location.origin;
        const res = await fetch(`${apiBase}/api/proxy/opspilot/model_provider_mgmt/llm/fetch_k8s_deployment_yaml/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({
            namespace: selectedItem.namespace === 'all' ? '' : selectedItem.namespace,
            name: selectedItem.workload_name.split(' ')[0],
            cluster_name: report.cluster_name,
            skill_id: selectedItem.skill_id,
          }),
        });
        const json = await res.json();
        if (json.result && json.data?.yaml) {
          setFetchedYaml({ yaml: json.data.yaml, loading: false, error: null });
        } else {
          setFetchedYaml({ yaml: '', loading: false, error: json.message || 'fetch failed' });
        }
      } catch (e: any) {
        setFetchedYaml({ yaml: '', loading: false, error: e?.message || 'network error' });
      }
    })();
  }, [selectedItem?.skill_id, selectedItem?.namespace, selectedItem?.workload_name, report.cluster_name]);
  const a2uiComponent = report.a2ui?.component || 'config-diff-report';
  const a2uiVersion = report.a2ui?.version || 'legacy';

  return (
    <div
      className="mt-3 w-full max-w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
      data-a2ui-component={a2uiComponent}
      data-a2ui-version={a2uiVersion}
      data-a2ui-event={report.a2ui?.event_name || 'repair_diff_report'}
    >
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-blue-50 to-white border-b border-gray-200 flex items-center gap-2">
        <FileTextOutlined className="text-blue-500 text-base" />
        <span className="font-semibold text-sm text-gray-800">{report.title}</span>
        <Tag className="ml-auto !mb-0" color="blue">{report.cluster_name}</Tag>
      </div>

      {/* Items */}
      <div className="divide-y divide-gray-100">
        {report.items.map((item, idx) => {
          const sev = getSeverity(item.severity);
          return (
            <div
              key={idx}
              className="px-4 py-3 cursor-pointer hover:bg-blue-50/50 transition-colors group"
              onClick={() => setSelectedItem(item)}
            >
              <div className="flex items-center gap-2">
                <Tag color={sev.tagColor} className="!m-0 text-xs">{sev.label}</Tag>
                <span className="text-sm font-medium text-gray-800 font-mono">
                  {item.namespace}/{item.workload_name}
                </span>
                <span className="text-xs text-gray-400 shrink-0">
                  {item.workload_type}
                </span>
                <RightOutlined className="ml-auto text-gray-300 text-xs group-hover:text-blue-400 transition-colors" />
              </div>
              <div className="mt-1.5 ml-[52px] text-xs text-gray-500 leading-relaxed">
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
          selectedItem && (
            <div className="flex items-center gap-2">
              <Tag color={getSeverity(selectedItem.severity).tagColor}>
                {getSeverity(selectedItem.severity).label}
              </Tag>
              <span className="font-medium">{selectedItem.namespace}/{selectedItem.workload_name}</span>
              <span className="text-gray-400 text-sm font-normal">({selectedItem.workload_type})</span>
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
            ? computeLineDiff(beforeYaml || '# (空)', afterYaml || '# (空)')
            : null;
          return (
            <div>
              <div className="px-4 py-3 bg-blue-50/50 border-b border-blue-100">
                <div className="text-sm font-medium text-gray-800">
                  {selectedItem.summary}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {selectedItem.namespace} / {selectedItem.workload_name} ({selectedItem.workload_type})
                </div>
              </div>
              {/* 配置修改对比 — 并排两列,行级 diff 高亮(新增绿、删除红) */}
              {diff && (
                <div className="px-4 py-3 border-b border-gray-100">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="inline-flex h-6 items-center rounded-md bg-blue-100 px-2 text-xs font-medium text-blue-700 border border-blue-200">
                      配置修改对比
                    </span>
                    <span className="text-xs text-gray-500">
                      <span className="inline-block w-3 h-3 bg-red-100 border border-red-300 mr-1 align-middle" />
                      删除
                      <span className="inline-block w-3 h-3 bg-green-100 border border-green-300 mx-1 ml-2 align-middle" />
                      新增
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-md border border-gray-200 overflow-hidden">
                      <div className="px-3 py-1.5 bg-red-50/60 border-b border-gray-200 text-xs font-medium text-red-700">
                        修改前 (Before)
                      </div>
                      <pre className="m-0 p-3 text-xs font-mono leading-5 text-gray-800 overflow-x-auto bg-white">
                        {diff.left.map((line, idx) => (
                          <div
                            key={`l-${idx}`}
                            className={
                              line.op === 'remove'
                                ? 'bg-red-50 text-red-900 -mx-3 px-3'
                                : 'text-gray-700'
                            }
                          >
                            <span className="inline-block w-8 text-right pr-2 text-gray-400 select-none">
                              {line.leftNo || ''}
                            </span>
                            <span className="text-gray-400 select-none mr-1">
                              {line.op === 'remove' ? '-' : ' '}
                            </span>
                            {line.text || ' '}
                          </div>
                        ))}
                      </pre>
                    </div>
                    <div className="rounded-md border border-gray-200 overflow-hidden">
                      <div className="px-3 py-1.5 bg-green-50/60 border-b border-gray-200 text-xs font-medium text-green-700">
                        修改后 (After)
                      </div>
                      <pre className="m-0 p-3 text-xs font-mono leading-5 text-gray-800 overflow-x-auto bg-white">
                        {diff.right.map((line, idx) => (
                          <div
                            key={`r-${idx}`}
                            className={
                              line.op === 'add'
                                ? 'bg-green-50 text-green-900 -mx-3 px-3'
                                : 'text-gray-700'
                            }
                          >
                            <span className="inline-block w-8 text-right pr-2 text-gray-400 select-none">
                              {line.rightNo || ''}
                            </span>
                            <span className="text-gray-400 select-none mr-1">
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
                <div className="px-4 py-3 border-b border-gray-100 bg-green-50/30">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="inline-flex h-6 items-center rounded-md bg-green-100 px-2 text-xs font-medium text-green-700 border border-green-200">
                      ✅ 修复建议
                    </span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words rounded-md bg-white border border-green-200 p-3 text-sm text-gray-800">
                    {selectedItem.fix_description}
                  </pre>
                </div>
              )}
              {/* 真实 deployment YAML — modal 一开就自动 fetch,不再多点 */}
              {selectedItem.skill_id && (
                <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="inline-flex h-6 items-center rounded-md bg-gray-100 px-2 text-xs font-medium text-gray-700 border border-gray-200">
                      当前 deployment YAML(集群实际状态)
                    </span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words rounded-md bg-white border border-gray-200 p-3 text-xs font-mono text-gray-700 max-h-80 overflow-auto">
                    {fetchedYaml.loading ? '加载中...'
                    : fetchedYaml.error || fetchedYaml.yaml || '加载失败,请重试'}
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
