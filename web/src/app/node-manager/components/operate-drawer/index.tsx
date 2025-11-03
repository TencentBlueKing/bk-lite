import React from 'react';
import { Drawer, DrawerProps } from 'antd';
import customDrawerStyle from './index.module.scss';

interface CustomDrawerProps
  extends Omit<DrawerProps, 'title' | 'footer' | 'headerStyle' | 'bodyStyle'> {
  title?: React.ReactNode;
  footer?: React.ReactNode;
  subTitle?: React.ReactNode;
  headerExtra?: React.ReactNode;
}

const OperateDrawer: React.FC<CustomDrawerProps> = ({
  title,
  footer,
  subTitle = '',
  headerExtra,
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
        <div className={customDrawerStyle.customDrawerFooter}>{footer}</div>
      }
      {...drawerProps}
    />
  );
};

export default OperateDrawer;
