'use client';

import React, { useEffect, useRef, useState } from 'react';
import type { PlannedExecutionStepData } from '../plannedExecution';
import { ToolCallGroup, type ToolCall } from './ToolCallGroup';
import { useTranslator } from '../useTranslator';

const statusLabel = (
  status: PlannedExecutionStepData['status'],
  isStreaming: boolean,
  t: ReturnType<typeof useTranslator>,
) => {
  if (status === 'failed') return t('chat.plannedStep.failed', '失败');
  if (status === 'skipped') return t('chat.plannedStep.skipped', '已跳过');
  if (status === 'running' && isStreaming) return t('chat.plannedStep.running', '执行中');
  if (status === 'done') return t('chat.plannedStep.done', '已完成');
  return t('chat.plannedStep.running', '执行中');
};

export const PlannedExecutionPanel: React.FC<{
  steps: PlannedExecutionStepData[];
  toolCalls: ToolCall[];
  isStreaming?: boolean;
}> = ({ steps, toolCalls, isStreaming = false }) => {
  const t = useTranslator();
  const [isGroupExpanded, setIsGroupExpanded] = useState(isStreaming);
  const prevStreamingRef = useRef(isStreaming);
  const running = isStreaming ? steps.find((step) => step.status === 'running') : undefined;
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(() => (
    running ? new Set([running.step_index]) : new Set()
  ));

  useEffect(() => {
    if (isStreaming) {
      setIsGroupExpanded(true);
    } else if (prevStreamingRef.current) {
      setIsGroupExpanded(false);
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming]);

  if (steps.length === 0) return null;

  const doneCount = steps.filter((step) => step.status === 'done').length;
  const failedCount = steps.filter((step) => step.status === 'failed').length;
  const skippedCount = steps.filter((step) => step.status === 'skipped').length;
  const toolById = new Map(toolCalls.map((tool) => [tool.id, tool]));
  const summaryText = isStreaming
    ? t('chat.plannedStep.summaryRunning', '步骤 {current}/{total}', {
      current: running?.step_index ?? doneCount,
      total: steps.length,
    })
    : failedCount > 0 || skippedCount > 0
      ? t('chat.plannedStep.summaryPartial', '完成 {done} 步{failed}{skipped}', {
        done: doneCount,
        failed: failedCount > 0
          ? t('chat.plannedStep.summaryFailed', ' · {count} 步失败', { count: failedCount })
          : '',
        skipped: skippedCount > 0
          ? t('chat.plannedStep.summarySkipped', ' · {count} 步跳过', { count: skippedCount })
          : '',
      })
      : t('chat.plannedStep.summaryDone', '已完成 {count} 步', { count: doneCount });

  return (
    <div className="my-1.5">
      <button
        type="button"
        className="group -ml-1 inline-flex cursor-pointer select-none items-center gap-1.5 rounded border-0 bg-transparent px-1 py-0.5 text-xs text-[var(--color-text-3)] transition-colors hover:bg-[var(--color-fill-1)] hover:text-[var(--color-text-2)]"
        onClick={() => setIsGroupExpanded((prev) => !prev)}
      >
        <span
          className="inline-flex h-3 w-3 items-center justify-center text-[9px] text-[var(--color-text-4)] transition-transform duration-200 group-hover:text-[var(--color-text-3)]"
          style={{ transform: isGroupExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▶
        </span>
        <span className="flex items-center gap-1.5 font-normal">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isStreaming ? 'animate-neutral-pulse bg-[var(--color-primary)]' : 'bg-emerald-500'}`} />
          <span className="text-[var(--color-text-2)]">{t('chat.plannedStep.planTitle', '执行计划')}</span>
        </span>
        <span className="ml-0.5 font-mono text-[11px] tabular-nums text-[var(--color-text-4)]">
          ({summaryText})
        </span>
      </button>

      {isGroupExpanded ? (
        <div className="ml-1 mt-1.5 space-y-1 border-l-2 border-[var(--color-fill-3)] pl-3">
          {steps.map((step) => {
            const expanded = expandedSteps.has(step.step_index);
            const stepTools = step.toolCallIds
              .map((id) => toolById.get(id))
              .filter((tool): tool is ToolCall => Boolean(tool));
            const isActive = step.status === 'running' && isStreaming;
            const isFailed = step.status === 'failed';
            const isSkipped = step.status === 'skipped';
            return (
              <div key={step.step_index} className="rounded">
                <button
                  type="button"
                  aria-expanded={expanded}
                  className="group flex w-full cursor-pointer select-none items-center gap-1.5 border-0 bg-transparent py-0.5 text-left text-xs text-[var(--color-text-2)] transition-colors hover:text-[var(--color-text-1)]"
                  onClick={() => setExpandedSteps((prev) => {
                    const next = new Set(prev);
                    if (next.has(step.step_index)) next.delete(step.step_index);
                    else next.add(step.step_index);
                    return next;
                  })}
                >
                  <span
                    className="inline-flex w-3 shrink-0 items-center justify-center text-[9px] text-[var(--color-text-4)] transition-transform group-hover:text-[var(--color-text-3)]"
                    style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                  >
                    ▶
                  </span>
                  <span className="min-w-0 flex-1 tabular-nums leading-5">
                    <span className="font-medium text-[var(--color-text-1)]">
                      {t('chat.plannedStep.stepTitle', '步骤 {index}/{total}', {
                        index: step.step_index,
                        total: step.total_steps || steps.length,
                      })}
                    </span>
                    <span className="text-[var(--color-text-3)]"> · {step.objective}</span>
                  </span>
                  <span
                    className="shrink-0 text-[11px]"
                    style={{
                      color: isFailed
                        ? 'var(--color-error)'
                        : isActive
                          ? 'var(--color-primary)'
                          : 'var(--color-text-4)',
                    }}
                  >
                    {statusLabel(step.status, isStreaming, t)}
                  </span>
                </button>
                {expanded ? (
                  <div className="pb-1 pl-4">
                    {stepTools.length > 0 ? (
                      <ToolCallGroup toolCalls={stepTools} />
                    ) : (
                      <div className="px-2 py-0.5 text-[11px] text-[var(--color-text-4)]">
                        {isActive
                          ? t('chat.plannedStep.waitingTool', '等待工具调用…')
                          : isFailed
                            ? (step.error || t('chat.plannedStep.incomplete', '本步未完成'))
                            : isSkipped
                              ? t('chat.plannedStep.skippedNoContext', '因上下文不足已跳过')
                              : step.reusedPriorResult
                                ? t('chat.plannedStep.reusedPrior', '复用上一步结果')
                                : t('chat.plannedStep.noToolCall', '本步无工具调用')}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};
