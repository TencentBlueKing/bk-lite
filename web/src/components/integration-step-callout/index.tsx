import React from 'react';
import { InfoCircleOutlined } from '@ant-design/icons';
import SectionHeader from '@/components/section-header';

export interface IntegrationStepCalloutProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  items?: React.ReactNode[];
  className?: string;
}

const IntegrationStepCallout: React.FC<IntegrationStepCalloutProps> = ({
  title,
  description,
  items = [],
  className = '',
}) => {
  return (
    <div className={className}>
      <SectionHeader
        className="mb-3"
        icon={
          <InfoCircleOutlined className="text-lg text-[var(--color-primary)]" />
        }
        title={title}
      />
      <div className="mb-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
        {description ? (
          <p className="mb-3 text-sm leading-6 text-[var(--color-text-2)]">
            {description}
          </p>
        ) : null}
        {items.length ? (
          <ul className="space-y-2 text-sm leading-6 text-[var(--color-text-3)]">
            {items.map((item, index) => (
              <li key={index} className="flex items-start gap-2">
                <span className="mt-[7px] h-1.5 w-1.5 flex-none rounded-full bg-[var(--color-primary)]" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
};

export default IntegrationStepCallout;
export {
  createLogK8sStepCalloutPreset,
  createMonitorK8sStepCalloutPreset,
} from './presets';
export type { IntegrationStepCalloutPreset } from './presets';
