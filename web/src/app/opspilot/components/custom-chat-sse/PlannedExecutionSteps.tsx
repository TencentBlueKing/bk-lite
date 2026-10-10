'use client';

import React, { useEffect, useRef, useState } from 'react';
import { RightOutlined } from '@ant-design/icons';
import {
  PlannedExecutionStepData,
  shouldExpandPlannedStep,
} from './plannedExecutionState';
import ToolCallGroup from './ToolCallGroup';
import { useTranslation } from '@/utils/i18n';

export interface PlannedStepToolCall {
  id: string;
  name: string;
  args: string;
  status: 'calling' | 'completed' | 'error';
  result?: string;
}

interface PlannedExecutionStepsProps {
  steps: PlannedExecutionStepData[];
  toolCalls: PlannedStepToolCall[];
  isStreaming?: boolean;
}

type Translate = (
  key: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

const statusLabel = (status: PlannedExecutionStepData['status'], isStreaming: boolean, t: Translate) => {
  if (status === 'failed') return t('chat.plannedStep.failed', '失败');
  if (status === 'skipped') return t('chat.plannedStep.skipped', '已跳过');
  if (status === 'running' && isStreaming) return t('chat.plannedStep.running', '执行中');
  if (status === 'done') return t('chat.plannedStep.done', '已完成');
  return t('chat.plannedStep.running', '执行中');
};

const PlannedExecutionSteps: React.FC<PlannedExecutionStepsProps> = ({
  steps,
  toolCalls,
  isStreaming = false,
}) => {
  const { t } = useTranslation();
  const [isGroupExpanded, setIsGroupExpanded] = useState<boolean>(Boolean(isStreaming));
  const prevStreamingRef = useRef<boolean>(Boolean(isStreaming));

  useEffect(() => {
    if (isStreaming) {
      setIsGroupExpanded(true);
    } else if (prevStreamingRef.current) {
      setIsGroupExpanded(false);
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming]);

  const running = steps.find((step) => shouldExpandPlannedStep(step, isStreaming));
  const doneCount = steps.filter((step) => step.status === 'done').length;
  const failedCount = steps.filter((step) => step.status === 'failed').length;
  const skippedCount = steps.filter((step) => step.status === 'skipped').length;
  const totalSteps = steps.length;
  const toolById = new Map(toolCalls.map((tool) => [tool.id, tool]));

  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(() => {
    if (!running) {
      return new Set<number>();
    }
    return new Set<number>([running.step_index]);
  });

  const toggleStep = (stepIndex: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepIndex)) {
        next.delete(stepIndex);
      } else {
        next.add(stepIndex);
      }
      return next;
    });
  };

  const summaryText = isStreaming
    ? t('chat.plannedStep.summaryRunning', '步骤 {current}/{total}', {
      current: running?.step_index ?? doneCount,
      total: totalSteps,
    })
    : failedCount > 0 || skippedCount > 0
      ? t(
        'chat.plannedStep.summaryPartial',
        '完成 {done} 步{failed}{skipped}',
        {
          done: doneCount,
          failed: failedCount > 0
            ? t('chat.plannedStep.summaryFailed', ' · {count} 步失败', { count: failedCount })
            : '',
          skipped: skippedCount > 0
            ? t('chat.plannedStep.summarySkipped', ' · {count} 步跳过', { count: skippedCount })
            : '',
        }
      )
      : t('chat.plannedStep.summaryDone', '已完成 {count} 步', { count: doneCount });

  return (
    <div className="my-1.5">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 py-0.5 px-1 -ml-1 text-xs text-[var(--color-text-3)] hover:text-[var(--color-text-2)] hover:bg-[var(--color-fill-1)] rounded transition-colors cursor-pointer select-none group border-0 bg-transparent"
        onClick={() => setIsGroupExpanded((prev) => !prev)}
      >
        <RightOutlined className={`text-[9px] text-[var(--color-text-4)] group-hover:text-[var(--color-text-3)] transition-transform duration-200 ${isGroupExpanded ? 'rotate-90' : 'rotate-0'}`} />
        <span className="flex items-center gap-1.5 font-normal">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isStreaming ? 'bg-[var(--color-primary)] animate-pulse' : 'bg-emerald-500'}`} />
          <span className="text-[var(--color-text-2)]">{t('chat.plannedStep.planTitle', '执行计划')}</span>
        </span>
        <span className="text-[11px] text-[var(--color-text-4)] font-mono tabular-nums ml-0.5">
          ({summaryText})
        </span>
      </button>

      {isGroupExpanded && (
        <div className="mt-1.5 ml-1 space-y-1 border-l-2 border-[var(--color-fill-3)] pl-3">
          {steps.map((step) => {
            const expanded = expandedSteps.has(step.step_index);
            const stepTools = step.toolCallIds
              .map((id) => toolById.get(id))
              .filter((tool): tool is PlannedStepToolCall => Boolean(tool));
            const isActive = step.status === 'running' && isStreaming;
            const isFailed = step.status === 'failed';
            const isSkipped = step.status === 'skipped';

            return (
              <div key={step.step_index} className="rounded">
                <button
                  type="button"
                  onClick={() => toggleStep(step.step_index)}
                  aria-expanded={expanded}
                  aria-label={t('chat.plannedStep.stepAria', '步骤 {index} {objective}', {
                    index: step.step_index,
                    objective: step.objective,
                  })}
                  className="flex w-full cursor-pointer items-center gap-1.5 border-0 bg-transparent py-0.5 text-left text-xs transition-colors hover:text-[var(--color-text-1)] select-none group"
                  style={{ color: 'var(--color-text-2)' }}
                >
                  <span
                    className="inline-flex w-3 shrink-0 items-center justify-center text-[9px] text-[var(--color-text-4)] group-hover:text-[var(--color-text-3)] transition-transform"
                    style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                  >
                    ▶
                  </span>
                  <span className="min-w-0 flex-1 leading-5 tabular-nums">
                    <span className="font-medium text-[var(--color-text-1)]">
                      {t('chat.plannedStep.stepTitle', '步骤 {index}/{total}', {
                        index: step.step_index,
                        total: step.total_steps || totalSteps,
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
                          ? 'var(--color-primary-6)'
                          : 'var(--color-text-4)',
                    }}
                  >
                    {statusLabel(step.status, isStreaming, t)}
                  </span>
                </button>

                {expanded && (
                  <div className="pb-1 pl-4">
                    {stepTools.length > 0 ? (
                      <ToolCallGroup
                        toolCalls={stepTools}
                        isStreaming={isActive}
                      />
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
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PlannedExecutionSteps;
