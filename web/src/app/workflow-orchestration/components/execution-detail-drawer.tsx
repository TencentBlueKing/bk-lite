'use client';

import { DownloadOutlined, ReloadOutlined, RightOutlined } from '@ant-design/icons';
import { Alert, App, Button, Descriptions, Empty, Input, Popconfirm, Spin, Tag } from 'antd';
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import OperateDrawer from '@/components/operate-drawer';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { executionStatusPresentation, formatDuration, formatStartedBy, formatTriggerTypeLabel, presentExecutionInfoItem, formatJson } from '../lib/presentation';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import type { ExecutionArtifactRecord, ExecutionNodeDetail, ExecutionNodeSummary, ExecutionNodesResponse, ExecutionRecord } from '../lib/types';
import { ExecutionLifecycleActions } from './execution-lifecycle-actions';
import { WorkflowLaunchDialog } from './workflow-launch-dialog';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';
const ACTIVE = new Set(['QUEUED', 'RUNNING', 'WAITING_APPROVAL', 'TERMINATING']);

const NODE_LABEL_DEFAULTS: Record<ExecutionNodeSummary['state'], string> = {
  ACTIONABLE: '待我处理',
  FAILED: '失败',
  TIMED_OUT: '已超时',
  RUNNING: '运行中',
  WAITING: '等待审批',
  WARNING: '有告警',
  SUCCESS: '成功',
  SKIPPED: '已跳过',
  UNREACHABLE: '未到达',
  PENDING: '未开始',
};

function nodeLabel(state: ExecutionNodeSummary['state'], t: (id: string, defaultMessage?: string) => string) {
  return t(`workflowOrchestration.node.state.${state}`, NODE_LABEL_DEFAULTS[state]);
}

function isUserVisibleNode(node: ExecutionNodeSummary): boolean {
  return node.task_type !== 'END' && !(node.task_type === 'SWITCH' && node.task_name === 'approval_decision');
}

const NODE_COLORS: Partial<Record<ExecutionNodeSummary['state'], string>> = {
  ACTIONABLE: 'error',
  FAILED: 'error',
  TIMED_OUT: 'error',
  RUNNING: 'processing',
  WAITING: 'warning',
  WARNING: 'warning',
  SUCCESS: 'success',
};

const NODE_ACCENTS: Record<ExecutionNodeSummary['state'], string> = {
  ACTIONABLE: 'var(--color-fail)',
  FAILED: 'var(--color-fail)',
  TIMED_OUT: 'var(--color-fail)',
  RUNNING: 'var(--color-primary)',
  WAITING: 'var(--color-warning)',
  WARNING: 'var(--color-warning)',
  SUCCESS: 'var(--color-success)',
  SKIPPED: 'var(--color-border-3)',
  UNREACHABLE: 'var(--color-border-3)',
  PENDING: 'var(--color-border-3)',
};

