'use client';

import React, { useEffect, useRef, useState } from 'react';
import { RightOutlined } from '@ant-design/icons';
import {
  PlannedExecutionStepData,
  shouldExpandPlannedStep,
} from './plannedExecutionState';
import ToolCallGroup from './ToolCallGroup';

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

const statusLabel = (status: PlannedExecutionStepData['status'], isStreaming: boolean) => {
  if (status === 'failed') return '失败';
  if (status === 'running' && isStreaming) return '执行中';
  if (status === 'done') return '已完成';
  return '执行中';
};

const PlannedExecutionSteps: React.FC<PlannedExecutionStepsProps> = ({
  steps,
  toolCalls,
  isStreaming = false,
}) => {
  const [isGroupExpanded, setIsGroupExpanded] = useState<boolean>(Boolean(isStreaming));
  const prevStreamingRef = useRef<boolean>(Boolean(isStreaming));

  useEffect(() => {
    if (isStreaming) {
      setIsGroupExpanded(true);
    } else if (prevStreamingRef.current) {
      setIsGroupExpanded(false);
    }
    prevStreamingRef.current = Boolean(isStreaming);
  }, [isStreaming]);

  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(() => {
    const initial = new Set<number>();
    steps.forEach((step) => {
      if (shouldExpandPlannedStep(step, isStreaming)) {
        initial.add(step.step_index);
      }
    });
    return initial;
  });

  useEffect(() => {
    if (!isStreaming) {
      setExpandedSteps(new Set());
      return;
    }

    setExpandedSteps((prev) => {
      const next = new Set(prev);
      let changed = false;
      steps.forEach((step) => {
        const shouldOpen = shouldExpandPlannedStep(step, true);
        if (shouldOpen && !next.has(step.step_index)) {
          next.add(step.step_index);
          changed = true;
        }
        if (!shouldOpen && next.has(step.step_index) && (step.status === 'done' || step.status === 'failed')) {
          next.delete(step.step_index);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [steps, isStreaming]);

  if (!steps.length) return null;

  const toolById = new Map(toolCalls.map((tool) => [tool.id, tool]));
  const totalSteps = Math.max(steps[steps.length - 1]?.total_steps || 0, steps.length);
  const doneCount = steps.filter((step) => step.status === 'done' || step.status === 'failed').length;
  const failedCount = steps.filter((step) => step.status === 'failed').length;
  const running = steps.find((step) => step.status === 'running');

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
    ? `步骤 ${running?.step_index ?? doneCount}/${totalSteps}`
    : failedCount > 0
      ? `完成 ${doneCount} 步 · ${failedCount} 步失败`
      : `已完成 ${doneCount} 步`;

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
          <span className="text-[var(--color-text-2)]">执行计划</span>
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

            return (
              <div key={step.step_index} className="rounded">
                <button
                  type="button"
                  onClick={() => toggleStep(step.step_index)}
                  aria-expanded={expanded}
                  aria-label={`步骤 ${step.step_index} ${step.objective}`}
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
                      步骤 {step.step_index}/{step.total_steps || totalSteps}
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
                    {statusLabel(step.status, isStreaming)}
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
                        {isActive ? '等待工具调用…' : '本步无工具调用'}
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
