import React from 'react';
import { WC } from '../chrome';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = '确定',
  cancelText = '取消',
}) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: WC.overlay }}
      onClick={onCancel}
    >
      <div
        className="mx-4 max-w-sm rounded-lg p-6"
        style={{
          background: WC.white,
          border: `1px solid ${WC.botBorder}`,
          boxShadow: WC.shadow,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start gap-3">
          <div
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full"
            style={{ background: WC.warningBg }}
          >
            <svg
              className="h-6 w-6"
              style={{ color: WC.warning }}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="mb-2 text-lg font-semibold" style={{ color: WC.botText }}>
              {title}
            </h3>
            <p className="text-sm" style={{ color: WC.muted }}>
              {message}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: WC.page, color: WC.botText }}
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: WC.fail, color: WC.onPrimary }}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};
