import React from 'react';
import OperateDrawer from '@/components/operate-drawer';
import {
  type FormFeedbackFooterProps,
  renderFormFeedbackFooter,
} from '@/components/_internal/form-feedback-footer';

type OperateDrawerProps = React.ComponentProps<typeof OperateDrawer>;

export interface OperateFormDrawerProps
  extends Omit<OperateDrawerProps, 'footer'>,
  FormFeedbackFooterProps {
  hideFooter?: boolean;
}

const OperateFormDrawer: React.FC<OperateFormDrawerProps> = ({
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
  hideFooter = false,
  ...drawerProps
}) => {
  return (
    <OperateDrawer
      {...drawerProps}
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
          })
      }
    />
  );
};

export default OperateFormDrawer;
