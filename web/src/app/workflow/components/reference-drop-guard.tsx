'use client';

import { App } from 'antd';
import { useRef, type DragEvent, type ReactNode } from 'react';

import { useTranslation } from '@/utils/i18n';

import { WORKFLOW_REFERENCE_MIME } from './workflow-template-text-field';

export function isWorkflowReferenceDrag(event: DragEvent | DragEvent<Element>) {
  return Array.from(event.dataTransfer.types || []).includes(WORKFLOW_REFERENCE_MIME);
}

/** Blocks upstream-field drops on literal/select-only controls and explains why. */
export function ReferenceDropGuard({
  children,
  disabled = false,
  reason,
  className = 'w-full',
}: {
  children: ReactNode;
  disabled?: boolean;
  reason?: string;
  /** 默认铺满；与固定宽控件并排时传 `shrink-0`，避免挤扁相邻输入框。 */
  className?: string;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const warnedRef = useRef(false);
  const rejectMessage = reason || t(
    'workflowOrchestration.editor.literalFieldDropRejected',
    '该字段只支持从选项中选择或手动填写，不支持拖入上游字段',
  );

  const reject = (event: DragEvent<HTMLDivElement>) => {
    if (disabled || !isWorkflowReferenceDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'none';
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    if (disabled || !isWorkflowReferenceDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'none';
    if (warnedRef.current) return;
    warnedRef.current = true;
    message.warning(rejectMessage);
  };

  return (
    <div
      data-testid="workflow-reference-drop-guard"
      className={className}
      onDragEnter={reject}
      onDragOverCapture={reject}
      onDragLeave={() => { warnedRef.current = false; }}
      onDropCapture={onDrop}
    >
      {children}
    </div>
  );
}
