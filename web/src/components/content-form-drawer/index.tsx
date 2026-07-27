import React from 'react';
import ContentDrawer from '@/components/content-drawer';
import {
  type FormFeedbackFooterProps,
  renderFormFeedbackFooter,
} from '@/components/_internal/form-feedback-footer';

type ContentDrawerProps = React.ComponentProps<typeof ContentDrawer>;

export interface ContentFormDrawerProps
  extends Omit<ContentDrawerProps, 'footer' | 'title' | 'content'>,
  FormFeedbackFooterProps {
  title?: React.ReactNode;
  content?: React.ReactNode;
  headerExtra?: React.ReactNode;
  hideFooter?: boolean;
  loading?: boolean;
}

const ContentFormDrawer: React.FC<ContentFormDrawerProps> = ({
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
  headerExtra,
  hideFooter = false,
  ...drawerProps
}) => {
  return (
    <ContentDrawer
      {...drawerProps}
      extra={headerExtra}
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

export default ContentFormDrawer;
