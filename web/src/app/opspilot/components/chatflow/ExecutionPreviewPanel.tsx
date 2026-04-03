'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, Tag } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  CloseOutlined,
  CopyOutlined,
  ClockCircleFilled,
  DownOutlined,
  LoadingOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { WorkflowExecutionDetailItem } from '@/app/opspilot/types/studio';

interface ExecutionPreviewPanelProps {
  open: boolean;
  loading: boolean;
  title?: string;
  executionId?: string;
  streamingContent: string;
  rawExecutionData?: unknown;
  items: WorkflowExecutionDetailItem[];
  activeNodeId?: string | null;
  onClose: () => void;
}

const statusConfig = {
  pending: {
    color: 'default' as const,
    textClassName: 'text-(--color-text-3)',
    borderClassName: 'border-(--color-border-1)',
    icon: <ClockCircleFilled className="text-(--color-text-3)" />,
  },
  running: {
    color: 'processing' as const,
    textClassName: 'text-blue-600',
    borderClassName: 'border-blue-200',
    icon: <LoadingOutlined className="text-blue-500" spin />,
  },
  completed: {
    color: 'success' as const,
    textClassName: 'text-emerald-600',
    borderClassName: 'border-emerald-200',
    icon: <CheckCircleFilled className="text-emerald-500" />,
  },
  failed: {
    color: 'error' as const,
    textClassName: 'text-red-600',
    borderClassName: 'border-red-200',
    icon: <CloseCircleFilled className="text-red-500" />,
  },
  interrupted: {
    color: 'default' as const,
    textClassName: 'text-(--color-text-2)',
    borderClassName: 'border-(--color-border-1)',
    icon: <CloseCircleFilled className="text-(--color-text-3)" />,
  },
  interrupt_requested: {
    color: 'processing' as const,
    textClassName: 'text-orange-600',
    borderClassName: 'border-orange-200',
    icon: <ClockCircleFilled className="text-orange-500" />,
  },
};