function JsonEvidence({ title, value }: { title: string; value: Record<string, unknown> }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const contentId = useId();
  const hasValue = Object.keys(value).length > 0;

  return (
    <section aria-label={t('workflowOrchestration.node.sectionDetails', '{title}详情', { title })} className="flex w-full min-w-0 max-w-full flex-col gap-3">
      <h3 className="m-0">
        <WorkflowPermission operation="View" area="executions" className="block w-full"><button
          type="button"
          aria-controls={contentId}
          aria-expanded={expanded}
          aria-label={t('workflowOrchestration.node.toggleSection', '{action}{title}', { action: expanded ? t('common.collapse', '折叠') : t('common.expand', '展开'), title })}
          className="flex min-h-10 w-full cursor-pointer items-center gap-2 rounded px-1 text-left text-sm font-medium text-[var(--color-text-1)] transition-colors duration-150 hover:bg-[var(--color-bg-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          onClick={() => setExpanded((current) => !current)}
        >
          <RightOutlined aria-hidden className={`text-xs text-[var(--color-text-3)] transition-transform duration-150 ${expanded ? 'rotate-90' : ''}`} />
          <span>{title}</span>
        </button></WorkflowPermission>
      </h3>
      {expanded ? (
        <div id={contentId} className="w-full min-w-0 max-w-full">
          {hasValue ? (
            <pre className="m-0 box-border block w-full max-w-full overflow-x-auto rounded-md bg-[var(--color-fill-1)] p-3 text-xs leading-5 text-[var(--color-text-2)]">{formatJson(value)}</pre>
          ) : (
            <div className="flex min-h-32 items-center justify-center py-4">
              <Empty className="my-0" image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('workflowOrchestration.node.noSectionData', '暂无{title}', { title })} />
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

function NodeDetail({ detail, instancePermissions, onChanged }: { detail: ExecutionNodeDetail; instancePermissions?: string[]; onChanged: () => Promise<void> }) {
  const { get, post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState<string>();

  const approval = detail.interaction?.type === 'APPROVAL' ? detail.interaction : undefined;
  const showFrozenConfigNotice = ['PENDING', 'SKIPPED', 'UNREACHABLE'].includes(detail.node.state) && detail.instances.length === 0;
  const hasNodeNotice = Boolean(detail.error) || detail.node.state === 'WARNING' || showFrozenConfigNotice;

  const decide = async (decision: 'APPROVED' | 'REJECTED') => {
    if (!approval) return;
    setBusy(true);
    try {
      await post(`${API}/interactions/${approval.id}/decide/`, { decision, comment: comment.trim() });
      message.success(decision === 'APPROVED' ? t('workflowOrchestration.approval.approved', '已通过审批') : t('workflowOrchestration.approval.rejected', '已驳回审批'));
      setComment('');
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  const download = async (artifact: ExecutionArtifactRecord) => {
    setDownloading(artifact.id);
    try {
      const blob = await get<Blob>(artifact.download_url, { responseType: 'blob' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = artifact.filename;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(undefined);
    }
  };

  return (
    <div data-testid="node-detail-content" className="flex w-full min-w-0 max-w-full flex-col gap-5">
      {hasNodeNotice ? (
        <div data-testid="node-detail-alerts" className="flex flex-col gap-3">
          {detail.error ? <Alert type="error" showIcon message={detail.error.type || t('workflowOrchestration.node.executionFailed', '节点执行失败')} description={detail.error.message} /> : null}
          {detail.node.state === 'WARNING' ? <Alert type="warning" showIcon message={t('workflowOrchestration.node.nonFatalWarning', '执行完成，但该节点包含非致命告警')} description={t('workflowOrchestration.node.warningOutputHint', '具体告警信息请查看当前节点输出。')} /> : null}
          {showFrozenConfigNotice ? <Alert type="info" showIcon message={nodeLabel(detail.node.state, t)} description={t('workflowOrchestration.node.frozenConfigHint', '该节点本次没有产生执行实例，展示的是发布版本中的冻结配置。')} /> : null}
        </div>
      ) : null}
      <section aria-label={t('workflowOrchestration.node.executionInfo', '节点执行信息')} className="py-1">
        <Descriptions size="small" column={2} items={Object.entries(detail.execution_info).map(([key, value]) => {
          const item = presentExecutionInfoItem(key, value, t, convertToLocalizedTime);
          return { key, label: item.label, children: item.children };
        })} />
      </section>
      {approval ? (
        <section className="flex flex-col gap-4">
          <Alert type={approval.can_act ? 'info' : 'warning'} showIcon message={approval.title} description={approval.description || t('workflowOrchestration.approval.waitingCandidate', '等待候选审批人处理')} />
          <Descriptions size="small" column={1} items={[
            { key: 'candidate', label: t('workflowOrchestration.approval.candidates', '候选审批人'), children: approval.candidate_users.join('、') },
            { key: 'context', label: t('workflowOrchestration.approval.context', '审批上下文'), children: <pre className="m-0 max-w-full overflow-x-auto whitespace-pre-wrap text-xs">{formatJson(approval.public_context)}</pre> },
          ]} />
          {approval.can_act ? (
            <>
              <Input.TextArea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} maxLength={500} showCount placeholder={t('workflowOrchestration.approval.commentPlaceholder', '通过时选填；驳回时必填原因')} />
              <div data-testid="approval-actions" className="mt-1 flex justify-end gap-2">
                <WorkflowPermission operation="Approve" area="executions" instancePermissions={instancePermissions}><Popconfirm title={t('workflowOrchestration.approval.rejectConfirm', '确认驳回？')} description={comment.trim() ? t('workflowOrchestration.approval.rejectHint', '流程将进入审批驳回分支。') : t('workflowOrchestration.approval.rejectReasonRequired', '请先填写驳回原因。')} okButtonProps={{ danger: true, disabled: !comment.trim() }} onConfirm={() => void decide('REJECTED')}><Button aria-label={t('workflowOrchestration.approval.reject', '驳回审批')} danger loading={busy}>{t('workflowOrchestration.approval.rejectShort', '驳回')}</Button></Popconfirm></WorkflowPermission>
                <WorkflowPermission operation="Approve" area="executions" instancePermissions={instancePermissions}><Popconfirm title={t('workflowOrchestration.approval.approveConfirm', '确认通过并继续执行？')} onConfirm={() => void decide('APPROVED')}><Button aria-label={t('workflowOrchestration.approval.approve', '通过审批')} type="primary" loading={busy}>{t('workflowOrchestration.approval.approveShort', '通过')}</Button></Popconfirm></WorkflowPermission>
              </div>
            </>
          ) : null}
        </section>
      ) : (
        <>
          <JsonEvidence title={t('workflowOrchestration.node.input', '输入')} value={detail.inputs} />
          <JsonEvidence title={t('workflowOrchestration.node.output', '输出')} value={detail.outputs} />
        </>
      )}
      {detail.artifacts.length ? <section className="flex flex-col gap-3"><h3 className="m-0 text-sm font-medium">{t('workflowOrchestration.node.artifacts', '产物')}</h3><div className="space-y-2">{detail.artifacts.map((artifact) => <div key={artifact.id} className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border-1)] p-3"><div className="min-w-0"><div className="truncate">{artifact.filename}</div><div className="mt-1 text-xs text-[var(--color-text-3)]">{artifact.format.toUpperCase()} · {(artifact.size / 1024).toFixed(1)} KiB</div></div><WorkflowPermission operation="View" area="executions" instancePermissions={instancePermissions}><Button icon={<DownloadOutlined />} loading={downloading === artifact.id} onClick={() => void download(artifact)}>{t('common.download', '下载')}</Button></WorkflowPermission></div>)}</div></section> : null}
    </div>
  );
}

export interface ExecutionDetailDrawerProps {
  executionId?: string;
  initialNodeReference?: string;
  initialInstanceId?: string;
  open: boolean;
  onClose: () => void;
  onExecutionChanged?: () => void;
  onRerunStarted?: (executionId: string) => void;
}

export function ExecutionDetailDrawer({ executionId, initialNodeReference, initialInstanceId, open, onClose, onExecutionChanged, onRerunStarted }: ExecutionDetailDrawerProps) {
  const { get } = useApiClient();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [execution, setExecution] = useState<ExecutionRecord>();
  const [nodes, setNodes] = useState<ExecutionNodeSummary[]>([]);
  const [selectedNodeReference, setSelectedNodeReference] = useState<string>();
  const [nodeDetail, setNodeDetail] = useState<ExecutionNodeDetail>();
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);
  const [nodeDetailFailed, setNodeDetailFailed] = useState(false);
  const [nodeSearch, setNodeSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const requestCoordinator = useRequestCoordinator(setLoading);
  const nodeDetailRequestCoordinator = useRequestCoordinator(setNodeDetailLoading);
  const executionIdRef = useRef(executionId);
  const selectedNodeReferenceRef = useRef<string | undefined>(undefined);
  executionIdRef.current = executionId;

  const loadDetail = useCallback(async (reference: string, quiet = false): Promise<void> => {
    const currentExecutionId = executionIdRef.current;
    if (!currentExecutionId) return;
    const ticket = nodeDetailRequestCoordinator.begin({ visible: !quiet });
    if (!ticket) return;
    if (!quiet) {
      setNodeDetail(undefined);
      setNodeDetailFailed(false);
    }
    try {
      const instanceQuery = reference === initialNodeReference && initialInstanceId
        ? `?${new URLSearchParams({ instance_id: initialInstanceId }).toString()}`
        : '';
      const detail = await get<ExecutionNodeDetail>(`${API}/executions/${currentExecutionId}/nodes/${encodeURIComponent(reference)}/${instanceQuery}`, {
        signal: ticket.signal,
      });
      if (
        !nodeDetailRequestCoordinator.shouldApply(ticket)
        || executionIdRef.current !== currentExecutionId
        || selectedNodeReferenceRef.current !== reference
      ) return;
      setNodeDetail(detail);
      setNodeDetailFailed(false);
    } catch {
      if (nodeDetailRequestCoordinator.shouldApply(ticket) && !quiet) {
        setNodeDetail(undefined);
        setNodeDetailFailed(true);
      }
    } finally {
      nodeDetailRequestCoordinator.finish(ticket);
    }
  }, [get, initialInstanceId, initialNodeReference, nodeDetailRequestCoordinator]);

  const load = useCallback(async (quiet = false) => {
    if (!executionId) return;
    const ticket = requestCoordinator.begin({ visible: !quiet });
    if (!ticket) return;
    try {
      const [record, summary] = await Promise.all([
        get<ExecutionRecord>(`${API}/executions/${executionId}/`, { signal: ticket.signal }),
        get<ExecutionNodesResponse>(`${API}/executions/${executionId}/nodes/`, { signal: ticket.signal }),
      ]);
      if (!requestCoordinator.shouldApply(ticket)) return;
      const visibleNodes = summary.nodes.filter(isUserVisibleNode);
      setExecution(record);
      setNodes(visibleNodes);
      const currentReference = selectedNodeReferenceRef.current;
      const reference = currentReference && visibleNodes.some((node) => node.reference === currentReference)
        ? currentReference
        : initialNodeReference && visibleNodes.some((node) => node.reference === initialNodeReference)
          ? initialNodeReference
          : visibleNodes.find((node) => node.reference === summary.default_node_reference)?.reference
            || visibleNodes[visibleNodes.length - 1]?.reference;
      if (selectedNodeReferenceRef.current !== reference) {
        selectedNodeReferenceRef.current = reference;
        setSelectedNodeReference(reference);
      }
      if (reference) await loadDetail(reference, quiet);
    } catch {
      if (requestCoordinator.shouldApply(ticket)) {
        setExecution(undefined);
        setNodes([]);
      }
    } finally {
      requestCoordinator.finish(ticket);
    }
  }, [executionId, get, initialNodeReference, loadDetail, requestCoordinator]);

  const initialize = useCallback(() => {
    nodeDetailRequestCoordinator.invalidate();
    setExecution(undefined);
    setNodes([]);
    setNodeDetail(undefined);
    setNodeDetailFailed(false);
    setNodeSearch('');
    selectedNodeReferenceRef.current = undefined;
    setSelectedNodeReference(undefined);
    return load();
  }, [load, nodeDetailRequestCoordinator]);

  useAutoRequest(open && executionId ? `execution-detail:${executionId}:${initialNodeReference || ''}:${initialInstanceId || ''}` : undefined, initialize);

  useEffect(() => {
    if (open) return;
    requestCoordinator.invalidate();
    nodeDetailRequestCoordinator.invalidate();
    setNodeDetail(undefined);
    setNodeDetailFailed(false);
  }, [nodeDetailRequestCoordinator, open, requestCoordinator]);

  useEffect(() => {
    if (!open || !execution || !ACTIVE.has(execution.status)) return;
    const timer = window.setInterval(() => void load(true), 5_000);
    return () => window.clearInterval(timer);
  }, [execution, load, open]);

  const status = execution ? executionStatusPresentation[execution.status] : undefined;
  const selectedNode = nodes.find((node) => node.reference === selectedNodeReference);
  const normalizedNodeSearch = nodeSearch.trim().toLowerCase();
  const filteredNodes = normalizedNodeSearch
    ? nodes.filter((node) => `${node.name} ${node.reference}`.toLowerCase().includes(normalizedNodeSearch))
    : nodes;
  const selectedNodeDetail = nodeDetail?.node.reference === selectedNodeReference ? nodeDetail : undefined;
  return (
    <>
      <OperateDrawer
        open={open}
        onClose={() => {
          requestCoordinator.invalidate();
          nodeDetailRequestCoordinator.invalidate();
          onClose();
        }}
        width={980}
        title={t('workflowOrchestration.execution.details', '执行详情')}
        subTitle={execution ? `${execution.workflow_name} · v${execution.workflow_version}` : ''}
        extra={execution ? <div className="flex items-center gap-2">
          <WorkflowPermission operation="View" area="executions" instancePermissions={execution.permission}><Button
            type="link"
            size="small"
            icon={<ReloadOutlined />}
            loading={loading || nodeDetailLoading}
            onClick={() => {
              nodeDetailRequestCoordinator.invalidate();
              setNodeDetail(undefined);
              setNodeDetailFailed(false);
              void load();
            }}
          >{t('common.refresh', '刷新')}</Button></WorkflowPermission>
          <ExecutionLifecycleActions execution={execution} presentation="menu" onExecutionChanged={async (updated) => { setExecution(updated); await load(true); onExecutionChanged?.(); }} onRerun={() => setRerunOpen(true)} />
        </div> : undefined}
        destroyOnClose
        bodyStyle={{ padding: 0, display: 'flex', overflow: 'hidden' }}
      >
        {loading && !execution ? <div data-testid="execution-detail-initial-loading" className="flex h-full min-h-0 w-full flex-1 items-center justify-center"><Spin /></div> : execution ? (
          <div data-testid="execution-detail-content" className="flex h-full min-h-0 w-full min-w-0 max-w-full flex-1 flex-col overflow-hidden">
            <section className="shrink-0 px-5 py-4" aria-label={t('workflowOrchestration.execution.summary', '执行概要')}>
              <Descriptions size="small" column={2} items={[
                { key: 'status', label: t('common.status', '状态'), children: status ? <Tag color={status.color}>{t(`workflowOrchestration.execution.status.${execution.status}`, status.label)}</Tag> : '--' },
                { key: 'mode', label: t('workflowOrchestration.execution.mode', '模式'), children: execution.mode === 'PRODUCTION' ? t('workflowOrchestration.execution.production', '正式') : t('workflowOrchestration.execution.debug', '调试') },
                { key: 'trigger', label: t('workflowOrchestration.trigger.title', '触发器'), children: formatTriggerTypeLabel(execution.trigger_type, t) },
                { key: 'actor', label: t('workflowOrchestration.execution.startedBy', '发起人'), children: formatStartedBy(execution.started_by, t) },
                { key: 'started', label: t('workflowOrchestration.execution.startedAt', '开始时间'), children: execution.created_at ? convertToLocalizedTime(execution.created_at) : '--' },
                { key: 'duration', label: t('workflowOrchestration.execution.duration', '耗时'), children: formatDuration(execution.duration_ms) },
              ]} />
              {execution.termination_reason ? <Alert className="mt-3" type="info" message={t('workflowOrchestration.execution.terminationReasonValue', '终止原因：{reason}', { reason: execution.termination_reason })} /> : null}
            </section>
            <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden border-t border-[var(--color-border-1)]">
              <nav aria-label={t('workflowOrchestration.node.workflowNodes', '流程节点')} className="w-[310px] shrink-0 overflow-y-auto border-r border-[var(--color-border-1)] p-3">
                <Input.Search
                  allowClear
                  className="mb-3"
                  placeholder={t('workflowOrchestration.node.searchPlaceholder', '节点名称 / 标识')}
                  value={nodeSearch}
                  onChange={(event) => setNodeSearch(event.target.value)}
                />
                <div className="mb-2 flex items-center justify-between px-1">
                  <h2 className="m-0 text-sm font-semibold text-[var(--color-text-1)]">{t('workflowOrchestration.node.workflowNodes', '流程节点')}</h2>
                  <span className="text-xs text-[var(--color-text-3)]">{filteredNodes.length} / {nodes.length}</span>
                </div>
                {filteredNodes.length ? <div className="flex flex-col gap-3">{filteredNodes.map((node) => {
                  const selected = node.reference === selectedNodeReference;
                  const nodeIndex = nodes.findIndex((item) => item.reference === node.reference);
                  return (
                    <WorkflowPermission key={node.reference} operation="View" area="executions" instancePermissions={execution.permission} className="block w-full"><button
                      type="button"
                      aria-current={selected ? 'step' : undefined}
                      aria-label={t('workflowOrchestration.node.viewNode', '查看节点 {name}', { name: node.name })}
                      className={`flex min-h-14 w-full cursor-pointer items-start gap-3 rounded-[7px] border border-l-[3px] border-[var(--color-border-1)] px-3 py-3.5 text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] ${selected ? 'bg-[var(--color-fill-1)]' : 'bg-[var(--color-bg-1)] hover:bg-[var(--color-bg-hover)]'}`}
                      style={{ borderLeftColor: NODE_ACCENTS[node.state] }}
                      onClick={() => {
                        if (node.reference === selectedNodeReferenceRef.current) return;
                        selectedNodeReferenceRef.current = node.reference;
                        setSelectedNodeReference(node.reference);
                        void loadDetail(node.reference, false);
                      }}
                    >
                      <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border text-xs tabular-nums ${selected ? 'border-[var(--color-primary)] text-[var(--color-primary)]' : 'border-[var(--color-border-3)] text-[var(--color-text-3)]'}`}>{nodeIndex + 1}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium leading-5 text-[var(--color-text-1)]" title={node.name}>{node.name}</span>
                        <span className="mt-2 flex flex-wrap items-center gap-1.5">
                          <Tag className="!m-0" color={NODE_COLORS[node.state]}>{nodeLabel(node.state, t)}</Tag>
                          {node.instance_count > 1 ? <span className="text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.node.executionCount', '{count} 次执行', { count: node.instance_count })}</span> : null}
                        </span>
                      </span>
                    </button></WorkflowPermission>
                  );
                })}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={nodes.length ? t('workflowOrchestration.node.noMatchingNodes', '暂无匹配节点') : t('workflowOrchestration.node.noNodes', '暂无流程节点')} />}
              </nav>
              <section
                aria-label={t('workflowOrchestration.node.details', '节点详情')}
                aria-busy={nodeDetailLoading || (loading && !selectedNodeDetail)}
                className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-5 py-5"
              >
                {selectedNode ? (
                  <>
                    <div className="mb-5 flex items-center justify-between gap-3 border-b border-[var(--color-border-1)] pb-4">
                      <div className="min-w-0">
                        <h2 id="selected-node-title" className="m-0 truncate text-base font-semibold text-[var(--color-text-1)]" title={selectedNode.name}>{selectedNode.name}</h2>
                      </div>
                      <Tag className="!m-0 shrink-0" color={NODE_COLORS[selectedNode.state]}>{nodeLabel(selectedNode.state, t)}{selectedNode.instance_count > 1 ? t('workflowOrchestration.node.timesSuffix', ' · {count} 次', { count: selectedNode.instance_count }) : ''}</Tag>
                    </div>
                    {nodeDetailLoading || (loading && !selectedNodeDetail) ? <div className="flex min-h-52 items-center justify-center"><Spin /></div> : selectedNodeDetail ? (
                      <NodeDetail
                        key={selectedNode.reference}
                        detail={selectedNodeDetail}
                        instancePermissions={execution.permission}
                        onChanged={async () => { await load(true); onExecutionChanged?.(); }}
                      />
                    ) : nodeDetailFailed ? (
                      <Empty description={t('workflowOrchestration.node.loadFailed', '节点详情加载失败')}>
                        <WorkflowPermission operation="View" area="executions" instancePermissions={execution.permission}><Button type="primary" onClick={() => void loadDetail(selectedNode.reference, false)}>{t('common.retry', '重试')}</Button></WorkflowPermission>
                      </Empty>
                    ) : <Empty description={t('workflowOrchestration.node.noDetails', '暂无节点详情')} />}
                  </>
                ) : <div className="flex h-full min-h-48 items-center justify-center"><Empty description={t('workflowOrchestration.node.noDetails', '暂无节点详情')} /></div>}
              </section>
            </div>
          </div>
        ) : <Empty description={t('workflowOrchestration.execution.notFound', '执行记录不存在')} />}
      </OperateDrawer>
      {execution && rerunOpen ? <WorkflowLaunchDialog open title={t('workflowOrchestration.execution.rerunTitle', '重新执行 · {name}', { name: execution.workflow_name })} planUrl={`${API}/executions/${execution.id}/launch-plan/`} submitUrl={`${API}/executions/${execution.id}/rerun/`} instancePermissions={execution.permission} onClose={() => setRerunOpen(false)} onStarted={(record) => { setRerunOpen(false); onRerunStarted?.(record.id); }} /> : null}
    </>
  );
}
