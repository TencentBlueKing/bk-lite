import React from 'react';
import { Modal, ModalProps } from 'antd';
import customModalStyle from './index.module.scss';

interface CustomModalProps
  extends Omit<ModalProps, 'title' | 'footer' | 'centered' | 'subTitle'> {
  title?: React.ReactNode;
  footer?: React.ReactNode;
  headerExtra?: React.ReactNode;
  subTitle?: string;
  centered?: boolean;
  customHeaderClass?: string;
}

const OperateModal: React.FC<CustomModalProps> = ({
  title,
  footer,
  headerExtra,
  centered = true,
  subTitle = '',
  customHeaderClass = customModalStyle.customModalHeader,
  maskClosable = false,
  destroyOnClose,
  destroyOnHidden,
  ...modalProps
}) => {
  return (
    <Modal
      styles={{ body: { overflowY: 'auto', maxHeight: 'calc(80vh - 108px)' } }}
      className={customModalStyle.customModal}
      classNames={{
        body: customModalStyle.customModalBody,
        header: customHeaderClass,
        footer: customModalStyle.customModalFooter,
        content: customModalStyle.customModalContent,
      }}
      title={
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center min-w-0">
            {title}
            {subTitle && (
              <span
                style={{
                  color: 'var(--color-text-3)',
                  fontSize: '12px',
                  fontWeight: 'normal',
                }}
              >
                {' '}
                - {subTitle}
              </span>
            )}
          </div>
          {headerExtra ? <div className="shrink-0">{headerExtra}</div> : null}
        </div>
      }
      footer={footer}
      centered={centered}
      maskClosable={maskClosable}
      destroyOnHidden={destroyOnHidden ?? destroyOnClose}
      {...modalProps}
    />
  );
};

export default OperateModal;