const ExecutionPreviewPanel: React.FC<ExecutionPreviewPanelProps> = ({
  open,
  loading,
  streamingContent,
  rawExecutionData,
  items,
  activeNodeId,
  onClose,
}) => {
  const { t } = useTranslation();
  const [expandedNodeIds, setExpandedNodeIds] = useState<string[]>([]);
  const [expandedErrorNodeIds, setExpandedErrorNodeIds] = useState<string[]>([]);
  const failedNodeRef = useRef<HTMLDivElement | null>(null);

  const sortedItems = useMemo(() => {
    return [...items].sort((left, right) => {
      const leftIndex = left.node_index ?? Number.MAX_SAFE_INTEGER;
      const rightIndex = right.node_index ?? Number.MAX_SAFE_INTEGER;
      return leftIndex - rightIndex;
    });
  }, [items]);

  const firstFailedNode = useMemo(
    () => sortedItems.find((item) => item.status === 'failed') ?? null,
    [sortedItems]
  );

  useEffect(() => {
    if (!open || !firstFailedNode) {
      return;
    }

    setExpandedNodeIds((current) => (
      current.includes(firstFailedNode.node_id) ? current : [...current, firstFailedNode.node_id]
    ));
    setExpandedErrorNodeIds((current) => (
      current.includes(firstFailedNode.node_id) ? current : [...current, firstFailedNode.node_id]
    ));

    window.setTimeout(() => {
      failedNodeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  }, [open, firstFailedNode]);

  if (!open) {
    return null;
  }

  const expandAllNodes = () => {
    setExpandedNodeIds(sortedItems.map((item) => item.node_id));
    setExpandedErrorNodeIds(sortedItems.filter((item) => item.status === 'failed').map((item) => item.node_id));
  };

  const collapseAllNodes = () => {
    setExpandedNodeIds([]);
    setExpandedErrorNodeIds([]);
  };

  const toggleNode = (nodeId: string) => {
    setExpandedNodeIds((current) => (
      current.includes(nodeId)
        ? current.filter((id) => id !== nodeId)
        : [...current, nodeId]
    ));
  };

  const toggleError = (nodeId: string) => {
    setExpandedErrorNodeIds((current) => (
      current.includes(nodeId)
        ? current.filter((id) => id !== nodeId)
        : [...current, nodeId]
    ));
  };

  const parseJsonIfString = (value: unknown) => {
    if (typeof value !== 'string') {
      return value;
    }

    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  };

  const getExtendedField = (item: WorkflowExecutionDetailItem, keys: string[]) => {
    const record = item as unknown as Record<string, unknown>;
    for (const key of keys) {
      const value = record[key];
      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }
    return null;
  };

  const getFieldFromRecord = (source: unknown, keys: string[]) => {
    if (!source || typeof source !== 'object') {
      return null;
    }

    const record = source as Record<string, unknown>;
    for (const key of keys) {
      const value = record[key];
      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }

    return null;
  };

  const getExecutionErrorFields = (item: WorkflowExecutionDetailItem, metadata: unknown) => {
    const parsedMetadata = parseJsonIfString(metadata);
    const errorPayload = parseJsonIfString(
      getExtendedField(item, ['error_detail', 'error', 'exception', 'failure_detail', 'failure'])
    );

    const errorType = item.error_type
      ?? getFieldFromRecord(errorPayload, ['error_type', 'errorType', 'name', 'code'])
      ?? getFieldFromRecord(parsedMetadata, ['error_type', 'errorType', 'error_code', 'errorCode', 'name']);

    const errorReason = item.error_message
      ?? getFieldFromRecord(errorPayload, ['message', 'reason', 'detail', 'description'])
      ?? getFieldFromRecord(parsedMetadata, ['error_message', 'message', 'reason', 'detail', 'description']);

    const requestId = item.request_id
      ?? getFieldFromRecord(errorPayload, ['request_id', 'requestId', 'trace_id', 'traceId'])
      ?? getFieldFromRecord(parsedMetadata, ['request_id', 'requestId', 'trace_id', 'traceId']);

    const errorStack = item.error_stack
      ?? getFieldFromRecord(errorPayload, ['error_stack', 'stack', 'stack_trace', 'stackTrace', 'traceback'])
      ?? getFieldFromRecord(parsedMetadata, ['error_stack', 'stack', 'stack_trace', 'stackTrace', 'traceback']);

    const errorTime = getFieldFromRecord(errorPayload, ['error_time', 'errorTime', 'timestamp', 'time'])
      ?? getFieldFromRecord(parsedMetadata, ['error_time', 'errorTime', 'timestamp', 'time'])
      ?? item.end_time;

    return {
      errorType,
      errorReason,
      requestId,
      errorStack,
      errorTime,
    };
  };

  const renderDataBlock = (value: unknown, emptyText?: string) => {
    const parsedValue = parseJsonIfString(value);

    if (parsedValue === undefined || parsedValue === null || parsedValue === '') {
      return <div className="text-xs text-(--color-text-3)">{emptyText || '--'}</div>;
    }

    if (typeof parsedValue === 'string') {
      return (
        <div className="max-h-48 overflow-auto rounded-xl bg-(--color-fill-1) px-3 py-2 text-xs leading-5 whitespace-pre-wrap text-(--color-text-2)">
          {parsedValue}
        </div>
      );
    }

    return (
      <pre className="max-h-56 overflow-auto rounded-xl bg-(--color-fill-1) p-3 text-xs leading-5 whitespace-pre-wrap text-(--color-text-2)">
        {JSON.stringify(parsedValue, null, 2)}
      </pre>
    );
  };

  const copyBlock = async (value: unknown) => {
    const parsedValue = parseJsonIfString(value);
    const text = typeof parsedValue === 'string' ? parsedValue : JSON.stringify(parsedValue, null, 2);

    if (!text) {
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Ignore clipboard failures in preview panel.
    }
  };

  const formatDuration = (duration?: number | null) => {
    if (!duration && duration !== 0) {
      return '--';
    }
    return `${duration}ms`;
  };

  const renderStatusTag = (status: WorkflowExecutionDetailItem['status']) => {
    if (status === 'failed') return <Tag color="error">{t('chatflow.preview.failed')}</Tag>;
    if (status === 'completed') return <Tag color="success">{t('chatflow.preview.success')}</Tag>;
    if (status === 'running') return <Tag color="processing">{t('chatflow.preview.running')}</Tag>;
    if (status === 'interrupted') return <Tag>{t('chatflow.preview.interrupted', '已中断')}</Tag>;
    if (status === 'interrupt_requested') return <Tag color="orange">{t('chatflow.preview.interruptRequested', '中断中')}</Tag>;
    return <Tag>{t('chatflow.preview.pending')}</Tag>;
  };

  const formatTime = (value?: string | null) => {
    if (!value) {
      return '--';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  };

  return (
    <div className="pointer-events-auto absolute inset-y-4 right-4 z-20 flex w-90 flex-col overflow-hidden rounded-2xl border border-(--color-border-1) bg-(--color-bg-1) shadow-[0_18px_36px_rgba(15,23,42,0.14)]">
      <div className="border-b border-(--color-border-1) px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="text-[18px] font-semibold leading-none text-(--color-text-1)">{t('chatflow.preview.logCenter')}</div>
              <div className="flex items-center gap-1 text-xs">
                <Button size="small" type="text" className="rounded-md bg-(--color-fill-1) px-2 text-xs text-(--color-text-2) hover:bg-(--color-fill-2)! hover:text-(--color-text-1)!" onClick={expandAllNodes}>{t('chatflow.preview.expandAll')}</Button>
                <Button size="small" type="text" className="rounded-md bg-(--color-fill-1) px-2 text-xs text-(--color-text-2) hover:bg-(--color-fill-2)! hover:text-(--color-text-1)!" onClick={collapseAllNodes}>{t('chatflow.preview.collapseAll')}</Button>
              </div>
            </div>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-(--color-text-3) transition-colors hover:bg-(--color-fill-1) hover:text-(--color-text-1)"
            onClick={onClose}
          >
            <CloseOutlined />
          </button>
        </div>

      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {loading && sortedItems.length === 0 ? (
          <div className="flex h-full items-center justify-center text-(--color-text-3)">
            <LoadingOutlined spin className="mr-2" />
            {t('chatflow.preview.loading')}
          </div>
        ) : sortedItems.length === 0 ? (
          <Empty description={t('chatflow.preview.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="space-y-3">
            {sortedItems.map((item) => {
              const isExpanded = expandedNodeIds.includes(item.node_id);
              const isErrorExpanded = expandedErrorNodeIds.includes(item.node_id);
              const currentStatus = statusConfig[item.status as keyof typeof statusConfig] || statusConfig.pending;
              const isFailed = item.status === 'failed';
              const isActive = activeNodeId === item.node_id;
              const inputData = getExtendedField(item, ['input_data', 'input', 'node_input']);
              const outputData = getExtendedField(item, ['output_data', 'output', 'last_output', 'result', 'node_output']);
              const metadata = getExtendedField(item, ['metadata', 'meta']);
              const displayOutput = outputData ?? (isActive ? streamingContent : null);
              const {
                errorType,
                errorReason,
                requestId,
                errorStack,
                errorTime,
              } = getExecutionErrorFields(item, metadata);
              const hasErrorDetail = Boolean(errorType || errorReason || requestId || errorStack || errorTime);

              return (
                <div
                  key={item.node_id}
                  ref={firstFailedNode?.node_id === item.node_id ? failedNodeRef : null}
                  className={`overflow-hidden rounded-xl border bg-(--color-bg-1) ${currentStatus.borderClassName} ${isActive ? 'ring-2 ring-blue-200' : ''}`}
                >
                  <button
                    type="button"
                    onClick={() => toggleNode(item.node_id)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left"
                  >
                    <span className="flex h-5 w-5 items-center justify-center">{currentStatus.icon}</span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-(--color-text-1)">{item.node_name}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-(--color-text-3)">{formatDuration(item.duration_ms)}</span>
                      {isExpanded ? <DownOutlined className="text-xs text-(--color-text-3)" /> : <RightOutlined className="text-xs text-(--color-text-3)" />}
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-(--color-border-1) bg-(--color-bg-1) px-4 py-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-(--color-text-1)">{item.node_name}</span>
                            <span className="shrink-0">{renderStatusTag(item.status)}</span>
                          </div>
                          <div className="mt-1 text-[11px] text-(--color-text-3)">ID: {item.node_id}</div>
                        </div>
                        <div className="text-right text-[11px] text-(--color-text-3)">
                          <div>{formatDuration(item.duration_ms)}</div>
                        </div>
                      </div>

                      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                        <div>
                          <div className="text-(--color-text-3)">{t('chatflow.preview.startTime')}</div>
                          <div className="mt-1 text-(--color-text-2)">{formatTime(item.start_time)}</div>
                        </div>
                        <div>
                          <div className="text-(--color-text-3)">{t('chatflow.preview.endTime')}</div>
                          <div className="mt-1 text-(--color-text-2)">{formatTime(item.end_time)}</div>
                        </div>
                      </div>

                      <div className="mt-4 space-y-3">
                        <div>
                          <div className="mb-2 flex items-center justify-between gap-2 text-xs font-medium text-(--color-text-2)">
                            <span>{t('chatflow.preview.inputData')}</span>
                            <button
                              type="button"
                              className="rounded p-1 text-(--color-text-3) transition-colors hover:bg-(--color-fill-1) hover:text-(--color-text-1)"
                              onClick={() => copyBlock(inputData)}
                            >
                              <CopyOutlined />
                            </button>
                          </div>
                          {renderDataBlock(inputData, t('chatflow.preview.detailPending'))}
                        </div>

                        <div>
                          <div className="mb-2 flex items-center justify-between gap-2 text-xs font-medium text-(--color-text-2)">
                            <span>{t('chatflow.preview.outputData')}</span>
                            <button
                              type="button"
                              className="rounded p-1 text-(--color-text-3) transition-colors hover:bg-(--color-fill-1) hover:text-(--color-text-1)"
                              onClick={() => copyBlock(displayOutput ?? rawExecutionData ?? streamingContent)}
                            >
                              <CopyOutlined />
                            </button>
                          </div>
                          {renderDataBlock(displayOutput ?? rawExecutionData ?? (isActive ? streamingContent : null), t('chatflow.preview.detailPending'))}
                        </div>

                        {metadata && (
                          <div>
                            <div className="mb-2 text-xs font-medium text-(--color-text-2)">{t('chatflow.preview.metadata')}</div>
                            {renderDataBlock(metadata)}
                          </div>
                        )}
                      </div>

                      {isFailed && hasErrorDetail && (
                        <div className="mt-4 rounded-xl border border-red-200 bg-red-50/80 p-3.5">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <div className="text-sm font-semibold text-red-600">{t('chatflow.preview.errorSummary')}</div>
                              {errorType && (
                                <div className="mt-1 text-sm font-medium text-red-600">
                                  {t('chatflow.preview.errorType')}：{String(errorType)}
                                </div>
                              )}
                              {errorReason && (
                                <div className="mt-2 text-sm text-red-500">{String(errorReason)}</div>
                              )}
                            </div>
                            <Button size="small" type="link" danger onClick={() => toggleError(item.node_id)}>
                              {isErrorExpanded ? t('chatflow.preview.collapseDetail') : t('chatflow.preview.expandDetail')}
                            </Button>
                          </div>

                          {isErrorExpanded && (
                            <div className="mt-3 space-y-3 border-t border-red-200 pt-3 text-xs">
                              {errorType && (
                                <div>
                                  <div className="font-medium text-red-700">{t('chatflow.preview.errorType')}</div>
                                  <div className="mt-1 text-red-600">{String(errorType)}</div>
                                </div>
                              )}
                              {errorReason && (
                                <div>
                                  <div className="font-medium text-red-700">{t('chatflow.preview.errorReason')}</div>
                                  <div className="mt-1 whitespace-pre-wrap text-red-600">{String(errorReason)}</div>
                                </div>
                              )}
                              {errorTime && (
                                <div>
                                  <div className="font-medium text-red-700">{t('chatflow.preview.errorTime')}</div>
                                  <div className="mt-1 text-red-600">{formatTime(String(errorTime))}</div>
                                </div>
                              )}
                              {requestId && (
                                <div>
                                  <div className="font-medium text-red-700">{t('chatflow.preview.requestId')}</div>
                                  <div className="mt-1 break-all text-red-600">{String(requestId)}</div>
                                </div>
                              )}
                              {errorStack && (
                                <div>
                                  <div className="font-medium text-red-700">{t('chatflow.preview.errorStack')}</div>
                                  <pre className="mt-1 overflow-auto rounded-xl bg-white/80 p-3 whitespace-pre-wrap text-red-600">{String(errorStack)}</pre>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ExecutionPreviewPanel;
