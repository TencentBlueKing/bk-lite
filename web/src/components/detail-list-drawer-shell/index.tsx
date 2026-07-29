'use client';

import React from 'react';
import ContentDrawer from '@/components/content-drawer';
import DetailListPanel from '@/components/detail-list-panel';

type DetailListPanelProps = React.ComponentProps<typeof DetailListPanel>;

export interface DetailListDrawerShellProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  width?: number;
  items: DetailListPanelProps['items'];
  labelWidthClassName?: DetailListPanelProps['labelWidthClassName'];
  className?: DetailListPanelProps['className'];
  extra?: React.ReactNode;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  destroyOnClose?: boolean;
  loading?: boolean;
  bodyClassName?: string;
  styles?: React.ComponentProps<typeof ContentDrawer>['styles'];
}

const DetailListDrawerShell: React.FC<DetailListDrawerShellProps> = ({
  open,
  onClose,
  title,
  width = 680,
  items,
  labelWidthClassName,
  className,
  extra,
  footer,
  children,
  destroyOnClose,
  loading,
  bodyClassName = 'flex flex-col gap-4',
  styles,
}) => {
  return (
    <ContentDrawer
      title={title}
      open={open}
      onClose={onClose}
      width={width}
      extra={extra}
      footer={footer}
      destroyOnClose={destroyOnClose}
      loading={loading}
      styles={styles}
    >
      <div className={bodyClassName}>
        {items.length ? (
          <DetailListPanel
            items={items}
            labelWidthClassName={labelWidthClassName}
            className={className}
          />
        ) : null}
        {children}
      </div>
    </ContentDrawer>
  );
};

export default DetailListDrawerShell;
