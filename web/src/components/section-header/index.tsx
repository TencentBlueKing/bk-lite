import React from 'react';
import Icon from '@/components/icon';
import PageHeaderShell from '@/components/page-header-shell';

interface SectionHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  iconType?: string;
  actions?: React.ReactNode;
  variant?: 'default' | 'panel' | 'compact';
  spacing?: 'default' | 'regular' | 'compact' | 'flush';
  className?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  actionsClassName?: string;
}

const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  description,
  icon,
  iconType,
  actions,
  variant = 'default',
  spacing = 'default',
  className = '',
  titleClassName = '',
  descriptionClassName = '',
  actionsClassName = '',
}) => {
  const resolvedIcon = icon ? (
    icon
  ) : iconType ? (
    <Icon type={iconType} className="text-lg text-[var(--color-text-2)]" />
  ) : null;

  const variantTitleClassName =
    variant === 'panel'
      ? 'text-[16px] leading-6 text-[var(--color-text-1)]'
      : variant === 'compact'
        ? 'text-[16px] font-medium leading-tight text-[var(--color-text-1)]'
        : 'text-base font-semibold text-[var(--color-text-1)]';

  const variantDescriptionClassName =
    variant === 'panel'
      ? 'text-[12px] leading-5 text-[var(--color-text-3)]'
      : 'text-sm text-[var(--color-text-3)]';
  const spacingClassName =
    spacing === 'flush' ? 'mb-0' : spacing === 'compact' ? 'mb-3' : spacing === 'regular' ? 'mb-4' : 'mb-6';

  return (
    <PageHeaderShell
      className={`${spacingClassName} ${className}`.trim()}
      title={title}
      subtitle={description}
      leading={resolvedIcon}
      actions={actions}
      titleClassName={[
        variantTitleClassName,
        titleClassName,
      ].join(' ').trim()}
      subtitleClassName={[
        variantDescriptionClassName,
        descriptionClassName,
      ].join(' ').trim()}
      actionsClassName={`flex shrink-0 items-center gap-2 ${actionsClassName}`.trim()}
    />
  );
};

export default SectionHeader;
