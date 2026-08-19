import React from 'react';
import { Modal, ModalProps } from 'antd';
import customModalStyle from './index.module.scss';

interface CustomModalProps
  extends Omit<ModalProps, 'title' | 'footer' | 'centered' | 'subTitle'> {
  title?: React.ReactNode;
  footer?: React.ReactNode;
  headerExtra?: React.ReactNode;
  subTitle?: React.ReactNode;
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
  const shouldDestroyOnHidden = destroyOnHidden ?? destroyOnClose;
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
      // 默认预挂载，供 useEffect + setFieldsValue 的编辑弹窗首次打开回填。
      // 若调用方要靠 destroyOnHidden + initialValues 重挂载（如节点配置），则不能预挂载，否则会锁死空表单。
      forceRender={!shouldDestroyOnHidden}
      destroyOnHidden={shouldDestroyOnHidden}
      {...modalProps}
    />
  );
};

export default OperateModal;
