import React from 'react';
import OperateModal from '@/components/operate-modal';
import {
  type FormFeedbackFooterProps,
  renderFormFeedbackFooter,
} from '@/components/_internal/form-feedback-footer';

type OperateModalProps = React.ComponentProps<typeof OperateModal>;

export interface OperateFormModalProps
  extends Omit<OperateModalProps, 'footer' | 'onCancel'>,
  FormFeedbackFooterProps {
  hideFooter?: boolean;
}

const OperateFormModal: React.FC<OperateFormModalProps> = ({
  confirmText,
  cancelText,
  onConfirm,
  onCancel,
  confirmLoading,
  confirmDisabled,
  cancelDisabled,
  confirmType,
  confirmDanger,
  primaryFirst,
  secondaryActionsPosition,
  extra,
  secondaryActions,
  confirmPopconfirm,
  hideFooter = false,
  ...modalProps
}) => {
  return (
    <OperateModal
      {...modalProps}
      footer={
        hideFooter
          ? null
          : renderFormFeedbackFooter({
            confirmText,
            cancelText,
            onConfirm,
            onCancel,
            confirmLoading,
            confirmDisabled,
            cancelDisabled,
            confirmType,
            confirmDanger,
            primaryFirst,
            secondaryActionsPosition,
            extra,
            secondaryActions,
            confirmPopconfirm,
          })
      }
    />
  );
};

export default OperateFormModal;
