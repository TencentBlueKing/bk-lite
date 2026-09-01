'use client';

import React, { useEffect, useState } from 'react';
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

  return (
    <div
      className="my-2 rounded-md px-3 py-2"
      style={{ background: 'var(--color-fill-1)', fontSize: 13 }}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-medium text-[var(--color-text-1)]">执行计划</span>
        <span className="text-xs text-[var(--color-text-3)] tabular-nums">
          {isStreaming
            ? `步骤 ${running?.step_index ?? doneCount}/${totalSteps}`
            : failedCount > 0
              ? `完成 ${doneCount} 步 · ${failedCount} 步失败`
              : `已完成 ${doneCount} 步`}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        {steps.map((step) => {
          const expanded = expandedSteps.has(step.step_index);
          const stepTools = step.toolCallIds
            .map((id) => toolById.get(id))
            .filter((tool): tool is PlannedStepToolCall => Boolean(tool));
          const isActive = step.status === 'running' && isStreaming;
          const isFailed = step.status === 'failed';

          return (
            <div key={step.step_index} className="rounded-md">
              <button
                type="button"
                onClick={() => toggleStep(step.step_index)}
                aria-expanded={expanded}
                aria-label={`步骤 ${step.step_index} ${step.objective}`}
                className="flex w-full cursor-pointer items-center gap-2 border-0 bg-transparent px-1 py-1.5 text-left"
                style={{ color: 'var(--color-text-2)' }}
              >
                <span
                  className="inline-flex w-3 shrink-0 items-center justify-center text-xs text-[var(--color-text-4)] transition-transform"
                  style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)', fontSize: 10 }}
                >
                  ▶
                </span>
                <span className="min-w-0 flex-1 text-xs leading-5 text-[var(--color-text-1)] tabular-nums">
                  <span className="font-medium">
                    步骤 {step.step_index}/{step.total_steps || totalSteps}
                  </span>
                  <span className="text-[var(--color-text-3)]"> · {step.objective}</span>
                </span>
                <span
                  className="shrink-0 text-xs"
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
                    <div className="px-2 py-1 text-xs text-[var(--color-text-4)]">
                      {isActive ? '等待工具调用…' : '本步无工具调用'}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PlannedExecutionSteps;
