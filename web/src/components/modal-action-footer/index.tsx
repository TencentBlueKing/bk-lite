import React from 'react';
import { Button, Popconfirm } from 'antd';
import type { ButtonProps, PopconfirmProps } from 'antd';

type ConfirmPopconfirmProps = Omit<PopconfirmProps, 'children' | 'onConfirm'>;

export interface ModalActionFooterProps {
  confirmText?: React.ReactNode;
  cancelText?: React.ReactNode;
  onConfirm?: () => void;
  onCancel?: () => void;
  confirmLoading?: boolean;
  confirmDisabled?: boolean;
  cancelDisabled?: boolean;
  confirmType?: ButtonProps['type'];
  confirmDanger?: boolean;
  primaryFirst?: boolean;
  secondaryActionsPosition?: 'beforeConfirm' | 'afterConfirm';
  extra?: React.ReactNode;
  secondaryActions?: React.ReactNode;
  confirmPopconfirm?: ConfirmPopconfirmProps;
}

const ModalActionFooter: React.FC<ModalActionFooterProps> = ({
  confirmText,
  cancelText,
  onConfirm,
  onCancel,
  confirmLoading = false,
  confirmDisabled = false,
  cancelDisabled = false,
  confirmType = 'primary',
  confirmDanger = false,
  primaryFirst = true,
  secondaryActionsPosition = 'beforeConfirm',
  extra,
  secondaryActions,
  confirmPopconfirm,
}) => {
  const confirmButtonNode = confirmText ? (
    <Button
      key="confirm"
      type={confirmType}
      danger={confirmDanger}
      loading={confirmLoading}
      disabled={confirmDisabled}
      onClick={onConfirm}
    >
      {confirmText}
    </Button>
  ) : null;
  const confirmButton =
    confirmButtonNode && confirmPopconfirm && onConfirm ? (
      <Popconfirm {...confirmPopconfirm} onConfirm={onConfirm}>
        {confirmButtonNode}
      </Popconfirm>
    ) : (
      confirmButtonNode
    );

  const cancelButton = cancelText ? (
    <Button key="cancel" disabled={cancelDisabled} onClick={onCancel}>
      {cancelText}
    </Button>
  ) : null;

  const secondaryBeforeConfirm =
    secondaryActionsPosition === 'beforeConfirm' ? secondaryActions : null;
  const secondaryAfterConfirm =
    secondaryActionsPosition === 'afterConfirm' ? secondaryActions : null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>{extra}</div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {primaryFirst ? (
          <>
            {secondaryBeforeConfirm}
            {confirmButton}
            {secondaryAfterConfirm}
            {cancelButton}
          </>
        ) : (
          <>
            {cancelButton}
            {secondaryBeforeConfirm}
            {confirmButton}
            {secondaryAfterConfirm}
          </>
        )}
      </div>
    </div>
  );
};

export default ModalActionFooter;
