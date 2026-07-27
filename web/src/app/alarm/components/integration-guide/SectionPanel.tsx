import React from 'react';
import PanelShell from '@/components/panel-shell';
import SectionHeader from '@/components/section-header';

interface AlarmIntegrationGuideSectionPanelProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  headerVariant?: 'default' | 'panel' | 'compact';
}

const AlarmIntegrationGuideSectionPanel: React.FC<
  AlarmIntegrationGuideSectionPanelProps
> = ({
  title,
  description,
  children,
  className = 'overflow-hidden rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]',
  headerClassName = 'border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_3%,var(--color-bg-1))] px-5 py-4',
  bodyClassName = 'px-5 py-4',
  titleClassName = '',
  descriptionClassName = '',
  headerVariant = 'panel',
}) => {
  return (
    <PanelShell
      className={className}
      headerClassName={headerClassName}
      bodyClassName={bodyClassName}
      header={(
        <SectionHeader
          title={title}
          description={description}
          variant={headerVariant}
          className="mb-0"
          titleClassName={titleClassName}
          descriptionClassName={descriptionClassName}
        />
      )}
    >
      {children}
    </PanelShell>
  );
};

export default AlarmIntegrationGuideSectionPanel;
