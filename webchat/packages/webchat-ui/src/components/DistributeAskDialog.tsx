import React, { useEffect, useId } from 'react';
import { WC } from '../chrome';

interface DistributeAskDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 对齐技能测试和 Web 发布里的 Ant Design Modal.confirm：
 * 宽 416、距顶 100、警告圆标、主色确认。点遮罩不关闭。
 */
export const DistributeAskDialog: React.FC<DistributeAskDialogProps> = ({
  isOpen,
  title,
  message,
  confirmText,
  cancelText,
  onConfirm,
  onCancel,
}) => {
  const titleId = useId();

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCancel();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50"
      style={{ background: 'rgba(0, 0, 0, 0.45)' }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="absolute left-1/2 box-border"
        style={{
          top: 100,
          width: 416,
          maxWidth: 'calc(100vw - 32px)',
          transform: 'translateX(-50%)',
          padding: '20px 24px',
          borderRadius: 8,
          background: WC.white,
          boxShadow: '0 6px 16px 0 rgba(0, 0, 0, 0.08), 0 3px 6px -4px rgba(0, 0, 0, 0.12), 0 9px 28px 8px rgba(0, 0, 0, 0.05)',
        }}
      >
        <div className="flex items-start">
          <span className="mr-3 mt-0.5 shrink-0" style={{ color: WC.warning }} aria-hidden="true">
            <svg width="22" height="22" viewBox="64 64 896 896" fill="currentColor">
              <path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm-32 232c0-4.4 3.6-8 8-8h48c4.4 0 8 3.6 8 8v272c0 4.4-3.6 8-8 8h-48c-4.4 0-8-3.6-8-8V296zm32 440a48.01 48.01 0 010-96 48.01 48.01 0 010 96z" />
            </svg>
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <span id={titleId} className="text-base font-semibold leading-6" style={{ color: WC.botText }}>
              {title}
            </span>
            <div className="break-all text-sm leading-6" style={{ color: WC.botText }}>
              {message}
            </div>
          </div>
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="h-8 rounded-md border px-4 text-sm"
            style={{
              background: WC.white,
              borderColor: WC.dockEdge,
              color: WC.botText,
            }}
          >
            {cancelText}
          </button>
          <button
            type="button"
            autoFocus
            onClick={onConfirm}
            className="h-8 rounded-md border px-4 text-sm"
            style={{
              background: WC.indigo,
              borderColor: WC.indigo,
              color: WC.onPrimary,
            }}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};
