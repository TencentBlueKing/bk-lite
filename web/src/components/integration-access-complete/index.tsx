import React from 'react';
import { Button } from 'antd';
import Icon from '@/components/icon';

export interface IntegrationAccessCompleteAction {
  key: string;
  label: React.ReactNode;
  onClick: () => void;
  type?: 'primary' | 'default';
}

export interface IntegrationAccessCompleteProps {
  title: React.ReactNode;
  description: React.ReactNode;
  subDescription?: React.ReactNode;
  actions: IntegrationAccessCompleteAction[];
  primaryIconType?: string;
  statusIconType?: string;
}

const IntegrationAccessComplete: React.FC<IntegrationAccessCompleteProps> = ({
  title,
  description,
  subDescription,
  actions,
  primaryIconType = 'yunhangzhongx',
  statusIconType = 'finish',
}) => {
  return (
    <div className="p-[20px] text-center">
      <div className="mb-6">
        <div className="mx-auto flex items-center justify-center">
          <Icon type={primaryIconType} className="text-8xl" />
        </div>
      </div>
      <div className="mb-6">
        <div className="mb-4 flex items-center justify-center">
          <Icon type={statusIconType} className="mr-2 text-4xl" />
          <h3 className="text-2xl font-bold text-gray-900">{title}</h3>
        </div>
        <p className="mb-3 text-lg leading-relaxed">{description}</p>
        {subDescription ? (
          <p className="text-base leading-relaxed text-[var(--color-text-3)]">
            {subDescription}
          </p>
        ) : null}
      </div>
      <div className="mb-[10px] flex flex-wrap justify-center gap-[10px]">
        {actions.map((action) => (
          <Button
            key={action.key}
            type={action.type === 'primary' ? 'primary' : 'default'}
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        ))}
      </div>
    </div>
  );
};

export default IntegrationAccessComplete;
export {
  createCmdbK8sAccessCompletePreset,
  createLogK8sAccessCompletePreset,
  createMonitorFlowAccessCompletePreset,
  createMonitorK8sAccessCompletePreset,
} from './presets';
