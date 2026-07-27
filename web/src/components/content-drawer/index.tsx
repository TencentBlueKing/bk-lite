import React from 'react';
import { Drawer } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface ContentDrawerProps {
  visible?: boolean;
  open?: boolean;
  onClose: () => void;
  content?: React.ReactNode;
  title?: React.ReactNode;
  width?: number;
  extra?: React.ReactNode;
  styles?: { header?: React.CSSProperties; body?: React.CSSProperties };
  footer?: React.ReactNode;
  maskClosable?: boolean;
  destroyOnClose?: boolean;
  loading?: boolean;
  children?: React.ReactNode;
}

const ContentDrawer: React.FC<ContentDrawerProps> = ({ visible, open, onClose, content, title, width, extra, styles, footer, maskClosable, destroyOnClose, children }) => {
  const { t } = useTranslation();

  const formatContent = (text: React.ReactNode) => {
    if (typeof text !== 'string') return text;
    return text.split('\n').map((line, index) => (
      <React.Fragment key={index}>
        {line}
        {index < text.split('\n').length - 1 && <br />}
      </React.Fragment>
    ));
  };

  return (
    <Drawer
      title={title || t('common.viewDetails')}
      placement="right"
      onClose={onClose}
      open={open ?? visible ?? false}
      width={width || 600}
      extra={extra}
      styles={styles}
      footer={footer}
      maskClosable={maskClosable}
      destroyOnClose={destroyOnClose}
    >
      {children ? children : (
        <div className="whitespace-pre-wrap leading-6">
          {content ? formatContent(content) : null}
        </div>
      )}
    </Drawer>
  );
};

export default ContentDrawer;