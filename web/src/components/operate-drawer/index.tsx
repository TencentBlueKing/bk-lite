import React from 'react';
import { Drawer, DrawerProps } from 'antd';
import customDrawerStyle from './index.module.scss';

export interface OperateDrawerProps
  extends Omit<DrawerProps, 'title' | 'footer' | 'headerStyle'> {
  title?: React.ReactNode;
  footer?: React.ReactNode;
  subTitle?: React.ReactNode;
  headerExtra?: React.ReactNode;
}

const OperateDrawer: React.FC<OperateDrawerProps> = ({
  title,
  footer,
  subTitle = '',
  headerExtra,
  bodyStyle,
  styles,
  ...drawerProps
}) => {
  return (
    <Drawer
      className={customDrawerStyle.customDrawer}
      title={
        <div>
          <div className={customDrawerStyle.customDrawerHeader}>
            <span>{title}</span>
            {subTitle && (
              <span
                style={{
                  color: 'var(--color-text-3)',
                  fontSize: '12px',
                  fontWeight: 'normal',
                }}
              >
                - {subTitle}
              </span>
            )}
          </div>
          {headerExtra && <div style={{ marginTop: '8px' }}>{headerExtra}</div>}
        </div>
      }
      footer={
        footer ? (
          <div className={customDrawerStyle.customDrawerFooter}>{footer}</div>
        ) : undefined
      }
      styles={{
        ...styles,
        body: {
          ...bodyStyle,
          ...styles?.body,
        },
      }}
      {...drawerProps}
    />
  );
};

export default OperateDrawer;
