import React from 'react';
import { Drawer, DrawerProps } from 'antd';
import customDrawerStyle from './index.module.scss';

interface CustomDrawerProps
  extends Omit<DrawerProps, 'title' | 'footer' | 'headerStyle' | 'bodyStyle'> {
  title?: React.ReactNode;
  footer?: React.ReactNode;
  subTitle?: React.ReactNode;
  headerExtra?: React.ReactNode;
  bodyStyle?: React.CSSProperties;
}

const OperateDrawer: React.FC<CustomDrawerProps> = ({
  title,
  footer,
  subTitle = '',
  headerExtra,
  bodyStyle,
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
                {' '}
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
      bodyStyle={{ padding: '16px', overflow: 'auto', ...bodyStyle }}
      {...drawerProps}
    />
  );
};

export default OperateDrawer;
