import React from 'react';
import { Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import PageHeaderShell from '@/components/page-header-shell';

export interface PageFormHeaderCardProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  onBackClick?: () => void;
  actions?: React.ReactNode;
  spacing?: 'default' | 'compact' | 'flush';
  className?: string;
  headerRowClassName?: string;
  titleClassName?: string;
  actionsClassName?: string;
}

const PageFormHeaderCard: React.FC<PageFormHeaderCardProps> = ({
  title,
  description,
  onBackClick,
  actions,
  spacing = 'default',
  className = '',
  headerRowClassName,
  titleClassName,
  actionsClassName,
}) => {
  const spacingClassName =
    spacing === 'flush' ? 'mb-0' : spacing === 'compact' ? 'mb-3' : 'mb-4';

  return (
    <PageHeaderShell
      title={title}
      subtitle={description}
      leading={
        onBackClick ? (
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={onBackClick}
            className="p-1!"
            aria-label="Back"
          />
        ) : undefined
      }
      subtitleLeading={
        onBackClick ? (
          <span className="invisible p-1!">
            <ArrowLeftOutlined />
          </span>
        ) : undefined
      }
      className={`${spacingClassName} rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-6 py-4 ${className}`}
      headerRowClassName={headerRowClassName}
      titleRowClassName={onBackClick ? 'mb-1 flex items-center gap-2' : 'mb-1'}
      titleClassName={titleClassName}
      subtitleRowClassName={onBackClick ? 'flex items-start gap-2' : ''}
      actions={actions}
      actionsClassName={actionsClassName}
    />
  );
};

export default PageFormHeaderCard;
