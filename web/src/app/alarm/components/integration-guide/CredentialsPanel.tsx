import React from 'react';
import AlarmIntegrationGuideSectionPanel from '@/app/alarm/components/integration-guide/SectionPanel';

interface AlarmIntegrationGuideCredentialsPanelProps {
  title: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
}

const AlarmIntegrationGuideCredentialsPanel: React.FC<
  AlarmIntegrationGuideCredentialsPanelProps
> = ({
  title,
  children,
  className = 'rounded-[16px] border border-[var(--color-primary-bg-active)] bg-[var(--color-bg-1)]',
  headerClassName = 'px-4 pt-4',
  bodyClassName = 'px-4 pb-4',
}) => {
  return (
    <AlarmIntegrationGuideSectionPanel
      title={title}
      headerVariant="compact"
      className={className}
      headerClassName={headerClassName}
      bodyClassName={bodyClassName}
    >
      {children}
    </AlarmIntegrationGuideSectionPanel>
  );
};

export default AlarmIntegrationGuideCredentialsPanel;
