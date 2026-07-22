'use client';

import React from 'react';
import { Button, Space } from 'antd';

export interface FormFeedbackFooterProps {
  confirmText?: React.ReactNode;
  cancelText?: React.ReactNode;
  onConfirm?: () => void;
  onCancel?: () => void;
  confirmLoading?: boolean;
  confirmDisabled?: boolean;
  cancelDisabled?: boolean;
  confirmType?: 'primary' | 'default' | 'dashed' | 'link' | 'text';
  confirmDanger?: boolean;
  primaryFirst?: boolean;
  secondaryActions?: React.ReactNode;
  secondaryActionsPosition?: 'left' | 'right' | 'afterConfirm';
  extra?: React.ReactNode;
  confirmPopconfirm?: {
    title: React.ReactNode;
    description?: React.ReactNode;
    okText?: React.ReactNode;
    cancelText?: React.ReactNode;
    onConfirm?: () => void | Promise<void>;
  };
}

export const renderFormFeedbackFooter = ({
  confirmText = 'common.confirm',
  cancelText = 'common.cancel',
  onConfirm,
  onCancel,
  confirmLoading = false,
  confirmDisabled = false,
  cancelDisabled = false,
  confirmType = 'primary',
  confirmDanger = false,
  primaryFirst = true,
  secondaryActions,
  secondaryActionsPosition = 'left',
}: FormFeedbackFooterProps): React.ReactNode => {
  const confirm = (
    <Button
      type={confirmType}
      danger={confirmDanger}
      loading={confirmLoading}
      disabled={confirmDisabled}
      onClick={onConfirm}
    >
      {confirmText}
    </Button>
  );
  const cancel = (
    <Button
      disabled={cancelDisabled}
      onClick={onCancel}
    >
      {cancelText}
    </Button>
  );

  return (
    <Space>
      {secondaryActions && secondaryActionsPosition === 'left' ? secondaryActions : null}
      {primaryFirst ? (
        <>
          {confirm}
          {cancel}
        </>
      ) : (
        <>
          {cancel}
          {confirm}
        </>
      )}
      {secondaryActions && secondaryActionsPosition === 'right' ? secondaryActions : null}
    </Space>
  );
};

export default renderFormFeedbackFooter;
